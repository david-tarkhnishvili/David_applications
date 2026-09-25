from __future__ import annotations

import argparse
import csv
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
PIPELINE_VERSION = 4


@dataclass(frozen=True)
class ManifestRecord:
    specimen_id: str
    split: str
    image_path: Path
    relative_path: str
    source_file: str


@dataclass
class SpotFeature:
    image_path: Path
    relative_path: str
    specimen_id: str
    split: str
    preview_bgr: np.ndarray
    spot_map: np.ndarray
    spot_binary: np.ndarray
    thumb_map: np.ndarray
    thumb_mask: np.ndarray
    thumb_binary: np.ndarray
    keypoints_xy: np.ndarray
    descriptors: np.ndarray | None
    color_hist: np.ndarray
    green_leak_fraction: float
    quality_flag: str
    preview_path: Path
    spot_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Broad dorsal spot matcher for Darevskia images.")
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--output", help="Output folder. Defaults to project_dir/outputs/spot_match_run.")
    parser.add_argument("--cache", help="Cache file for gallery features. Defaults to project_dir/cache/spot_gallery_cache.pkl.")
    parser.add_argument("--rebuild-cache", action="store_true", help="Ignore the existing gallery cache and rebuild it.")
    parser.add_argument("--max-side", type=int, default=1600, help="Resize the longest image side to at most this value before feature extraction.")
    parser.add_argument("--preview-side", type=int, default=900, help="Save preview crops with this longest-side cap.")
    parser.add_argument("--thumb-size", type=int, default=256, help="Low-resolution size used for spot-map correlation.")
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


def ensure_dirs(base_output: Path) -> dict[str, Path]:
    mapping = {
        "preview": base_output / "preview",
        "spots": base_output / "spots",
        "qc": base_output / "qc",
    }
    for path in mapping.values():
        path.mkdir(parents=True, exist_ok=True)
    return mapping


def scan_project_records(project_dir: Path) -> list[ManifestRecord]:
    records: list[ManifestRecord] = []
    for split in ("gallery", "query"):
        split_dir = project_dir / split
        if not split_dir.exists():
            continue
        for specimen_dir in sorted(path for path in split_dir.iterdir() if path.is_dir()):
            specimen_id = specimen_dir.name.replace("specimen_", "")
            for image_path in sorted(specimen_dir.iterdir()):
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES:
                    records.append(
                        ManifestRecord(
                            specimen_id=specimen_id,
                            split=split,
                            image_path=image_path,
                            relative_path=str(image_path.relative_to(project_dir)).replace("/", "\\"),
                            source_file=image_path.name,
                        )
                    )
    return records


def load_manifest_records(project_dir: Path, manifest: Path, source_dir: Path | None) -> list[ManifestRecord]:
    records: list[ManifestRecord] = []
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            relative_path = str(row["relative_path"]).replace("/", "\\")
            records.append(
                ManifestRecord(
                    specimen_id=str(row["specimen_id"]).strip(),
                    split=str(row["split"]).strip().lower(),
                    image_path=(source_dir / str(row["source_file"]).strip()) if source_dir else (project_dir / Path(relative_path)),
                    relative_path=relative_path,
                    source_file=str(row.get("source_file", Path(relative_path).name)).strip(),
                )
            )
    return records


def infer_records(project_dir: Path, manifest_path: Path | None, source_dir: Path | None) -> list[ManifestRecord]:
    manifest = manifest_path or (project_dir / "config" / "manifest.csv")
    if source_dir is not None and manifest.exists():
        return load_manifest_records(project_dir, manifest, source_dir)
    return scan_project_records(project_dir)


def sample_paths(paths: list[ManifestRecord], limit: int | None, strategy: str) -> list[ManifestRecord]:
    if limit is None or len(paths) <= limit:
        return list(paths)
    if strategy == "first":
        return list(paths[:limit])
    if strategy == "last":
        return list(paths[-limit:])
    raw_indices = np.linspace(0, len(paths) - 1, num=limit)
    chosen_indices: list[int] = []
    for index in raw_indices:
        rounded = int(round(float(index)))
        if rounded not in chosen_indices:
            chosen_indices.append(rounded)
    if len(chosen_indices) < limit:
        for idx in range(len(paths)):
            if idx not in chosen_indices:
                chosen_indices.append(idx)
            if len(chosen_indices) >= limit:
                break
    chosen_indices = sorted(chosen_indices[:limit])
    return [paths[idx] for idx in chosen_indices]


def trim_grouped_records(grouped: dict[str, list[ManifestRecord]], specimen_order: list[str], total_limit: int) -> dict[str, list[ManifestRecord]]:
    trimmed: dict[str, list[ManifestRecord]] = {}
    seen = 0
    for specimen_id in specimen_order:
        specimen_records = grouped.get(specimen_id, [])
        if not specimen_records or seen >= total_limit:
            continue
        remaining = total_limit - seen
        kept = specimen_records[:remaining]
        if kept:
            trimmed[specimen_id] = kept
            seen += len(kept)
    return trimmed


def split_records(
    records: list[ManifestRecord],
    max_gallery: int | None,
    max_query: int | None,
    max_specimens: int | None,
    gallery_per_specimen: int | None,
    gallery_sampling: str,
    query_per_specimen: int | None,
) -> tuple[dict[str, list[ManifestRecord]], dict[str, list[ManifestRecord]]]:
    selected_specimens: list[str] = []
    selected_specimen_set: set[str] = set()
    all_gallery: dict[str, list[ManifestRecord]] = {}
    all_query: dict[str, list[ManifestRecord]] = {}

    for record in records:
        if record.specimen_id not in selected_specimen_set:
            if max_specimens is not None and len(selected_specimens) >= max_specimens:
                continue
            selected_specimens.append(record.specimen_id)
            selected_specimen_set.add(record.specimen_id)
        if record.specimen_id not in selected_specimen_set:
            continue
        if record.split == "gallery":
            all_gallery.setdefault(record.specimen_id, []).append(record)
        elif record.split == "query":
            all_query.setdefault(record.specimen_id, []).append(record)

    gallery = {
        specimen_id: sample_paths(all_gallery.get(specimen_id, []), gallery_per_specimen, gallery_sampling)
        for specimen_id in selected_specimens
        if all_gallery.get(specimen_id)
    }
    query = {
        specimen_id: sample_paths(all_query.get(specimen_id, []), query_per_specimen, "first")
        for specimen_id in selected_specimens
        if all_query.get(specimen_id)
    }

    if max_gallery is not None:
        gallery = trim_grouped_records(gallery, selected_specimens, max_gallery)
    if max_query is not None:
        query = trim_grouped_records(query, selected_specimens, max_query)
    return gallery, query


def keep_largest_component(mask: np.ndarray) -> np.ndarray:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num_labels <= 1:
        return mask
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == largest, 255, 0).astype(np.uint8)


def detect_green_background_pixels(image_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    b = image_bgr[:, :, 0].astype(np.int16)
    g = image_bgr[:, :, 1].astype(np.int16)
    r = image_bgr[:, :, 2].astype(np.int16)
    return (
        (hue >= 28)
        & (hue <= 95)
        & (sat >= 45)
        & (val >= 35)
        & (g >= r + 14)
        & (g >= b + 14)
    )


def suppress_green_leak(image_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float]:
    fg_pixels = int(np.count_nonzero(mask))
    if fg_pixels == 0:
        return mask.copy(), 0.0

    greenish = detect_green_background_pixels(image_bgr) & (mask > 0)
    green_fraction = float(np.count_nonzero(greenish)) / float(fg_pixels)
    if green_fraction <= 0.0:
        return mask.copy(), 0.0

    refined = mask.copy()
    refined[greenish] = 0
    refined = cv2.morphologyEx(refined, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    refined = cv2.morphologyEx(refined, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    refined = keep_largest_component(refined)

    retained_fraction = float(np.count_nonzero(refined)) / float(fg_pixels)
    if retained_fraction < 0.35:
        return mask.copy(), green_fraction
    return refined, green_fraction


def run_grabcut(image_bgr: np.ndarray) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    inset_x = max(8, int(round(width * 0.06)))
    inset_y = max(8, int(round(height * 0.06)))
    rect = (inset_x, inset_y, max(1, width - 2 * inset_x), max(1, height - 2 * inset_y))
    mask = np.zeros((height, width), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(image_bgr, mask, rect, bgd_model, fgd_model, 4, cv2.GC_INIT_WITH_RECT)
    fg_mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
    return keep_largest_component(fg_mask)


def resize_long_side(image_bgr: np.ndarray, max_side: int, mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None, float]:
    height, width = image_bgr.shape[:2]
    scale = min(1.0, float(max_side) / float(max(height, width)))
    if scale >= 0.999:
        return image_bgr.copy(), (mask.copy() if mask is not None else None), 1.0
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    resized_image = cv2.resize(image_bgr, new_size, interpolation=cv2.INTER_AREA)
    resized_mask = cv2.resize(mask, new_size, interpolation=cv2.INTER_NEAREST) if mask is not None else None
    return resized_image, resized_mask, scale


def crop_to_mask(image_bgr: np.ndarray, mask: np.ndarray, margin_fraction: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return image_bgr.copy(), mask.copy()
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    margin_y = max(6, int(round((y1 - y0 + 1) * margin_fraction)))
    margin_x = max(6, int(round((x1 - x0 + 1) * margin_fraction)))
    y0 = max(0, y0 - margin_y)
    y1 = min(image_bgr.shape[0], y1 + margin_y + 1)
    x0 = max(0, x0 - margin_x)
    x1 = min(image_bgr.shape[1], x1 + margin_x + 1)
    return image_bgr[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1].copy()


def filter_large_spot_components(binary: np.ndarray, mask: np.ndarray) -> np.ndarray:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num_labels <= 1:
        return binary
    mask_area = max(1, int(np.count_nonzero(mask)))
    min_area = max(18, int(round(mask_area * 0.00025)))
    filtered = np.zeros_like(binary, dtype=np.uint8)
    for label_idx in range(1, num_labels):
        area = int(stats[label_idx, cv2.CC_STAT_AREA])
        if area >= min_area:
            filtered[labels == label_idx] = 255
    return filtered


def create_shape_response(binary: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if np.count_nonzero(binary) == 0:
        return np.zeros_like(binary, dtype=np.uint8)
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    dist = cv2.GaussianBlur(dist, (0, 0), sigmaX=2.8, sigmaY=2.8)
    values = dist[mask > 0]
    if values.size == 0 or float(values.max()) < 1e-6:
        return np.zeros_like(binary, dtype=np.uint8)
    normalized = np.clip((dist / float(values.max())) * 255.0, 0, 255).astype(np.uint8)
    normalized[mask == 0] = 0
    return normalized


def create_dark_spot_map(crop_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lab = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2LAB)
    lightness = lab[:, :, 0]
    highlight_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    highlight_map = cv2.morphologyEx(lightness, cv2.MORPH_TOPHAT, highlight_kernel)
    deglinted = cv2.subtract(lightness, cv2.GaussianBlur(highlight_map, (0, 0), sigmaX=1.2, sigmaY=1.2))

    scale_suppressed = cv2.bilateralFilter(deglinted, d=9, sigmaColor=28, sigmaSpace=9)
    scale_suppressed = cv2.medianBlur(scale_suppressed, 5)

    small_h = max(48, int(round(crop_bgr.shape[0] * 0.35)))
    small_w = max(48, int(round(crop_bgr.shape[1] * 0.35)))
    small = cv2.resize(scale_suppressed, (small_w, small_h), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigmaX=1.2, sigmaY=1.2)
    broad_background_small = cv2.GaussianBlur(small, (0, 0), sigmaX=4.8, sigmaY=4.8)
    adaptive_dark_small = cv2.subtract(broad_background_small, small)
    adaptive_dark = cv2.resize(adaptive_dark_small, (crop_bgr.shape[1], crop_bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
    adaptive_dark = cv2.GaussianBlur(adaptive_dark, (0, 0), sigmaX=1.8, sigmaY=4.8)

    masked_values = adaptive_dark[mask > 0]
    if masked_values.size == 0:
        return adaptive_dark, np.zeros_like(adaptive_dark, dtype=np.uint8)

    threshold_value = float(np.percentile(masked_values, 66))
    binary = np.where(adaptive_dark >= threshold_value, 255, 0).astype(np.uint8)
    binary = cv2.bitwise_and(binary, binary, mask=mask)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((9, 5), np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    binary = filter_large_spot_components(binary, mask)
    response = create_shape_response(binary, mask)
    return response, binary


def masked_corrcoef(a: np.ndarray, b: np.ndarray, mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    overlap_mask = (mask_a > 0) & (mask_b > 0)
    if np.count_nonzero(overlap_mask) < 64:
        return 0.0
    a_float = a.astype(np.float32)[overlap_mask].ravel()
    b_float = b.astype(np.float32)[overlap_mask].ravel()
    if np.std(a_float) < 1e-6 or np.std(b_float) < 1e-6:
        return 0.0
    score = np.corrcoef(a_float, b_float)[0, 1]
    return 0.0 if np.isnan(score) else float(score)


def create_preview(crop_bgr: np.ndarray, preview_side: int) -> np.ndarray:
    preview, _, _ = resize_long_side(crop_bgr, preview_side)
    return preview


def normalize_masked_map_for_preview(spot_map: np.ndarray, mask: np.ndarray) -> np.ndarray:
    preview = np.zeros_like(spot_map, dtype=np.uint8)
    values = spot_map[mask > 0]
    if values.size == 0:
        return preview
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax - vmin < 1e-6:
        preview[mask > 0] = 128
        return preview
    normalized = np.clip((spot_map.astype(np.float32) - vmin) * (255.0 / (vmax - vmin)), 0, 255).astype(np.uint8)
    preview[mask > 0] = normalized[mask > 0]
    return preview


def make_spot_preview_bgr(spot_map: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    if mask is None:
        mask = np.where(spot_map > 0, 255, 0).astype(np.uint8)
    preview_gray = normalize_masked_map_for_preview(spot_map, mask)
    return cv2.applyColorMap(preview_gray, cv2.COLORMAP_BONE)


def make_spot_outline_preview_bgr(binary: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    if mask is None:
        mask = np.where(binary > 0, 255, 0).astype(np.uint8)
    canvas = np.zeros((binary.shape[0], binary.shape[1], 3), dtype=np.uint8)
    canvas[:] = (24, 24, 24)
    if mask is not None:
        canvas[mask == 0] = (0, 0, 0)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(canvas, contours, -1, (230, 230, 230), thickness=2, lineType=cv2.LINE_AA)
    return canvas


def create_pattern_enhanced_preview(crop_bgr: np.ndarray, mask: np.ndarray, spot_map: np.ndarray) -> np.ndarray:
    smoothed = cv2.edgePreservingFilter(crop_bgr, flags=1, sigma_s=70, sigma_r=0.45)
    lab = cv2.cvtColor(smoothed, cv2.COLOR_BGR2LAB)
    spot_preview = normalize_masked_map_for_preview(spot_map, mask).astype(np.float32)
    darkening = (spot_preview / 255.0) * 78.0
    adjusted_l = np.clip(lab[:, :, 0].astype(np.float32) - darkening, 0, 255).astype(np.uint8)
    lab[:, :, 0] = adjusted_l
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    enhanced[mask == 0] = (127, 127, 127)
    return enhanced


def preprocess_spot_feature(
    record: ManifestRecord,
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
) -> SpotFeature:
    image_bgr = cv2.imread(str(record.image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(f"Could not read image: {record.image_path}")

    working, _, _ = resize_long_side(image_bgr, max_side)
    mask = run_grabcut(working)
    mask, green_fraction_full = suppress_green_leak(working, mask)
    crop_bgr, crop_mask = crop_to_mask(working, mask)
    crop_mask, green_fraction_crop = suppress_green_leak(crop_bgr, crop_mask)
    dark_response, dark_binary = create_dark_spot_map(crop_bgr, crop_mask)

    masked_preview = create_pattern_enhanced_preview(crop_bgr, crop_mask, dark_response)

    blurred_map = cv2.GaussianBlur(dark_response, (0, 0), sigmaX=3.0, sigmaY=3.0)
    masked_map = blurred_map.copy()
    masked_map[crop_mask == 0] = 0

    detector = cv2.AKAZE_create(threshold=0.0009)
    keypoints, descriptors = detector.detectAndCompute(masked_map, mask=crop_mask)
    if descriptors is None or len(keypoints) < 10:
        orb = cv2.ORB_create(nfeatures=1200, fastThreshold=10)
        keypoints, descriptors = orb.detectAndCompute(masked_map, mask=crop_mask)
    keypoints_xy = np.array([kp.pt for kp in keypoints], dtype=np.float32) if keypoints else np.empty((0, 2), dtype=np.float32)

    thumb_map = cv2.resize(masked_map, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
    thumb_mask = cv2.resize(crop_mask, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)
    thumb_binary = cv2.resize(dark_binary, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)

    hsv = cv2.cvtColor(masked_preview, cv2.COLOR_BGR2HSV)
    color_hist = cv2.calcHist([hsv], [0, 1], crop_mask, [16, 16], [0, 180, 0, 256])
    color_hist = cv2.normalize(color_hist, color_hist).flatten()

    preview_bgr = create_preview(masked_preview, preview_side)
    preview_path = output_dirs["preview"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_preview.png"
    spot_path = output_dirs["spots"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_spots.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(preview_path), preview_bgr)
    cv2.imwrite(str(spot_path), make_spot_outline_preview_bgr(dark_binary, crop_mask))

    dark_fraction = float(np.count_nonzero(dark_binary)) / float(max(1, dark_binary.size))
    green_leak_fraction = max(green_fraction_full, green_fraction_crop)
    quality_flags: list[str] = []
    if green_leak_fraction >= 0.08:
        quality_flags.append("warn:green_leak")
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
        green_leak_fraction=green_leak_fraction,
        quality_flag=quality_flag,
        preview_path=preview_path,
        spot_path=spot_path,
    )


def serialize_feature(feature: SpotFeature, max_side: int, preview_side: int, thumb_size: int) -> dict[str, object]:
    return {
        "relative_path": feature.relative_path,
        "image_path": str(feature.image_path),
        "specimen_id": feature.specimen_id,
        "split": feature.split,
        "preview_bgr": feature.preview_bgr,
        "spot_map": feature.spot_map,
        "spot_binary": feature.spot_binary,
        "thumb_map": feature.thumb_map,
        "thumb_mask": feature.thumb_mask,
        "thumb_binary": feature.thumb_binary,
        "keypoints_xy": feature.keypoints_xy,
        "descriptors": feature.descriptors,
        "color_hist": feature.color_hist,
        "green_leak_fraction": feature.green_leak_fraction,
        "quality_flag": feature.quality_flag,
        "pipeline_version": PIPELINE_VERSION,
        "max_side": max_side,
        "preview_side": preview_side,
        "thumb_size": thumb_size,
        "mtime_ns": feature.image_path.stat().st_mtime_ns,
        "file_size": feature.image_path.stat().st_size,
    }


def deserialize_feature(payload: dict[str, object], output_dirs: dict[str, Path]) -> SpotFeature:
    image_path = Path(str(payload["image_path"]))
    specimen_id = str(payload["specimen_id"])
    split = str(payload["split"])
    preview_path = output_dirs["preview"] / split / f"specimen_{specimen_id}" / f"{image_path.stem}_preview.png"
    spot_path = output_dirs["spots"] / split / f"specimen_{specimen_id}" / f"{image_path.stem}_spots.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)
    return SpotFeature(
        image_path=image_path,
        relative_path=str(payload["relative_path"]),
        specimen_id=specimen_id,
        split=split,
        preview_bgr=np.asarray(payload["preview_bgr"]),
        spot_map=np.asarray(payload["spot_map"]),
        spot_binary=np.asarray(payload["spot_binary"]),
        thumb_map=np.asarray(payload["thumb_map"]),
        thumb_mask=np.asarray(payload["thumb_mask"]),
        thumb_binary=np.asarray(payload["thumb_binary"]),
        keypoints_xy=np.asarray(payload["keypoints_xy"], dtype=np.float32),
        descriptors=None if payload["descriptors"] is None else np.asarray(payload["descriptors"]),
        color_hist=np.asarray(payload["color_hist"], dtype=np.float32),
        green_leak_fraction=float(payload.get("green_leak_fraction", 0.0)),
        quality_flag=str(payload["quality_flag"]),
        preview_path=preview_path,
        spot_path=spot_path,
    )


def load_cache(cache_path: Path) -> dict[str, dict[str, object]]:
    if not cache_path.exists():
        return {}
    with cache_path.open("rb") as handle:
        payload = pickle.load(handle)
    return payload if isinstance(payload, dict) else {}


def save_cache(cache_path: Path, cache_payload: dict[str, dict[str, object]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as handle:
        pickle.dump(cache_payload, handle, protocol=pickle.HIGHEST_PROTOCOL)


def feature_cache_key(record: ManifestRecord) -> str:
    return record.relative_path or str(record.image_path)


def cache_hit_valid(record: ManifestRecord, cached: dict[str, object], max_side: int, preview_side: int, thumb_size: int) -> bool:
    try:
        stat = record.image_path.stat()
    except FileNotFoundError:
        return False
    return (
        cached.get("mtime_ns") == stat.st_mtime_ns
        and cached.get("file_size") == stat.st_size
        and cached.get("pipeline_version") == PIPELINE_VERSION
        and cached.get("max_side") == max_side
        and cached.get("preview_side") == preview_side
        and cached.get("thumb_size") == thumb_size
    )


def get_gallery_feature(
    record: ManifestRecord,
    cache_payload: dict[str, dict[str, object]],
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
) -> SpotFeature:
    key = feature_cache_key(record)
    cached = cache_payload.get(key)
    if cached and cache_hit_valid(record, cached, max_side, preview_side, thumb_size):
        return deserialize_feature(cached, output_dirs)
    feature = preprocess_spot_feature(record, output_dirs, max_side, preview_side, thumb_size)
    cache_payload[key] = serialize_feature(feature, max_side, preview_side, thumb_size)
    return feature


def geometric_match(query: SpotFeature, candidate: SpotFeature) -> tuple[int, int, float]:
    if query.descriptors is None or candidate.descriptors is None:
        return 0, 0, 0.0
    if len(query.keypoints_xy) < 8 or len(candidate.keypoints_xy) < 8:
        return 0, 0, 0.0

    if query.descriptors.dtype == np.uint8 and candidate.descriptors.dtype == np.uint8:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    else:
        matcher = cv2.BFMatcher(cv2.NORM_L2)

    knn_matches = matcher.knnMatch(query.descriptors, candidate.descriptors, k=2)
    good_matches = []
    for pair in knn_matches:
        if len(pair) < 2:
            continue
        first, second = pair
        if first.distance < 0.78 * second.distance:
            good_matches.append(first)

    if len(good_matches) < 6:
        return len(good_matches), 0, 0.0

    query_points = np.float32([query.keypoints_xy[m.queryIdx] for m in good_matches])
    candidate_points = np.float32([candidate.keypoints_xy[m.trainIdx] for m in good_matches])
    affine, inliers = cv2.estimateAffinePartial2D(
        query_points,
        candidate_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=5.5,
        maxIters=2000,
        confidence=0.995,
    )
    if affine is None or inliers is None:
        return len(good_matches), 0, 0.0
    inlier_count = int(inliers.ravel().sum())
    inlier_ratio = float(inlier_count) / float(max(1, len(good_matches)))
    normalized_inliers = min(1.0, float(inlier_count) / 24.0)
    geom_score = (0.6 * inlier_ratio) + (0.4 * normalized_inliers)
    return len(good_matches), inlier_count, geom_score


def compare_features(query: SpotFeature, candidate: SpotFeature) -> tuple[float, dict[str, float]]:
    good_matches, inlier_count, geom_score = geometric_match(query, candidate)
    map_score = (masked_corrcoef(query.thumb_map, candidate.thumb_map, query.thumb_mask, candidate.thumb_mask) + 1.0) / 2.0
    hist_score = (cv2.compareHist(query.color_hist.astype(np.float32), candidate.color_hist.astype(np.float32), cv2.HISTCMP_CORREL) + 1.0) / 2.0
    total_score = float((0.72 * geom_score) + (0.20 * map_score) + (0.08 * hist_score))
    details = {
        "good_matches": float(good_matches),
        "inlier_count": float(inlier_count),
        "geom_score": float(geom_score),
        "map_score": float(map_score),
        "hist_score": float(hist_score),
    }
    return total_score, details


def pil_from_bgr(image_bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))


def add_label(canvas: Image.Image, text: str, x: int, y: int, width: int) -> None:
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.rectangle((x, y, x + width, y + 20), fill=(255, 255, 255))
    draw.text((x + 4, y + 3), text, fill=(0, 0, 0), font=font)


def make_qc_panel(
    query: SpotFeature,
    best_match: SpotFeature,
    panel_path: Path,
    predicted_specimen: str,
    best_score: float,
    second_specimen: str,
    second_score: float,
    is_correct: bool,
    decision_reason: str,
) -> None:
    images = [
        pil_from_bgr(query.preview_bgr).resize((320, 420)),
        pil_from_bgr(make_spot_preview_bgr(query.spot_map, query.thumb_mask)).resize((320, 320)),
        pil_from_bgr(best_match.preview_bgr).resize((320, 420)),
        pil_from_bgr(make_spot_preview_bgr(best_match.spot_map, best_match.thumb_mask)).resize((320, 320)),
    ]
    canvas = Image.new("RGB", (680, 840), color=(245, 245, 245))
    canvas.paste(images[0], (20, 40))
    canvas.paste(images[2], (340, 40))
    canvas.paste(images[1], (20, 480))
    canvas.paste(images[3], (340, 480))
    add_label(canvas, f"Query preview: {query.image_path.name}", 20, 12, 320)
    add_label(canvas, f"Best match preview: {best_match.image_path.name}", 340, 12, 320)
    add_label(canvas, "Query dark-spot map", 20, 452, 320)
    add_label(canvas, "Best match dark-spot map", 340, 452, 320)
    verdict = "correct" if is_correct else "mismatch"
    add_label(
        canvas,
        f"true={query.specimen_id} predicted={predicted_specimen} best={best_score:.3f} second={second_specimen}:{second_score:.3f} {verdict} {decision_reason}",
        20,
        800,
        640,
    )
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(panel_path)


def decide_prediction(
    ranked: list[tuple[str, tuple[float, SpotFeature, dict[str, float]]]],
    allow_new_specimen: bool,
    new_specimen_threshold: float,
    new_specimen_margin: float,
) -> tuple[str, str, float, str, float, SpotFeature, dict[str, float], bool]:
    predicted_specimen, (best_score, best_match, best_details) = ranked[0]
    if len(ranked) > 1:
        second_specimen, (second_score, _, _) = ranked[1]
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


def evaluate(
    query_features: list[SpotFeature],
    gallery_features: list[SpotFeature],
    output_dirs: dict[str, Path],
    allow_new_specimen: bool,
    new_specimen_threshold: float,
    new_specimen_margin: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    gallery_specimens = {feature.specimen_id for feature in gallery_features}

    for query in query_features:
        specimen_scores: dict[str, tuple[float, SpotFeature, dict[str, float]]] = {}
        for candidate in gallery_features:
            score, details = compare_features(query, candidate)
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
                "good_matches": int(best_details["good_matches"]),
                "inlier_count": int(best_details["inlier_count"]),
                "geom_score": float(best_details["geom_score"]),
                "map_score": float(best_details["map_score"]),
                "hist_score": float(best_details["hist_score"]),
                "green_leak_fraction": query.green_leak_fraction,
                "quality_flag": query.quality_flag,
                "preview_file": str(query.preview_path),
                "spot_file": str(query.spot_path),
                "qc_file": str(qc_path),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    source_dir = Path(args.source_images) if args.source_images else None
    output_dir = Path(args.output) if args.output else project_dir / "outputs" / "spot_match_run"
    cache_path = Path(args.cache) if args.cache else project_dir / "cache" / "spot_gallery_cache.pkl"
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

    cache_payload: dict[str, dict[str, object]] = {} if args.rebuild_cache else load_cache(cache_path)
    gallery_features: list[SpotFeature] = []
    for specimen_id, specimen_records in sorted(gallery_records.items()):
        for record in specimen_records:
            gallery_features.append(
                get_gallery_feature(
                    record,
                    cache_payload,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                )
            )

    query_features: list[SpotFeature] = []
    for specimen_id, specimen_records in sorted(query_records.items()):
        for record in specimen_records:
            query_features.append(
                preprocess_spot_feature(
                    record,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                )
            )

    save_cache(cache_path, cache_payload)

    predictions = evaluate(
        query_features,
        gallery_features,
        output_dirs,
        allow_new_specimen=args.allow_new_specimen,
        new_specimen_threshold=args.new_specimen_threshold,
        new_specimen_margin=args.new_specimen_margin,
    )

    predictions_path = output_dir / "predictions.csv"
    summary_path = output_dir / "summary.json"
    predictions.to_csv(predictions_path, index=False)

    per_specimen = (
        predictions.groupby("true_specimen")["correct"]
        .agg(["count", "sum", "mean"])
        .rename(columns={"sum": "correct_count", "mean": "accuracy"})
        .reset_index()
    )
    summary = {
        "mode": "broad_dorsum_spot_matcher",
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "cache_path": str(cache_path),
        "max_side": args.max_side,
        "preview_side": args.preview_side,
        "thumb_size": args.thumb_size,
        "max_specimens": args.max_specimens,
        "gallery_per_specimen": args.gallery_per_specimen,
        "gallery_sampling": args.gallery_sampling,
        "query_per_specimen": args.query_per_specimen,
        "n_gallery_images": len(gallery_features),
        "n_query_images": len(query_features),
        "overall_accuracy": float(predictions["correct"].mean()) if len(predictions) else 0.0,
        "allow_new_specimen": args.allow_new_specimen,
        "new_specimen_threshold": args.new_specimen_threshold,
        "new_specimen_margin": args.new_specimen_margin,
        "n_new_specimen_predictions": int(predictions["new_specimen_flag"].sum()) if len(predictions) else 0,
        "per_specimen": per_specimen.to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved predictions to: {predictions_path}")


if __name__ == "__main__":
    main()
