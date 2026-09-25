from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from darevskia_spot_matcher import (  # noqa: E402
    ManifestRecord,
    SpotFeature,
    add_label,
    create_pattern_enhanced_preview,
    create_dark_spot_map,
    geometric_match,
    infer_records,
    masked_corrcoef,
    make_spot_outline_preview_bgr,
    pil_from_bgr,
    resize_long_side,
    split_records,
    make_spot_preview_bgr,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="5-landmark curved dorsal belt matcher: build a standardized belt along a curved dorsal axis and compare spot patterns inside that belt."
    )
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--landmarks", help="CSV containing 5-point axis landmarks. Defaults to project_dir/config/axis_belt_landmarks.csv.")
    parser.add_argument("--output", help="Output folder. Defaults to project_dir/outputs/axis_belt_run.")
    parser.add_argument("--max-side", type=int, default=2200, help="Resize the longest image side to at most this value before building the belt.")
    parser.add_argument("--preview-side", type=int, default=900, help="Save belt previews with this longest-side cap.")
    parser.add_argument("--thumb-size", type=int, default=256, help="Low-resolution size used for spot-map correlation.")
    parser.add_argument("--belt-width", type=int, default=360, help="Width of the standardized belt image in pixels.")
    parser.add_argument("--belt-height", type=int, default=900, help="Height of the standardized belt image in pixels.")
    parser.add_argument("--belt-breadth-fraction", type=float, default=0.14, help="Belt breadth as a fraction of the full axis length in the source image.")
    parser.add_argument("--belt-breadth-px", type=float, default=None, help="Optional absolute belt breadth in source-image pixels. Overrides belt-breadth-fraction.")
    parser.add_argument("--inner-margin", type=float, default=0.03, help="Fraction to trim from each side of the standardized belt to avoid boundary noise.")
    parser.add_argument("--max-specimens", type=int, default=None, help="Optional cap on the number of specimens included, in manifest/specimen order.")
    parser.add_argument("--gallery-per-specimen", type=int, default=None, help="Optional cap on gallery images per specimen.")
    parser.add_argument("--gallery-sampling", choices=("first", "spaced", "last"), default="last", help="How to sample gallery images when gallery_per_specimen is smaller than the available images.")
    parser.add_argument("--query-per-specimen", type=int, default=None, help="Optional cap on query images per specimen.")
    parser.add_argument("--max-gallery", type=int, default=None, help="Optional cap on gallery image count after per-specimen sampling.")
    parser.add_argument("--max-query", type=int, default=None, help="Optional cap on query image count after per-specimen sampling.")
    parser.add_argument("--allow-new-specimen", action="store_true", help="Allow rejection of a weak match as NEW_SPECIMEN.")
    parser.add_argument("--new-specimen-threshold", type=float, default=0.20, help="Reject as new if the best score falls below this threshold.")
    parser.add_argument("--new-specimen-margin", type=float, default=0.035, help="Reject as new if the best-vs-second score gap is below this margin and the best score is still weak.")
    parser.add_argument("--consensus-top-k", type=int, default=2, help="Number of top gallery images per specimen to average for specimen-level consensus scoring.")
    return parser.parse_args()


def read_image_bgr_raw(image_path: Path) -> np.ndarray:
    pil_image = Image.open(image_path).convert("RGB")
    rgb = np.asarray(pil_image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def ensure_dirs(base_output: Path) -> dict[str, Path]:
    mapping = {
        "overlay": base_output / "overlay",
        "belt": base_output / "belt",
        "spots": base_output / "spots",
        "qc": base_output / "qc",
    }
    for path in mapping.values():
        path.mkdir(parents=True, exist_ok=True)
    return mapping


def load_landmarks(csv_path: Path) -> dict[str, dict[str, object]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Landmarks file not found: {csv_path}")

    rows: dict[str, dict[str, object]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            relative_path = str(row["relative_path"]).replace("/", "\\")
            point_count = int(row.get("point_count") or 0)
            points: list[tuple[float, float]] = []
            for idx in range(1, point_count + 1):
                x_value = row.get(f"x{idx}", "")
                y_value = row.get(f"y{idx}", "")
                if x_value == "" or y_value == "":
                    continue
                points.append((float(x_value), float(y_value)))
            if len(points) < 5:
                continue
            rows[relative_path] = {
                "relative_path": relative_path,
                "specimen_id": str(row["specimen_id"]),
                "split": str(row["split"]).lower(),
                "image_width": int(float(row.get("image_width") or 0)),
                "image_height": int(float(row.get("image_height") or 0)),
                "point_count": point_count,
                "points": points[:5],
            }
    return rows


def safe_normalize(vector: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-6:
        fallback_norm = float(np.linalg.norm(fallback))
        if fallback_norm < 1e-6:
            return np.array([0.0, 1.0], dtype=np.float32)
        return (fallback / fallback_norm).astype(np.float32)
    return (vector / norm).astype(np.float32)


def rotate_ccw_90(vector: np.ndarray) -> np.ndarray:
    return np.array([-vector[1], vector[0]], dtype=np.float32)


def polyline_arrays(points: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    pts = np.asarray(points, dtype=np.float32)
    segs = pts[1:] - pts[:-1]
    seg_lens = np.linalg.norm(segs, axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg_lens, dtype=np.float32)])
    total_length = float(cumulative[-1]) if len(cumulative) else 0.0
    return pts, segs, cumulative, total_length


def center_at_arclength(points: np.ndarray, cumulative: np.ndarray, arclength: float) -> np.ndarray:
    if len(points) == 1:
        return points[0].copy()
    total_length = float(cumulative[-1])
    arclength = float(np.clip(arclength, 0.0, total_length))
    idx = int(np.searchsorted(cumulative, arclength, side="right") - 1)
    idx = max(0, min(idx, len(points) - 2))
    seg_start = points[idx]
    seg_end = points[idx + 1]
    seg_len = float(cumulative[idx + 1] - cumulative[idx])
    if seg_len < 1e-6:
        return seg_start.copy()
    frac = (arclength - float(cumulative[idx])) / seg_len
    return (seg_start * (1.0 - frac)) + (seg_end * frac)


def center_and_tangent(points: np.ndarray, cumulative: np.ndarray, arclength: float) -> tuple[np.ndarray, np.ndarray]:
    total_length = float(cumulative[-1])
    center = center_at_arclength(points, cumulative, arclength)
    delta = max(4.0, total_length * 0.02)
    before = center_at_arclength(points, cumulative, max(0.0, arclength - delta))
    after = center_at_arclength(points, cumulative, min(total_length, arclength + delta))
    tangent = safe_normalize(after - before, np.array([0.0, 1.0], dtype=np.float32))
    return center.astype(np.float32), tangent


def build_belt(
    image_bgr: np.ndarray,
    points: list[tuple[float, float]],
    belt_width: int,
    belt_height: int,
    belt_breadth_px: float,
    inner_margin: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    poly_points, _segments, cumulative, total_length = polyline_arrays(points)
    if total_length < 1e-6:
        raise ValueError("The 5 axis landmarks do not define a usable dorsal axis.")

    half_breadth = float(belt_breadth_px) / 2.0
    sample_s = np.linspace(0.0, total_length, num=belt_height, dtype=np.float32)
    offsets = np.linspace(-half_breadth, half_breadth, num=belt_width, dtype=np.float32)

    map_x = np.zeros((belt_height, belt_width), dtype=np.float32)
    map_y = np.zeros((belt_height, belt_width), dtype=np.float32)
    top_edge = np.zeros((belt_height, 2), dtype=np.float32)
    bottom_edge = np.zeros((belt_height, 2), dtype=np.float32)

    for row_idx, arclength in enumerate(sample_s):
        center, tangent = center_and_tangent(poly_points, cumulative, float(arclength))
        normal = rotate_ccw_90(tangent)
        coords = center[None, :] + (offsets[:, None] * normal[None, :])
        map_x[row_idx, :] = coords[:, 0]
        map_y[row_idx, :] = coords[:, 1]
        top_edge[row_idx] = coords[0]
        bottom_edge[row_idx] = coords[-1]

    belt = cv2.remap(
        image_bgr,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    src_mask = np.full(image_bgr.shape[:2], 255, dtype=np.uint8)
    belt_mask = cv2.remap(
        src_mask,
        map_x,
        map_y,
        interpolation=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    margin_x = max(0, int(round(belt_width * inner_margin)))
    x0 = min(margin_x, max(0, belt_width // 8))
    x1 = max(x0 + 8, belt_width - x0)
    trimmed_belt = belt[:, x0:x1].copy()
    trimmed_mask = belt_mask[:, x0:x1].copy()
    return trimmed_belt, trimmed_mask, top_edge, bottom_edge


def draw_overlay(image_bgr: np.ndarray, points: list[tuple[float, float]], top_edge: np.ndarray, bottom_edge: np.ndarray) -> np.ndarray:
    overlay = image_bgr.copy()
    center_poly = np.asarray(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(overlay, [center_poly], False, (0, 255, 255), 3, cv2.LINE_AA)

    step = max(1, len(top_edge) // 60)
    top_poly = np.asarray(top_edge[::step], dtype=np.int32).reshape((-1, 1, 2))
    bottom_poly = np.asarray(bottom_edge[::step], dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(overlay, [top_poly], False, (0, 255, 120), 3, cv2.LINE_AA)
    cv2.polylines(overlay, [bottom_poly], False, (0, 255, 120), 3, cv2.LINE_AA)

    for idx, (x_value, y_value) in enumerate(points, start=1):
        center = (int(round(x_value)), int(round(y_value)))
        cv2.circle(overlay, center, 8, (255, 80, 0), -1, lineType=cv2.LINE_AA)
        cv2.putText(
            overlay,
            str(idx),
            (center[0] + 10, center[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return overlay


def preprocess_belt_feature(
    record: ManifestRecord,
    landmark_entry: dict[str, object],
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    belt_width: int,
    belt_height: int,
    belt_breadth_fraction: float,
    belt_breadth_px_override: float | None,
    inner_margin: float,
) -> SpotFeature:
    image_bgr = read_image_bgr_raw(record.image_path)
    working, _, scale = resize_long_side(image_bgr, max_side)
    points = [(float(x) * scale, float(y) * scale) for x, y in landmark_entry["points"][:5]]

    poly_points, _segments, cumulative, total_length = polyline_arrays(points)
    if total_length < 1e-6:
        raise ValueError(f"Could not build a dorsal axis for {record.image_path}")

    belt_breadth_px = float(belt_breadth_px_override) if belt_breadth_px_override is not None else max(80.0, total_length * float(belt_breadth_fraction))

    belt_bgr, belt_mask, top_edge, bottom_edge = build_belt(
        working,
        points,
        belt_width,
        belt_height,
        belt_breadth_px,
        inner_margin,
    )

    dark_response, dark_binary = create_dark_spot_map(belt_bgr, belt_mask)
    masked_preview = create_pattern_enhanced_preview(belt_bgr, belt_mask, dark_response)

    blurred_map = cv2.GaussianBlur(dark_response, (0, 0), sigmaX=3.0, sigmaY=3.0)
    masked_map = blurred_map.copy()
    masked_map[belt_mask == 0] = 0

    detector = cv2.AKAZE_create(threshold=0.0009)
    keypoints, descriptors = detector.detectAndCompute(masked_map, mask=belt_mask)
    if descriptors is None or len(keypoints) < 10:
        orb = cv2.ORB_create(nfeatures=1600, fastThreshold=10)
        keypoints, descriptors = orb.detectAndCompute(masked_map, mask=belt_mask)
    keypoints_xy = np.array([kp.pt for kp in keypoints], dtype=np.float32) if keypoints else np.empty((0, 2), dtype=np.float32)

    thumb_map = cv2.resize(masked_map, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
    thumb_mask = cv2.resize(belt_mask, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)
    thumb_binary = cv2.resize(dark_binary, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)

    hsv = cv2.cvtColor(masked_preview, cv2.COLOR_BGR2HSV)
    color_hist = cv2.calcHist([hsv], [0, 1], belt_mask, [16, 16], [0, 180, 0, 256])
    color_hist = cv2.normalize(color_hist, color_hist).flatten()

    preview_bgr, _, _ = resize_long_side(masked_preview, preview_side)
    belt_path = output_dirs["belt"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_belt.png"
    overlay_path = output_dirs["overlay"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_overlay.png"
    spot_path = output_dirs["spots"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_spots.png"
    belt_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(belt_path), preview_bgr)
    cv2.imwrite(str(overlay_path), draw_overlay(working, points, top_edge, bottom_edge))
    cv2.imwrite(str(spot_path), make_spot_outline_preview_bgr(dark_binary, belt_mask))

    dark_fraction = float(np.count_nonzero(dark_binary)) / float(max(1, dark_binary.size))
    quality_flags: list[str] = []
    if len(keypoints_xy) < 10:
        quality_flags.append("warn:few_features")
    if dark_fraction < 0.02:
        quality_flags.append("warn:weak_spot_pattern")
    quality_flag = ";".join(quality_flags) if quality_flags else "ok"

    return SpotFeature(
        image_path=record.image_path,
        relative_path=record.relative_path,
        specimen_id=record.specimen_id,
        split=record.split,
        preview_bgr=preview_bgr,
        spot_map=masked_map,
        spot_binary=dark_binary,
        thumb_map=thumb_map,
        thumb_mask=thumb_mask,
        thumb_binary=thumb_binary,
        keypoints_xy=keypoints_xy,
        descriptors=descriptors,
        color_hist=color_hist,
        green_leak_fraction=0.0,
        quality_flag=quality_flag,
        preview_path=belt_path,
        spot_path=spot_path,
    )


def local_similarity_map(
    query_map: np.ndarray,
    candidate_map: np.ndarray,
    query_mask: np.ndarray,
    candidate_mask: np.ndarray,
    window_size: int,
) -> np.ndarray:
    overlap = ((query_mask > 0) & (candidate_mask > 0)).astype(np.float32)
    if np.count_nonzero(overlap) < 64:
        return np.zeros_like(query_map, dtype=np.float32)
    q = query_map.astype(np.float32)
    c = candidate_map.astype(np.float32)
    q_values = q[query_mask > 0]
    c_values = c[candidate_mask > 0]
    if q_values.size == 0 or c_values.size == 0:
        return np.zeros_like(query_map, dtype=np.float32)
    q = (q - float(q_values.min())) / max(1e-6, float(q_values.max() - q_values.min()))
    c = (c - float(c_values.min())) / max(1e-6, float(c_values.max() - c_values.min()))
    similarity = (1.0 - np.abs(q - c)) * overlap
    kernel = (window_size, window_size)
    overlap_sum = cv2.boxFilter(overlap, ddepth=-1, ksize=kernel, normalize=False)
    sim_sum = cv2.boxFilter(similarity, ddepth=-1, ksize=kernel, normalize=False)
    return np.divide(sim_sum, overlap_sum + 1e-6, out=np.zeros_like(sim_sum), where=overlap_sum > 1.0)


def local_information_map(query_map: np.ndarray, query_mask: np.ndarray, window_size: int) -> np.ndarray:
    valid = (query_mask > 0).astype(np.float32)
    if np.count_nonzero(valid) < 64:
        return np.zeros_like(query_map, dtype=np.float32)
    q = query_map.astype(np.float32)
    values = q[query_mask > 0]
    if values.size == 0:
        return np.zeros_like(query_map, dtype=np.float32)
    q = (q - float(values.min())) / max(1e-6, float(values.max() - values.min()))
    kernel = (window_size, window_size)
    valid_sum = cv2.boxFilter(valid, ddepth=-1, ksize=kernel, normalize=False)
    mean = np.divide(
        cv2.boxFilter(q * valid, ddepth=-1, ksize=kernel, normalize=False),
        valid_sum + 1e-6,
        out=np.zeros_like(q),
        where=valid_sum > 1.0,
    )
    mean_sq = np.divide(
        cv2.boxFilter((q * q) * valid, ddepth=-1, ksize=kernel, normalize=False),
        valid_sum + 1e-6,
        out=np.zeros_like(q),
        where=valid_sum > 1.0,
    )
    variance = np.maximum(0.0, mean_sq - (mean * mean))
    if float(variance.max()) > 1e-6:
        variance /= float(variance.max())
    return variance


def find_characteristic_regions(
    query: SpotFeature,
    best_match: SpotFeature,
    second_match: SpotFeature | None,
    count: int = 3,
    window_size: int = 29,
) -> list[tuple[int, int, int, int]]:
    best_similarity = local_similarity_map(query.thumb_map, best_match.thumb_map, query.thumb_mask, best_match.thumb_mask, window_size)
    if second_match is not None:
        second_similarity = local_similarity_map(query.thumb_map, second_match.thumb_map, query.thumb_mask, second_match.thumb_mask, window_size)
        discriminative = best_similarity - (0.92 * second_similarity)
    else:
        discriminative = best_similarity
    info_map = local_information_map(query.thumb_map, query.thumb_mask, window_size)
    score_map = discriminative * (0.35 + 0.65 * info_map)
    valid = (query.thumb_mask > 0).astype(np.float32)
    overlap_sum = cv2.boxFilter(valid, ddepth=-1, ksize=(window_size, window_size), normalize=False)
    min_support = float(window_size * window_size) * 0.45
    score_map = np.where(overlap_sum >= min_support, score_map, -1.0)

    boxes: list[tuple[int, int, int, int]] = []
    suppression = score_map.copy()
    radius = window_size // 2
    for _ in range(count):
        flat_index = int(np.argmax(suppression))
        best_value = float(suppression.flat[flat_index])
        if best_value <= 0.01:
            break
        y_center, x_center = np.unravel_index(flat_index, suppression.shape)
        x0 = max(0, x_center - radius)
        y0 = max(0, y_center - radius)
        x1 = min(suppression.shape[1], x_center + radius + 1)
        y1 = min(suppression.shape[0], y_center + radius + 1)
        boxes.append((x0, y0, x1, y1))
        pad = int(radius * 1.4)
        sx0 = max(0, x_center - pad)
        sy0 = max(0, y_center - pad)
        sx1 = min(suppression.shape[1], x_center + pad + 1)
        sy1 = min(suppression.shape[0], y_center + pad + 1)
        suppression[sy0:sy1, sx0:sx1] = -1.0
    return boxes


def draw_boxes_on_image(
    image: Image.Image,
    boxes: list[tuple[int, int, int, int]],
    color: tuple[int, int, int],
    reference_shape: tuple[int, int],
) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    thumb_h, thumb_w = reference_shape
    for idx, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        px0 = int(round((x0 / float(thumb_w)) * width))
        py0 = int(round((y0 / float(thumb_h)) * height))
        px1 = int(round((x1 / float(thumb_w)) * width))
        py1 = int(round((y1 / float(thumb_h)) * height))
        draw.rectangle((px0, py0, px1, py1), outline=color, width=3)
        draw.rectangle((px0, py0, px0 + 22, py0 + 18), fill=color)
        draw.text((px0 + 5, py0 + 2), str(idx), fill=(255, 255, 255))
    return canvas


def extract_box_crops(
    image: Image.Image,
    boxes: list[tuple[int, int, int, int]],
    reference_shape: tuple[int, int],
    out_size: tuple[int, int] = (120, 88),
    pad_fraction: float = 0.45,
) -> list[Image.Image]:
    width, height = image.size
    ref_h, ref_w = reference_shape
    crops: list[Image.Image] = []
    for x0, y0, x1, y1 in boxes:
        px0 = (x0 / float(ref_w)) * width
        py0 = (y0 / float(ref_h)) * height
        px1 = (x1 / float(ref_w)) * width
        py1 = (y1 / float(ref_h)) * height
        box_w = max(8.0, px1 - px0)
        box_h = max(8.0, py1 - py0)
        pad_x = box_w * pad_fraction
        pad_y = box_h * pad_fraction
        cx = (px0 + px1) * 0.5
        cy = (py0 + py1) * 0.5
        crop_x0 = int(round(max(0.0, cx - (box_w * 0.5) - pad_x)))
        crop_y0 = int(round(max(0.0, cy - (box_h * 0.5) - pad_y)))
        crop_x1 = int(round(min(float(width), cx + (box_w * 0.5) + pad_x)))
        crop_y1 = int(round(min(float(height), cy + (box_h * 0.5) + pad_y)))
        crop = image.crop((crop_x0, crop_y0, crop_x1, crop_y1)).resize(out_size)
        crops.append(crop)
    return crops


def fit_image_to_box(image: Image.Image, box_size: tuple[int, int], background: tuple[int, int, int] = (245, 245, 245)) -> Image.Image:
    box_w, box_h = box_size
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", box_size, color=background)
    scale = min(box_w / float(src_w), box_h / float(src_h))
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = image.resize((new_w, new_h))
    canvas = Image.new("RGB", box_size, color=background)
    off_x = (box_w - new_w) // 2
    off_y = (box_h - new_h) // 2
    canvas.paste(resized, (off_x, off_y))
    return canvas


def compare_features(query: SpotFeature, candidate: SpotFeature) -> tuple[float, dict[str, float]]:
    compatible_descriptors = (
        query.descriptors is not None
        and candidate.descriptors is not None
        and query.descriptors.dtype == candidate.descriptors.dtype
        and len(query.descriptors.shape) == 2
        and len(candidate.descriptors.shape) == 2
        and query.descriptors.shape[1] == candidate.descriptors.shape[1]
    )
    if compatible_descriptors:
        good_matches, inlier_count, geom_score = geometric_match(query, candidate)
    else:
        good_matches, inlier_count, geom_score = 0, 0, 0.0
    map_score = (masked_corrcoef(query.thumb_map, candidate.thumb_map, query.thumb_mask, candidate.thumb_mask) + 1.0) / 2.0
    hist_score = (cv2.compareHist(query.color_hist.astype(np.float32), candidate.color_hist.astype(np.float32), cv2.HISTCMP_CORREL) + 1.0) / 2.0
    total_score = float((0.72 * geom_score) + (0.22 * map_score) + (0.06 * hist_score))
    if inlier_count == 0:
        total_score *= 0.75
    elif inlier_count <= 2:
        total_score *= 0.9
    details = {
        "good_matches": float(good_matches),
        "inlier_count": float(inlier_count),
        "geom_score": float(geom_score),
        "map_score": float(map_score),
        "hist_score": float(hist_score),
        "descriptor_compatible": 1.0 if compatible_descriptors else 0.0,
    }
    return total_score, details


def aggregate_specimen_consensus(
    scored_candidates: list[tuple[float, SpotFeature, dict[str, float]]],
    top_k: int,
) -> tuple[float, SpotFeature, dict[str, float], int, str]:
    ranked = sorted(scored_candidates, key=lambda item: item[0], reverse=True)
    if not ranked:
        raise ValueError("Cannot aggregate an empty specimen score list.")

    consensus_k = max(1, min(int(top_k), len(ranked)))
    top_entries = ranked[:consensus_k]
    consensus_score = float(np.mean([entry[0] for entry in top_entries]))

    representative_score, representative_feature, representative_details = ranked[0]
    consensus_files = "|".join(entry[1].image_path.name for entry in top_entries)
    representative_details = dict(representative_details)
    representative_details["representative_score"] = float(representative_score)
    representative_details["consensus_score"] = consensus_score
    representative_details["consensus_support_count"] = float(consensus_k)
    return consensus_score, representative_feature, representative_details, consensus_k, consensus_files


def decide_prediction_consensus(
    ranked: list[tuple[str, tuple[float, SpotFeature, dict[str, float], int, str]]],
    allow_new_specimen: bool,
    new_specimen_threshold: float,
    new_specimen_margin: float,
) -> tuple[str, str, float, str, float, SpotFeature, dict[str, float], bool]:
    predicted_specimen, (best_score, best_match, best_details, _support_count, _support_files) = ranked[0]
    if len(ranked) > 1:
        second_specimen, (second_score, _, _, _, _) = ranked[1]
    else:
        second_specimen, second_score = "", 0.0
    score_margin = best_score - second_score
    if not allow_new_specimen:
        return predicted_specimen, predicted_specimen, best_score, second_specimen, second_score, best_match, best_details, False
    weak_match = best_score < new_specimen_threshold
    ambiguous_weak_match = score_margin < new_specimen_margin and best_score < (new_specimen_threshold + 0.10)
    if weak_match or ambiguous_weak_match:
        return "NEW_SPECIMEN", predicted_specimen, best_score, second_specimen, second_score, best_match, best_details, True
    return predicted_specimen, predicted_specimen, best_score, second_specimen, second_score, best_match, best_details, False


def make_qc_panel(
    query: SpotFeature,
    best_match: SpotFeature,
    second_match: SpotFeature | None,
    query_overlay_path: Path,
    best_overlay_path: Path,
    panel_path: Path,
    predicted_specimen: str,
    best_score: float,
    second_specimen: str,
    second_score: float,
    is_correct: bool,
    decision_reason: str,
) -> None:
    characteristic_boxes = find_characteristic_regions(query, best_match, second_match)
    canvas = Image.new("RGB", (920, 1105), color=(245, 245, 245))
    ref_shape = query.thumb_map.shape[:2]
    query_overlay = fit_image_to_box(Image.open(query_overlay_path).convert("RGB"), (440, 260))
    best_overlay = fit_image_to_box(Image.open(best_overlay_path).convert("RGB"), (440, 260))

    query_belt_plain = pil_from_bgr(query.preview_bgr)
    best_belt_plain = pil_from_bgr(best_match.preview_bgr)
    query_spots_plain = pil_from_bgr(make_spot_outline_preview_bgr(query.spot_binary, None))
    best_spots_plain = pil_from_bgr(make_spot_outline_preview_bgr(best_match.spot_binary, None))

    query_belt_marked = draw_boxes_on_image(query_belt_plain, characteristic_boxes, (210, 55, 55), ref_shape)
    best_belt_marked = draw_boxes_on_image(best_belt_plain, characteristic_boxes, (210, 55, 55), ref_shape)
    query_spots_marked = draw_boxes_on_image(query_spots_plain, characteristic_boxes, (210, 55, 55), ref_shape)
    best_spots_marked = draw_boxes_on_image(best_spots_plain, characteristic_boxes, (210, 55, 55), ref_shape)

    query_belt = fit_image_to_box(query_belt_marked, (440, 260))
    best_belt = fit_image_to_box(best_belt_marked, (440, 260))
    query_spots = fit_image_to_box(query_spots_marked, (440, 260))
    best_spots = fit_image_to_box(best_spots_marked, (440, 260))

    query_crops = extract_box_crops(query_belt_plain, characteristic_boxes, ref_shape)
    best_crops = extract_box_crops(best_belt_plain, characteristic_boxes, ref_shape)

    canvas.paste(query_overlay, (20, 40))
    canvas.paste(best_overlay, (460, 40))
    canvas.paste(query_belt, (20, 340))
    canvas.paste(best_belt, (460, 340))
    canvas.paste(query_spots, (20, 640))
    canvas.paste(best_spots, (460, 640))

    add_label(canvas, f"Query overlay: {query.image_path.name}", 20, 12, 440)
    add_label(canvas, f"Best matched gallery: {best_match.image_path.name}", 460, 12, 440)
    add_label(canvas, "Query curved belt", 20, 312, 440)
    add_label(canvas, "Best matched curved belt", 460, 312, 440)
    add_label(canvas, "Query dark-spot outlines (true aspect ratio)", 20, 612, 440)
    add_label(canvas, "Best match dark-spot outlines", 460, 612, 440)
    add_label(canvas, "Characteristic belt crops: query (left in pair) vs best match (right in pair)", 20, 872, 880)

    crop_y = 905
    for idx, (query_crop, best_crop) in enumerate(zip(query_crops, best_crops), start=1):
        x_base = 20 + ((idx - 1) * 290)
        canvas.paste(query_crop, (x_base, crop_y))
        canvas.paste(best_crop, (x_base + 130, crop_y))
        add_label(canvas, f"Q{idx}", x_base, crop_y - 22, 120)
        add_label(canvas, f"B{idx}", x_base + 130, crop_y - 22, 120)

    verdict = "correct" if is_correct else "mismatch"
    add_label(
        canvas,
        f"true={query.specimen_id} predicted={predicted_specimen} best={best_score:.3f} second={second_specimen}:{second_score:.3f} {verdict} {decision_reason}",
        20,
        1068,
        880,
    )
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(panel_path)


def summarize_predictions(
    predictions: pd.DataFrame,
    output_dir: Path,
    project_dir: Path,
    args: argparse.Namespace,
    n_manifest_records: int,
    n_gallery_images: int,
    n_query_images: int,
) -> dict[str, object]:
    overall_accuracy = float(predictions["correct"].mean()) if len(predictions) else 0.0
    per_specimen = []
    for specimen_id, group in predictions.groupby("true_specimen"):
        per_specimen.append(
            {
                "true_specimen": str(specimen_id),
                "count": int(len(group)),
                "correct_count": int(group["correct"].sum()),
                "accuracy": float(group["correct"].mean()) if len(group) else 0.0,
            }
        )
    return {
        "mode": "five_landmark_axis_belt_matcher",
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "landmarks_path": str(Path(args.landmarks) if args.landmarks else (project_dir / "config" / "axis_belt_landmarks.csv")),
        "max_side": args.max_side,
        "preview_side": args.preview_side,
        "thumb_size": args.thumb_size,
        "belt_width": args.belt_width,
        "belt_height": args.belt_height,
        "belt_breadth_fraction": args.belt_breadth_fraction,
        "belt_breadth_px": args.belt_breadth_px,
        "inner_margin": args.inner_margin,
        "max_specimens": args.max_specimens,
        "gallery_per_specimen": args.gallery_per_specimen,
        "gallery_sampling": args.gallery_sampling,
        "query_per_specimen": args.query_per_specimen,
        "n_manifest_records": n_manifest_records,
        "n_gallery_images": n_gallery_images,
        "n_query_images": n_query_images,
        "overall_accuracy": overall_accuracy,
        "allow_new_specimen": bool(args.allow_new_specimen),
        "new_specimen_threshold": float(args.new_specimen_threshold),
        "new_specimen_margin": float(args.new_specimen_margin),
        "consensus_top_k": int(args.consensus_top_k),
        "n_new_specimen_predictions": int((predictions["predicted_specimen"] == "NEW_SPECIMEN").sum()) if len(predictions) else 0,
        "per_specimen": per_specimen,
    }


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    source_dir = Path(args.source_images) if args.source_images else None
    landmarks_path = Path(args.landmarks) if args.landmarks else project_dir / "config" / "axis_belt_landmarks.csv"
    output_dir = Path(args.output) if args.output else project_dir / "outputs" / "axis_belt_run"
    output_dirs = ensure_dirs(output_dir)

    records = infer_records(project_dir, Path(args.manifest) if args.manifest else None, source_dir)
    gallery_records, query_records = split_records(
        records,
        args.max_gallery,
        args.max_query,
        args.max_specimens,
        args.gallery_per_specimen,
        args.gallery_sampling,
        args.query_per_specimen,
    )
    landmark_rows = load_landmarks(landmarks_path)

    gallery_features: list[SpotFeature] = []
    gallery_overlay_by_relpath: dict[str, Path] = {}
    for specimen_id, specimen_records in sorted(gallery_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 5:
                continue
            feature = preprocess_belt_feature(
                record,
                landmark_entry,
                output_dirs,
                args.max_side,
                args.preview_side,
                args.thumb_size,
                args.belt_width,
                args.belt_height,
                args.belt_breadth_fraction,
                args.belt_breadth_px,
                args.inner_margin,
            )
            gallery_features.append(feature)
            gallery_overlay_by_relpath[record.relative_path] = output_dirs["overlay"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_overlay.png"

    query_features: list[SpotFeature] = []
    query_overlay_by_relpath: dict[str, Path] = {}
    for specimen_id, specimen_records in sorted(query_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 5:
                continue
            feature = preprocess_belt_feature(
                record,
                landmark_entry,
                output_dirs,
                args.max_side,
                args.preview_side,
                args.thumb_size,
                args.belt_width,
                args.belt_height,
                args.belt_breadth_fraction,
                args.belt_breadth_px,
                args.inner_margin,
            )
            query_features.append(feature)
            query_overlay_by_relpath[record.relative_path] = output_dirs["overlay"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_overlay.png"

    if not gallery_features:
        raise ValueError("No gallery images with 5-point landmarks were available for matching.")
    if not query_features:
        raise ValueError("No query images with 5-point landmarks were available for matching.")

    gallery_specimens = {feature.specimen_id for feature in gallery_features}
    rows: list[dict[str, object]] = []
    for query in query_features:
        specimen_scores: dict[str, list[tuple[float, SpotFeature, dict[str, float]]]] = {}
        for candidate in gallery_features:
            score, details = compare_features(query, candidate)
            specimen_scores.setdefault(candidate.specimen_id, []).append((score, candidate, details))
        specimen_consensus: dict[str, tuple[float, SpotFeature, dict[str, float], int, str]] = {}
        for specimen_id, scored_candidates in specimen_scores.items():
            specimen_consensus[specimen_id] = aggregate_specimen_consensus(scored_candidates, args.consensus_top_k)
        ranked = sorted(specimen_consensus.items(), key=lambda item: item[1][0], reverse=True)
        predicted_label, best_gallery_specimen, best_score, second_specimen, second_score, best_match, best_details, is_new_specimen = decide_prediction_consensus(
            ranked,
            allow_new_specimen=bool(args.allow_new_specimen),
            new_specimen_threshold=float(args.new_specimen_threshold),
            new_specimen_margin=float(args.new_specimen_margin),
        )
        second_match = ranked[1][1][1] if len(ranked) > 1 else None
        score_margin = best_score - second_score
        known_in_gallery = query.specimen_id in gallery_specimens
        decision_reason = "new_specimen_rule" if is_new_specimen else ("matched_consensus" if len(ranked) > 1 else "single_gallery_specimen")
        is_correct = predicted_label == query.specimen_id if known_in_gallery else predicted_label == "NEW_SPECIMEN"
        qc_path = output_dirs["qc"] / f"{query.image_path.stem}_qc.png"
        make_qc_panel(
            query,
            best_match,
            second_match,
            query_overlay_by_relpath[query.relative_path],
            gallery_overlay_by_relpath[best_match.relative_path],
            qc_path,
            predicted_label,
            best_score,
            second_specimen,
            second_score,
            is_correct,
            decision_reason,
        )

        rows.append(
            {
                "query_file": query.image_path.name,
                "true_specimen": query.specimen_id,
                "known_in_gallery": known_in_gallery,
                "predicted_specimen": predicted_label,
                "best_gallery_specimen": best_gallery_specimen,
                "new_specimen_flag": is_new_specimen,
                "correct": is_correct,
                "best_score": best_score,
                "second_specimen": second_specimen,
                "second_score": second_score,
                "score_margin": score_margin,
                "decision_reason": decision_reason,
                "best_match_file": best_match.image_path.name,
                "consensus_top_k": int(args.consensus_top_k),
                "consensus_support_count": int(best_details.get("consensus_support_count", 1.0)),
                "consensus_score": float(best_details.get("consensus_score", best_score)),
                "representative_score": float(best_details.get("representative_score", best_score)),
                "consensus_gallery_files": specimen_consensus[best_gallery_specimen][4],
                "good_matches": int(best_details["good_matches"]),
                "inlier_count": int(best_details["inlier_count"]),
                "geom_score": float(best_details["geom_score"]),
                "map_score": float(best_details["map_score"]),
                "hist_score": float(best_details["hist_score"]),
                "quality_flag": query.quality_flag,
                "overlay_file": str(query_overlay_by_relpath[query.relative_path]),
                "belt_file": str(query.preview_path),
                "spot_file": str(query.spot_path),
                "qc_file": str(qc_path),
            }
        )

    predictions = pd.DataFrame(rows)
    predictions_path = output_dir / "predictions.csv"
    summary_path = output_dir / "summary.json"
    predictions.to_csv(predictions_path, index=False)

    summary = summarize_predictions(
        predictions,
        output_dir,
        project_dir,
        args,
        n_manifest_records=len(records),
        n_gallery_images=sum(len(items) for items in gallery_records.values()),
        n_query_images=sum(len(items) for items in query_records.values()),
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved predictions to: {predictions_path}")


if __name__ == "__main__":
    main()
