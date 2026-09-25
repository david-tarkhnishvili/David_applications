from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd
from PIL import Image

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from darevskia_spot_matcher import (  # noqa: E402
    ManifestRecord,
    SpotFeature,
    add_label,
    create_dark_spot_map,
    decide_prediction,
    geometric_match,
    infer_records,
    masked_corrcoef,
    pil_from_bgr,
    resize_long_side,
    split_records,
    make_spot_preview_bgr,
)


@dataclass
class TripointFeature:
    image_path: Path
    relative_path: str
    specimen_id: str
    split: str
    overlay_path: Path
    windows: dict[str, SpotFeature]
    quality_flag: str


WINDOW_NAMES = ("neck", "middle", "hind")
WINDOW_WEIGHTS = {"neck": 1.0, "middle": 1.15, "hind": 1.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="3-landmark, 3-window dorsal matcher: derive standardized body-aligned windows from neck/middle/hindbody landmarks and combine their spot-matching evidence."
    )
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--landmarks", help="CSV containing 3-point annotations. Defaults to project_dir/config/tripoint_landmarks.csv.")
    parser.add_argument("--output", help="Output folder. Defaults to project_dir/outputs/tripoint_spot_run.")
    parser.add_argument("--max-side", type=int, default=2200, help="Resize the longest image side to at most this value before extracting windows.")
    parser.add_argument("--preview-side", type=int, default=900, help="Save window previews with this longest-side cap.")
    parser.add_argument("--thumb-size", type=int, default=256, help="Low-resolution size used for spot-map correlation.")
    parser.add_argument("--window-width", type=int, default=360, help="Width of each standardized window in pixels.")
    parser.add_argument("--window-height", type=int, default=520, help="Height of each standardized window in pixels.")
    parser.add_argument("--window-length-fraction", type=float, default=0.30, help="Window height as a fraction of the neck-to-hindbody distance.")
    parser.add_argument("--window-width-fraction", type=float, default=0.18, help="Window width as a fraction of the neck-to-hindbody distance.")
    parser.add_argument("--inner-margin", type=float, default=0.03, help="Fraction to trim from each side of the standardized window to avoid boundary noise.")
    parser.add_argument("--max-specimens", type=int, default=None, help="Optional cap on the number of specimens included, in manifest/specimen order.")
    parser.add_argument("--gallery-per-specimen", type=int, default=None, help="Optional cap on gallery images per specimen.")
    parser.add_argument("--gallery-sampling", choices=("first", "spaced", "last"), default="last", help="How to sample gallery images when gallery_per_specimen is smaller than the available images.")
    parser.add_argument("--query-per-specimen", type=int, default=None, help="Optional cap on query images per specimen.")
    parser.add_argument("--max-gallery", type=int, default=None, help="Optional cap on gallery image count after per-specimen sampling.")
    parser.add_argument("--max-query", type=int, default=None, help="Optional cap on query image count after per-specimen sampling.")
    parser.add_argument("--allow-new-specimen", action="store_true", help="Allow rejection of a weak match as NEW_SPECIMEN.")
    parser.add_argument("--new-specimen-threshold", type=float, default=0.20, help="Reject as new if the best score falls below this threshold.")
    parser.add_argument("--new-specimen-margin", type=float, default=0.035, help="Reject as new if the best-vs-second score gap is below this margin and the best score is still weak.")
    return parser.parse_args()


def read_image_bgr_raw(image_path: Path) -> np.ndarray:
    pil_image = Image.open(image_path).convert("RGB")
    rgb = np.asarray(pil_image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def ensure_dirs(base_output: Path) -> dict[str, Path]:
    mapping = {
        "overlay": base_output / "overlay",
        "windows": base_output / "windows",
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
            if len(points) < 3:
                continue
            rows[relative_path] = {
                "relative_path": relative_path,
                "specimen_id": str(row["specimen_id"]),
                "split": str(row["split"]).lower(),
                "image_width": int(float(row.get("image_width") or 0)),
                "image_height": int(float(row.get("image_height") or 0)),
                "point_count": point_count,
                "points": points[:3],
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


def derive_window_specs(
    points: list[tuple[float, float]],
    length_fraction: float,
    width_fraction: float,
) -> dict[str, dict[str, np.ndarray | float]]:
    neck = np.array(points[0], dtype=np.float32)
    middle = np.array(points[1], dtype=np.float32)
    hind = np.array(points[2], dtype=np.float32)

    body_axis = hind - neck
    body_length = float(np.linalg.norm(body_axis))
    overall_dir = safe_normalize(body_axis, np.array([0.0, 1.0], dtype=np.float32))

    neck_dir = safe_normalize(middle - neck, overall_dir)
    middle_dir = overall_dir
    hind_dir = safe_normalize(hind - middle, overall_dir)

    window_height = max(120.0, body_length * float(length_fraction))
    window_width = max(80.0, body_length * float(width_fraction))

    return {
        "neck": {"center": neck, "direction": neck_dir, "height": window_height, "width": window_width},
        "middle": {"center": middle, "direction": middle_dir, "height": window_height, "width": window_width},
        "hind": {"center": hind, "direction": hind_dir, "height": window_height, "width": window_width},
    }


def rectangle_corners(center: np.ndarray, direction: np.ndarray, rect_height: float, rect_width: float) -> np.ndarray:
    half_h = rect_height / 2.0
    half_w = rect_width / 2.0
    normal = rotate_ccw_90(direction)
    top_left = center - (normal * half_w) - (direction * half_h)
    top_right = center + (normal * half_w) - (direction * half_h)
    bottom_right = center + (normal * half_w) + (direction * half_h)
    bottom_left = center - (normal * half_w) + (direction * half_h)
    return np.vstack([top_left, top_right, bottom_right, bottom_left]).astype(np.float32)


def warp_window(
    image_bgr: np.ndarray,
    corners: np.ndarray,
    output_width: int,
    output_height: int,
    inner_margin: float,
) -> tuple[np.ndarray, np.ndarray]:
    dst = np.array(
        [
            [0.0, 0.0],
            [float(output_width - 1), 0.0],
            [float(output_width - 1), float(output_height - 1)],
            [0.0, float(output_height - 1)],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(
        image_bgr,
        matrix,
        (output_width, output_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    margin_x = max(0, int(round(output_width * inner_margin)))
    margin_y = max(0, int(round(output_height * inner_margin)))
    x0 = min(margin_x, max(0, output_width // 6))
    y0 = min(margin_y, max(0, output_height // 6))
    x1 = max(x0 + 8, output_width - x0)
    y1 = max(y0 + 8, output_height - y0)
    trimmed = warped[y0:y1, x0:x1].copy()
    mask = np.full(trimmed.shape[:2], 255, dtype=np.uint8)
    return trimmed, mask


def draw_overlay(image_bgr: np.ndarray, specs: dict[str, dict[str, np.ndarray | float]]) -> np.ndarray:
    overlay = image_bgr.copy()
    colors = {"neck": (255, 120, 0), "middle": (0, 220, 255), "hind": (120, 255, 80)}
    labels = {"neck": "N", "middle": "M", "hind": "H"}
    for window_name in WINDOW_NAMES:
        spec = specs[window_name]
        center = np.asarray(spec["center"], dtype=np.float32)
        direction = np.asarray(spec["direction"], dtype=np.float32)
        corners = rectangle_corners(center, direction, float(spec["height"]), float(spec["width"]))
        color = colors[window_name]
        cv2.polylines(overlay, [corners.astype(np.int32).reshape((-1, 1, 2))], True, color, 4, cv2.LINE_AA)
        cv2.circle(overlay, (int(round(center[0])), int(round(center[1]))), 8, color, -1, lineType=cv2.LINE_AA)
        cv2.putText(
            overlay,
            labels[window_name],
            (int(round(center[0])) + 10, int(round(center[1])) - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return overlay


def create_window_feature(
    record: ManifestRecord,
    split: str,
    specimen_id: str,
    window_name: str,
    window_bgr: np.ndarray,
    window_mask: np.ndarray,
    output_dirs: dict[str, Path],
    preview_side: int,
    thumb_size: int,
) -> SpotFeature:
    dark_response, dark_binary = create_dark_spot_map(window_bgr, window_mask)

    masked_preview = window_bgr.copy()
    masked_preview[window_mask == 0] = (127, 127, 127)

    blurred_map = cv2.GaussianBlur(dark_response, (0, 0), sigmaX=3.0, sigmaY=3.0)
    masked_map = blurred_map.copy()
    masked_map[window_mask == 0] = 0

    detector = cv2.AKAZE_create(threshold=0.0009)
    keypoints, descriptors = detector.detectAndCompute(masked_map, mask=window_mask)
    if descriptors is None or len(keypoints) < 10:
        orb = cv2.ORB_create(nfeatures=1200, fastThreshold=10)
        keypoints, descriptors = orb.detectAndCompute(masked_map, mask=window_mask)
    keypoints_xy = np.array([kp.pt for kp in keypoints], dtype=np.float32) if keypoints else np.empty((0, 2), dtype=np.float32)

    thumb_map = cv2.resize(masked_map, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
    thumb_mask = cv2.resize(window_mask, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)

    hsv = cv2.cvtColor(masked_preview, cv2.COLOR_BGR2HSV)
    color_hist = cv2.calcHist([hsv], [0, 1], window_mask, [16, 16], [0, 180, 0, 256])
    color_hist = cv2.normalize(color_hist, color_hist).flatten()

    preview_bgr, _, _ = resize_long_side(masked_preview, preview_side)
    window_path = output_dirs["windows"] / split / f"specimen_{specimen_id}" / f"{record.image_path.stem}_{window_name}.png"
    spot_path = output_dirs["spots"] / split / f"specimen_{specimen_id}" / f"{record.image_path.stem}_{window_name}_spots.png"
    window_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(window_path), preview_bgr)
    cv2.imwrite(str(spot_path), make_spot_preview_bgr(masked_map, window_mask))

    dark_fraction = float(np.count_nonzero(dark_binary)) / float(max(1, dark_binary.size))
    quality_flags: list[str] = []
    if len(keypoints_xy) < 10:
        quality_flags.append("warn:few_features")
    if dark_fraction < 0.02:
        quality_flags.append("warn:weak_spot_pattern")
    quality_flag = ";".join(quality_flags) if quality_flags else "ok"

    return SpotFeature(
        image_path=record.image_path,
        relative_path=f"{record.relative_path}::{window_name}",
        specimen_id=record.specimen_id,
        split=record.split,
        preview_bgr=preview_bgr,
        spot_map=masked_map,
        thumb_map=thumb_map,
        thumb_mask=thumb_mask,
        keypoints_xy=keypoints_xy,
        descriptors=descriptors,
        color_hist=color_hist,
        green_leak_fraction=0.0,
        quality_flag=quality_flag,
        preview_path=window_path,
        spot_path=spot_path,
    )


def preprocess_tripoint_feature(
    record: ManifestRecord,
    landmark_entry: dict[str, object],
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    window_width_px: int,
    window_height_px: int,
    window_length_fraction: float,
    window_width_fraction: float,
    inner_margin: float,
) -> TripointFeature:
    image_bgr = read_image_bgr_raw(record.image_path)
    working, _, scale = resize_long_side(image_bgr, max_side)
    scaled_points = [(float(x) * scale, float(y) * scale) for x, y in landmark_entry["points"][:3]]
    specs = derive_window_specs(scaled_points, window_length_fraction, window_width_fraction)

    overlay_path = output_dirs["overlay"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_overlay.png"
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(overlay_path), draw_overlay(working, specs))

    windows: dict[str, SpotFeature] = {}
    quality_flags: list[str] = []
    for window_name in WINDOW_NAMES:
        spec = specs[window_name]
        corners = rectangle_corners(
            np.asarray(spec["center"], dtype=np.float32),
            np.asarray(spec["direction"], dtype=np.float32),
            float(spec["height"]),
            float(spec["width"]),
        )
        window_bgr, window_mask = warp_window(
            working,
            corners,
            window_width_px,
            window_height_px,
            inner_margin,
        )
        feature = create_window_feature(
            record,
            record.split,
            record.specimen_id,
            window_name,
            window_bgr,
            window_mask,
            output_dirs,
            preview_side,
            thumb_size,
        )
        windows[window_name] = feature
        if feature.quality_flag != "ok":
            quality_flags.append(f"{window_name}:{feature.quality_flag}")

    quality_flag = ";".join(quality_flags) if quality_flags else "ok"
    return TripointFeature(
        image_path=record.image_path,
        relative_path=record.relative_path,
        specimen_id=record.specimen_id,
        split=record.split,
        overlay_path=overlay_path,
        windows=windows,
        quality_flag=quality_flag,
    )


def compare_window_features(query: SpotFeature, candidate: SpotFeature) -> tuple[float, dict[str, float]]:
    good_matches, inlier_count, geom_score = geometric_match(query, candidate)
    map_score = (masked_corrcoef(query.thumb_map, candidate.thumb_map, query.thumb_mask, candidate.thumb_mask) + 1.0) / 2.0
    hist_score = (cv2.compareHist(query.color_hist.astype(np.float32), candidate.color_hist.astype(np.float32), cv2.HISTCMP_CORREL) + 1.0) / 2.0
    total_score = float((0.70 * geom_score) + (0.25 * map_score) + (0.05 * hist_score))
    if inlier_count == 0:
        total_score *= 0.72
    elif inlier_count <= 2:
        total_score *= 0.88
    return total_score, {
        "good_matches": float(good_matches),
        "inlier_count": float(inlier_count),
        "geom_score": float(geom_score),
        "map_score": float(map_score),
        "hist_score": float(hist_score),
    }


def compare_tripoint_features(query: TripointFeature, candidate: TripointFeature) -> tuple[float, dict[str, float]]:
    weighted_scores = 0.0
    total_weight = 0.0
    window_inlier_hits = 0
    details: dict[str, float] = {
        "good_matches_total": 0.0,
        "inlier_count_total": 0.0,
    }

    for window_name in WINDOW_NAMES:
        weight = WINDOW_WEIGHTS[window_name]
        score, window_details = compare_window_features(query.windows[window_name], candidate.windows[window_name])
        weighted_scores += weight * score
        total_weight += weight
        details[f"{window_name}_score"] = score
        details[f"{window_name}_good_matches"] = window_details["good_matches"]
        details[f"{window_name}_inlier_count"] = window_details["inlier_count"]
        details[f"{window_name}_geom_score"] = window_details["geom_score"]
        details[f"{window_name}_map_score"] = window_details["map_score"]
        details[f"{window_name}_hist_score"] = window_details["hist_score"]
        details["good_matches_total"] += window_details["good_matches"]
        details["inlier_count_total"] += window_details["inlier_count"]
        if window_details["inlier_count"] > 0:
            window_inlier_hits += 1

    total_score = weighted_scores / max(1e-6, total_weight)
    if window_inlier_hits >= 2:
        total_score += 0.03
    elif window_inlier_hits == 0:
        total_score *= 0.82
    details["window_inlier_hits"] = float(window_inlier_hits)
    return float(total_score), details


def make_qc_panel(
    query: TripointFeature,
    best_match: TripointFeature,
    panel_path: Path,
    predicted_specimen: str,
    best_score: float,
    second_specimen: str,
    second_score: float,
    is_correct: bool,
    decision_reason: str,
) -> None:
    canvas = Image.new("RGB", (920, 1260), color=(245, 245, 245))

    query_overlay = Image.open(query.overlay_path).convert("RGB").resize((440, 260))
    best_overlay = Image.open(best_match.overlay_path).convert("RGB").resize((440, 260))
    canvas.paste(query_overlay, (20, 40))
    canvas.paste(best_overlay, (460, 40))
    add_label(canvas, f"Query overlay: {query.image_path.name}", 20, 12, 440)
    add_label(canvas, f"Best matched gallery: {best_match.image_path.name}", 460, 12, 440)

    row_y = 340
    for window_name in WINDOW_NAMES:
        query_img = pil_from_bgr(query.windows[window_name].preview_bgr).resize((200, 260))
        query_spots = pil_from_bgr(make_spot_preview_bgr(query.windows[window_name].thumb_map, query.windows[window_name].thumb_mask)).resize((200, 200))
        best_img = pil_from_bgr(best_match.windows[window_name].preview_bgr).resize((200, 260))
        best_spots = pil_from_bgr(make_spot_preview_bgr(best_match.windows[window_name].thumb_map, best_match.windows[window_name].thumb_mask)).resize((200, 200))

        canvas.paste(query_img, (20, row_y))
        canvas.paste(query_spots, (230, row_y + 30))
        canvas.paste(best_img, (470, row_y))
        canvas.paste(best_spots, (680, row_y + 30))
        add_label(canvas, f"{window_name} window", 20, row_y - 28, 200)
        add_label(canvas, f"{window_name} spot map", 230, row_y - 28, 200)
        add_label(canvas, f"{window_name} window", 470, row_y - 28, 200)
        add_label(canvas, f"{window_name} spot map", 680, row_y - 28, 200)
        row_y += 300

    verdict = "correct" if is_correct else "mismatch"
    add_label(
        canvas,
        f"true={query.specimen_id} predicted={predicted_specimen} best={best_score:.3f} second={second_specimen}:{second_score:.3f} {verdict} {decision_reason}",
        20,
        1220,
        880,
    )
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(panel_path)


def evaluate(
    query_features: list[TripointFeature],
    gallery_features: list[TripointFeature],
    output_dirs: dict[str, Path],
    allow_new_specimen: bool,
    new_specimen_threshold: float,
    new_specimen_margin: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    gallery_specimens = {feature.specimen_id for feature in gallery_features}

    for query in query_features:
        specimen_scores: dict[str, tuple[float, TripointFeature, dict[str, float]]] = {}
        for candidate in gallery_features:
            score, details = compare_tripoint_features(query, candidate)
            current = specimen_scores.get(candidate.specimen_id)
            if current is None or score > current[0]:
                specimen_scores[candidate.specimen_id] = (score, candidate, details)
        ranked = sorted(specimen_scores.items(), key=lambda item: item[1][0], reverse=True)
        predicted_label, best_gallery_specimen, best_score, second_specimen, second_score, best_match, best_details, is_new_specimen = decide_prediction(
            ranked,
            allow_new_specimen=allow_new_specimen,
            new_specimen_threshold=new_specimen_threshold,
            new_specimen_margin=new_specimen_margin,
        )
        score_margin = best_score - second_score
        known_in_gallery = query.specimen_id in gallery_specimens
        decision_reason = "new_specimen_rule" if is_new_specimen else ("matched" if len(ranked) > 1 else "single_gallery_specimen")
        is_correct = predicted_label == query.specimen_id if known_in_gallery else predicted_label == "NEW_SPECIMEN"
        qc_path = output_dirs["qc"] / f"{query.image_path.stem}_qc.png"
        make_qc_panel(query, best_match, qc_path, predicted_label, best_score, second_specimen, second_score, is_correct, decision_reason)

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
                "window_inlier_hits": int(best_details["window_inlier_hits"]),
                "good_matches_total": int(best_details["good_matches_total"]),
                "inlier_count_total": int(best_details["inlier_count_total"]),
                "neck_score": float(best_details["neck_score"]),
                "middle_score": float(best_details["middle_score"]),
                "hind_score": float(best_details["hind_score"]),
                "neck_inlier_count": int(best_details["neck_inlier_count"]),
                "middle_inlier_count": int(best_details["middle_inlier_count"]),
                "hind_inlier_count": int(best_details["hind_inlier_count"]),
                "quality_flag": query.quality_flag,
                "overlay_file": str(query.overlay_path),
                "qc_file": str(qc_path),
            }
        )
    return pd.DataFrame(rows)


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
        "mode": "tripoint_three_window_spot_matcher",
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "landmarks_path": str(Path(args.landmarks) if args.landmarks else (project_dir / "config" / "tripoint_landmarks.csv")),
        "max_side": args.max_side,
        "preview_side": args.preview_side,
        "thumb_size": args.thumb_size,
        "window_width": args.window_width,
        "window_height": args.window_height,
        "window_length_fraction": args.window_length_fraction,
        "window_width_fraction": args.window_width_fraction,
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
        "n_new_specimen_predictions": int((predictions["predicted_specimen"] == "NEW_SPECIMEN").sum()) if len(predictions) else 0,
        "per_specimen": per_specimen,
    }


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    source_dir = Path(args.source_images) if args.source_images else None
    landmarks_path = Path(args.landmarks) if args.landmarks else project_dir / "config" / "tripoint_landmarks.csv"
    output_dir = Path(args.output) if args.output else project_dir / "outputs" / "tripoint_spot_run"
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

    gallery_features: list[TripointFeature] = []
    for specimen_id, specimen_records in sorted(gallery_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 3:
                continue
            gallery_features.append(
                preprocess_tripoint_feature(
                    record,
                    landmark_entry,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                    args.window_width,
                    args.window_height,
                    args.window_length_fraction,
                    args.window_width_fraction,
                    args.inner_margin,
                )
            )

    query_features: list[TripointFeature] = []
    for specimen_id, specimen_records in sorted(query_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 3:
                continue
            query_features.append(
                preprocess_tripoint_feature(
                    record,
                    landmark_entry,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                    args.window_width,
                    args.window_height,
                    args.window_length_fraction,
                    args.window_width_fraction,
                    args.inner_margin,
                )
            )

    if not gallery_features:
        raise ValueError("No gallery images with 3-point landmarks were available for matching.")
    if not query_features:
        raise ValueError("No query images with 3-point landmarks were available for matching.")

    predictions = evaluate(
        query_features,
        gallery_features,
        output_dirs,
        allow_new_specimen=bool(args.allow_new_specimen),
        new_specimen_threshold=float(args.new_specimen_threshold),
        new_specimen_margin=float(args.new_specimen_margin),
    )
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
