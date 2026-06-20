from __future__ import annotations

import argparse
import csv
import json
import pickle
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd
from PIL import Image

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from darevskia_spot_matcher import (
    IMAGE_SUFFIXES,
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

PIPELINE_VERSION = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="4-point dorsal quadrilateral matcher: warp the marked dorsum region, then run the spot matcher on the warped patch."
    )
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--landmarks", help="CSV containing 4-point annotations. Defaults to project_dir/config/dorsal_quad_landmarks.csv.")
    parser.add_argument("--output", help="Output folder. Defaults to project_dir/outputs/quad_spot_run.")
    parser.add_argument("--cache", help="Cache file for gallery features. Defaults to project_dir/cache/quad_spot_gallery_cache.pkl.")
    parser.add_argument("--rebuild-cache", action="store_true", help="Ignore the existing gallery cache and rebuild it.")
    parser.add_argument("--max-side", type=int, default=2200, help="Resize the longest image side to at most this value before warping.")
    parser.add_argument("--preview-side", type=int, default=900, help="Save warped previews with this longest-side cap.")
    parser.add_argument("--thumb-size", type=int, default=256, help="Low-resolution size used for spot-map correlation.")
    parser.add_argument("--warp-width", type=int, default=520, help="Width of the warped dorsal rectangle.")
    parser.add_argument("--warp-height", type=int, default=720, help="Height of the warped dorsal rectangle.")
    parser.add_argument("--inner-margin", type=float, default=0.03, help="Fraction to trim from each side of the warped rectangle to avoid boundary/background noise.")
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
        "warped": base_output / "warped",
        "overlay": base_output / "overlay",
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
            if len(points) < 4:
                continue
            rows[relative_path] = {
                "relative_path": relative_path,
                "specimen_id": str(row["specimen_id"]),
                "split": str(row["split"]).lower(),
                "image_width": int(float(row.get("image_width") or 0)),
                "image_height": int(float(row.get("image_height") or 0)),
                "point_count": point_count,
                "points": points,
            }
    return rows


def landmarks_signature(entry: dict[str, object]) -> str:
    points = entry["points"]
    if not isinstance(points, list):
        return "[]"
    rounded = [[round(float(x), 2), round(float(y), 2)] for x, y in points]
    return json.dumps(rounded, separators=(",", ":"))


def draw_overlay(image_bgr: np.ndarray, points: list[tuple[float, float]]) -> np.ndarray:
    overlay = image_bgr.copy()
    polygon = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(overlay, [polygon], isClosed=True, color=(0, 255, 120), thickness=5, lineType=cv2.LINE_AA)
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


def warp_quadrilateral(
    image_bgr: np.ndarray,
    points: list[tuple[float, float]],
    warp_width: int,
    warp_height: int,
    inner_margin: float,
) -> tuple[np.ndarray, np.ndarray]:
    src = np.asarray(points[:4], dtype=np.float32)
    dst = np.array(
        [
            [0.0, 0.0],
            [float(warp_width - 1), 0.0],
            [float(warp_width - 1), float(warp_height - 1)],
            [0.0, float(warp_height - 1)],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        image_bgr,
        matrix,
        (warp_width, warp_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    margin_x = max(0, int(round(warp_width * inner_margin)))
    margin_y = max(0, int(round(warp_height * inner_margin)))
    x0 = min(margin_x, max(0, warp_width // 6))
    y0 = min(margin_y, max(0, warp_height // 6))
    x1 = max(x0 + 8, warp_width - x0)
    y1 = max(y0 + 8, warp_height - y0)
    trimmed = warped[y0:y1, x0:x1].copy()
    mask = np.full(trimmed.shape[:2], 255, dtype=np.uint8)
    return trimmed, mask


def preprocess_quad_feature(
    record: ManifestRecord,
    landmark_entry: dict[str, object],
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    warp_width: int,
    warp_height: int,
    inner_margin: float,
) -> SpotFeature:
    image_bgr = read_image_bgr_raw(record.image_path)

    working, _, scale = resize_long_side(image_bgr, max_side)
    points = [(float(x) * scale, float(y) * scale) for x, y in landmark_entry["points"][:4]]

    warped_bgr, warped_mask = warp_quadrilateral(working, points, warp_width, warp_height, inner_margin)
    dark_response, dark_binary = create_dark_spot_map(warped_bgr, warped_mask)

    masked_preview = warped_bgr.copy()
    masked_preview[warped_mask == 0] = (127, 127, 127)

    blurred_map = cv2.GaussianBlur(dark_response, (0, 0), sigmaX=3.0, sigmaY=3.0)
    masked_map = blurred_map.copy()
    masked_map[warped_mask == 0] = 0

    detector = cv2.AKAZE_create(threshold=0.0009)
    keypoints, descriptors = detector.detectAndCompute(masked_map, mask=warped_mask)
    if descriptors is None or len(keypoints) < 10:
        orb = cv2.ORB_create(nfeatures=1200, fastThreshold=10)
        keypoints, descriptors = orb.detectAndCompute(masked_map, mask=warped_mask)
    keypoints_xy = np.array([kp.pt for kp in keypoints], dtype=np.float32) if keypoints else np.empty((0, 2), dtype=np.float32)

    thumb_map = cv2.resize(masked_map, (thumb_size, thumb_size), interpolation=cv2.INTER_AREA)
    thumb_mask = cv2.resize(warped_mask, (thumb_size, thumb_size), interpolation=cv2.INTER_NEAREST)

    hsv = cv2.cvtColor(masked_preview, cv2.COLOR_BGR2HSV)
    color_hist = cv2.calcHist([hsv], [0, 1], warped_mask, [16, 16], [0, 180, 0, 256])
    color_hist = cv2.normalize(color_hist, color_hist).flatten()

    preview_bgr, _, _ = resize_long_side(masked_preview, preview_side)
    warped_path = output_dirs["warped"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_warped.png"
    overlay_path = output_dirs["overlay"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_overlay.png"
    spot_path = output_dirs["spots"] / record.split / f"specimen_{record.specimen_id}" / f"{record.image_path.stem}_spots.png"
    warped_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(warped_path), preview_bgr)
    cv2.imwrite(str(overlay_path), draw_overlay(working, points))
    cv2.imwrite(str(spot_path), make_spot_preview_bgr(masked_map, warped_mask))

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
        thumb_map=thumb_map,
        thumb_mask=thumb_mask,
        keypoints_xy=keypoints_xy,
        descriptors=descriptors,
        color_hist=color_hist,
        green_leak_fraction=0.0,
        quality_flag=quality_flag,
        preview_path=warped_path,
        spot_path=spot_path,
    )


def serialize_feature(
    feature: SpotFeature,
    landmark_entry: dict[str, object],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    warp_width: int,
    warp_height: int,
    inner_margin: float,
) -> dict[str, object]:
    return {
        "relative_path": feature.relative_path,
        "image_path": str(feature.image_path),
        "specimen_id": feature.specimen_id,
        "split": feature.split,
        "preview_bgr": feature.preview_bgr,
        "spot_map": feature.spot_map,
        "thumb_map": feature.thumb_map,
        "thumb_mask": feature.thumb_mask,
        "keypoints_xy": feature.keypoints_xy,
        "descriptors": feature.descriptors,
        "color_hist": feature.color_hist,
        "green_leak_fraction": 0.0,
        "quality_flag": feature.quality_flag,
        "landmarks_signature": landmarks_signature(landmark_entry),
        "pipeline_version": PIPELINE_VERSION,
        "max_side": max_side,
        "preview_side": preview_side,
        "thumb_size": thumb_size,
        "warp_width": warp_width,
        "warp_height": warp_height,
        "inner_margin": inner_margin,
        "mtime_ns": feature.image_path.stat().st_mtime_ns,
        "file_size": feature.image_path.stat().st_size,
    }


def deserialize_feature(payload: dict[str, object], output_dirs: dict[str, Path]) -> SpotFeature:
    image_path = Path(str(payload["image_path"]))
    specimen_id = str(payload["specimen_id"])
    split = str(payload["split"])
    warped_path = output_dirs["warped"] / split / f"specimen_{specimen_id}" / f"{image_path.stem}_warped.png"
    spot_path = output_dirs["spots"] / split / f"specimen_{specimen_id}" / f"{image_path.stem}_spots.png"
    warped_path.parent.mkdir(parents=True, exist_ok=True)
    spot_path.parent.mkdir(parents=True, exist_ok=True)
    return SpotFeature(
        image_path=image_path,
        relative_path=str(payload["relative_path"]),
        specimen_id=specimen_id,
        split=split,
        preview_bgr=np.asarray(payload["preview_bgr"]),
        spot_map=np.asarray(payload["spot_map"]),
        thumb_map=np.asarray(payload["thumb_map"]),
        thumb_mask=np.asarray(payload["thumb_mask"]),
        keypoints_xy=np.asarray(payload["keypoints_xy"], dtype=np.float32),
        descriptors=None if payload["descriptors"] is None else np.asarray(payload["descriptors"]),
        color_hist=np.asarray(payload["color_hist"], dtype=np.float32),
        green_leak_fraction=0.0,
        quality_flag=str(payload["quality_flag"]),
        preview_path=warped_path,
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


def cache_hit_valid(
    record: ManifestRecord,
    landmark_entry: dict[str, object],
    cached: dict[str, object],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    warp_width: int,
    warp_height: int,
    inner_margin: float,
) -> bool:
    try:
        stat = record.image_path.stat()
    except FileNotFoundError:
        return False
    return (
        cached.get("mtime_ns") == stat.st_mtime_ns
        and cached.get("file_size") == stat.st_size
        and cached.get("pipeline_version") == PIPELINE_VERSION
        and cached.get("landmarks_signature") == landmarks_signature(landmark_entry)
        and cached.get("max_side") == max_side
        and cached.get("preview_side") == preview_side
        and cached.get("thumb_size") == thumb_size
        and cached.get("warp_width") == warp_width
        and cached.get("warp_height") == warp_height
        and abs(float(cached.get("inner_margin", -1.0)) - float(inner_margin)) < 1e-9
    )


def get_gallery_feature(
    record: ManifestRecord,
    landmark_entry: dict[str, object],
    cache_payload: dict[str, dict[str, object]],
    output_dirs: dict[str, Path],
    max_side: int,
    preview_side: int,
    thumb_size: int,
    warp_width: int,
    warp_height: int,
    inner_margin: float,
) -> SpotFeature:
    key = feature_cache_key(record)
    cached = cache_payload.get(key)
    if cached and cache_hit_valid(record, landmark_entry, cached, max_side, preview_side, thumb_size, warp_width, warp_height, inner_margin):
        return deserialize_feature(cached, output_dirs)
    feature = preprocess_quad_feature(record, landmark_entry, output_dirs, max_side, preview_side, thumb_size, warp_width, warp_height, inner_margin)
    cache_payload[key] = serialize_feature(feature, landmark_entry, max_side, preview_side, thumb_size, warp_width, warp_height, inner_margin)
    return feature


def compare_features(query: SpotFeature, candidate: SpotFeature) -> tuple[float, dict[str, float]]:
    good_matches, inlier_count, geom_score = geometric_match(query, candidate)
    map_score = (masked_corrcoef(query.thumb_map, candidate.thumb_map, query.thumb_mask, candidate.thumb_mask) + 1.0) / 2.0
    hist_score = (cv2.compareHist(query.color_hist.astype(np.float32), candidate.color_hist.astype(np.float32), cv2.HISTCMP_CORREL) + 1.0) / 2.0

    # For the manually defined dorsal quadrilateral, the most trustworthy signal
    # is geometric consistency of the dark-spot constellation. Broad texture or
    # color agreement alone should not dominate when feature matching is weak.
    total_score = float((0.70 * geom_score) + (0.25 * map_score) + (0.05 * hist_score))

    if inlier_count == 0:
        total_score *= 0.72
    elif inlier_count <= 2:
        total_score *= 0.88

    details = {
        "good_matches": float(good_matches),
        "inlier_count": float(inlier_count),
        "geom_score": float(geom_score),
        "map_score": float(map_score),
        "hist_score": float(hist_score),
    }
    return total_score, details


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
    query_spots = pil_from_bgr(make_spot_preview_bgr(query.thumb_map, query.thumb_mask)).resize((320, 320))
    best_spots = pil_from_bgr(make_spot_preview_bgr(best_match.thumb_map, best_match.thumb_mask)).resize((320, 320))
    images = [
        pil_from_bgr(query.preview_bgr).resize((320, 420)),
        query_spots,
        pil_from_bgr(best_match.preview_bgr).resize((320, 420)),
        best_spots,
    ]
    canvas = Image.new("RGB", (680, 840), color=(245, 245, 245))
    canvas.paste(images[0], (20, 40))
    canvas.paste(images[2], (340, 40))
    canvas.paste(images[1], (20, 480))
    canvas.paste(images[3], (340, 480))
    add_label(canvas, f"Query warped region: {query.image_path.name}", 20, 12, 320)
    add_label(canvas, f"Best matched gallery: {best_match.image_path.name}", 340, 12, 320)
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
                "quality_flag": query.quality_flag,
                "preview_file": str(query.preview_path),
                "spot_file": str(query.spot_path),
                "qc_file": str(qc_path),
            }
        )
    return pd.DataFrame(rows)


def summarize_predictions(
    predictions: pd.DataFrame,
    output_dir: Path,
    project_dir: Path,
    cache_path: Path,
    args: argparse.Namespace,
    n_manifest_records: int,
    n_gallery_images: int,
    n_query_images: int,
    n_annotated_gallery_images: int,
    n_annotated_query_images: int,
    n_skipped_gallery_images: int,
    n_skipped_query_images: int,
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
    summary = {
        "mode": "quad_region_spot_matcher",
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "cache_path": str(cache_path),
        "landmarks_path": str(Path(args.landmarks) if args.landmarks else (project_dir / "config" / "dorsal_quad_landmarks.csv")),
        "max_side": args.max_side,
        "preview_side": args.preview_side,
        "thumb_size": args.thumb_size,
        "warp_width": args.warp_width,
        "warp_height": args.warp_height,
        "inner_margin": args.inner_margin,
        "max_specimens": args.max_specimens,
        "gallery_per_specimen": args.gallery_per_specimen,
        "gallery_sampling": args.gallery_sampling,
        "query_per_specimen": args.query_per_specimen,
        "n_manifest_records": n_manifest_records,
        "n_gallery_images": n_gallery_images,
        "n_query_images": n_query_images,
        "n_annotated_gallery_images": n_annotated_gallery_images,
        "n_annotated_query_images": n_annotated_query_images,
        "n_skipped_gallery_images_without_landmarks": n_skipped_gallery_images,
        "n_skipped_query_images_without_landmarks": n_skipped_query_images,
        "overall_accuracy": overall_accuracy,
        "allow_new_specimen": bool(args.allow_new_specimen),
        "new_specimen_threshold": float(args.new_specimen_threshold),
        "new_specimen_margin": float(args.new_specimen_margin),
        "n_new_specimen_predictions": int((predictions["predicted_specimen"] == "NEW_SPECIMEN").sum()) if len(predictions) else 0,
        "per_specimen": per_specimen,
    }
    return summary


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    source_dir = Path(args.source_images) if args.source_images else None
    landmarks_path = Path(args.landmarks) if args.landmarks else project_dir / "config" / "dorsal_quad_landmarks.csv"
    output_dir = Path(args.output) if args.output else project_dir / "outputs" / "quad_spot_run"
    cache_path = Path(args.cache) if args.cache else project_dir / "cache" / "quad_spot_gallery_cache.pkl"
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

    cache_payload: dict[str, dict[str, object]] = {} if args.rebuild_cache else load_cache(cache_path)

    gallery_features: list[SpotFeature] = []
    n_skipped_gallery = 0
    for specimen_id, specimen_records in sorted(gallery_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 4:
                n_skipped_gallery += 1
                continue
            gallery_features.append(
                get_gallery_feature(
                    record,
                    landmark_entry,
                    cache_payload,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                    args.warp_width,
                    args.warp_height,
                    args.inner_margin,
                )
            )

    query_features: list[SpotFeature] = []
    n_skipped_query = 0
    for specimen_id, specimen_records in sorted(query_records.items()):
        for record in specimen_records:
            landmark_entry = landmark_rows.get(record.relative_path)
            if not landmark_entry or int(landmark_entry.get("point_count", 0)) < 4:
                n_skipped_query += 1
                continue
            query_features.append(
                preprocess_quad_feature(
                    record,
                    landmark_entry,
                    output_dirs,
                    args.max_side,
                    args.preview_side,
                    args.thumb_size,
                    args.warp_width,
                    args.warp_height,
                    args.inner_margin,
                )
            )

    save_cache(cache_path, cache_payload)

    if not gallery_features:
        raise ValueError("No gallery images with 4-point landmarks were available for matching.")
    if not query_features:
        raise ValueError("No query images with 4-point landmarks were available for matching.")

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
        cache_path,
        args,
        n_manifest_records=len(records),
        n_gallery_images=sum(len(items) for items in gallery_records.values()),
        n_query_images=sum(len(items) for items in query_records.values()),
        n_annotated_gallery_images=len(gallery_features),
        n_annotated_query_images=len(query_features),
        n_skipped_gallery_images=n_skipped_gallery,
        n_skipped_query_images=n_skipped_query,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"Saved predictions to: {predictions_path}")


if __name__ == "__main__":
    main()
