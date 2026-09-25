from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from darevskia_axis_belt_matcher import (  # noqa: E402
    ensure_dirs as ensure_matcher_dirs,
    load_landmarks,
    preprocess_belt_feature,
)
from darevskia_spot_matcher import (  # noqa: E402
    ManifestRecord,
    SpotFeature,
    infer_records,
    make_spot_outline_preview_bgr,
    split_records,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate dorsal-pattern variability from 5-point curved belts: build consensus images, quantify deviation from consensus, and estimate left-right asymmetry."
    )
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--landmarks", help="CSV containing 5-point axis landmarks. Defaults to project_dir/config/axis_belt_landmarks.csv.")
    parser.add_argument("--output", help="Output folder. Defaults to project_dir/outputs/pattern_variation_run.")
    parser.add_argument("--include-split", choices=("gallery", "query", "both"), default="both", help="Which project split(s) to include in the analysis.")
    parser.add_argument("--max-side", type=int, default=2200, help="Resize the longest image side to at most this value before building the belt.")
    parser.add_argument("--preview-side", type=int, default=900, help="Save belt previews with this longest-side cap.")
    parser.add_argument("--thumb-size", type=int, default=256, help="Low-resolution internal size kept for compatibility with the belt extractor.")
    parser.add_argument("--belt-width", type=int, default=360, help="Width of the standardized belt image in pixels.")
    parser.add_argument("--belt-height", type=int, default=900, help="Height of the standardized belt image in pixels.")
    parser.add_argument("--belt-breadth-fraction", type=float, default=0.14, help="Belt breadth as a fraction of the full axis length in the source image.")
    parser.add_argument("--belt-breadth-px", type=float, default=None, help="Optional absolute belt breadth in source-image pixels. Overrides belt-breadth-fraction.")
    parser.add_argument("--inner-margin", type=float, default=0.03, help="Fraction to trim from each side of the standardized belt to avoid boundary noise.")
    parser.add_argument("--max-specimens", type=int, default=None, help="Optional cap on the number of specimens included, in manifest/specimen order.")
    parser.add_argument("--gallery-per-specimen", type=int, default=4, help="Optional cap on gallery images per specimen.")
    parser.add_argument("--gallery-sampling", choices=("first", "spaced", "last"), default="last", help="How to sample gallery images when gallery_per_specimen is smaller than the available images.")
    parser.add_argument("--query-per-specimen", type=int, default=1, help="Optional cap on query images per specimen.")
    parser.add_argument("--max-gallery", type=int, default=None, help="Optional cap on gallery image count after per-specimen sampling.")
    parser.add_argument("--max-query", type=int, default=None, help="Optional cap on query image count after per-specimen sampling.")
    return parser.parse_args()


def ensure_dirs(base_output: Path) -> dict[str, Path]:
    mapping = ensure_matcher_dirs(base_output)
    extras = {
        "consensus": base_output / "consensus",
        "deviation": base_output / "deviation",
        "asymmetry": base_output / "asymmetry",
        "specimens": base_output / "specimens",
    }
    for path in extras.values():
        path.mkdir(parents=True, exist_ok=True)
    mapping.update(extras)
    return mapping


def select_records(args: argparse.Namespace) -> list[ManifestRecord]:
    project_dir = Path(args.project_dir)
    manifest_path = Path(args.manifest) if args.manifest else None
    source_dir = Path(args.source_images) if args.source_images else None
    records = infer_records(project_dir, manifest_path, source_dir)
    gallery_records, query_records = split_records(
        records,
        args.max_gallery,
        args.max_query,
        args.max_specimens,
        args.gallery_per_specimen,
        args.gallery_sampling,
        args.query_per_specimen,
    )
    selected: list[ManifestRecord] = []
    if args.include_split in {"gallery", "both"}:
        for specimen_id in sorted(gallery_records.keys(), key=lambda value: (len(value), value)):
            selected.extend(gallery_records[specimen_id])
    if args.include_split in {"query", "both"}:
        for specimen_id in sorted(query_records.keys(), key=lambda value: (len(value), value)):
            selected.extend(query_records[specimen_id])
    return selected


def feature_mask(feature: SpotFeature) -> np.ndarray:
    mask = np.any(feature.preview_bgr > 0, axis=2).astype(np.uint8) * 255
    if mask.shape != feature.spot_binary.shape:
        mask = cv2.resize(mask, (feature.spot_binary.shape[1], feature.spot_binary.shape[0]), interpolation=cv2.INTER_NEAREST)
    mask[feature.spot_binary > 0] = 255
    return mask


def normalize_masked_map(spot_map: np.ndarray, mask: np.ndarray) -> np.ndarray:
    masked = mask > 0
    normalized = np.zeros_like(spot_map, dtype=np.float32)
    if np.count_nonzero(masked) < 16:
        return normalized
    values = spot_map.astype(np.float32)[masked]
    low = float(np.percentile(values, 2))
    high = float(np.percentile(values, 98))
    scale = max(1e-6, high - low)
    normalized = np.clip((spot_map.astype(np.float32) - low) / scale, 0.0, 1.0)
    normalized[~masked] = 0.0
    return normalized


def save_grayscale_map(path: Path, data: np.ndarray, mask: np.ndarray) -> None:
    mask_bool = mask > 0
    canvas = np.zeros_like(data, dtype=np.uint8)
    if np.count_nonzero(mask_bool) > 0:
        values = data[mask_bool]
        low = float(values.min())
        high = float(values.max())
        scale = max(1e-6, high - low)
        normalized = np.clip((data - low) / scale, 0.0, 1.0)
        canvas = (normalized * 255.0).astype(np.uint8)
        canvas[~mask_bool] = 0
    cv2.imwrite(str(path), cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR))


def save_heatmap(path: Path, data: np.ndarray, mask: np.ndarray) -> None:
    mask_bool = mask > 0
    canvas = np.zeros_like(data, dtype=np.uint8)
    if np.count_nonzero(mask_bool) > 0:
        values = data[mask_bool]
        high = max(1e-6, float(values.max()))
        normalized = np.clip(data / high, 0.0, 1.0)
        canvas = (normalized * 255.0).astype(np.uint8)
        canvas[~mask_bool] = 0
    color = cv2.applyColorMap(canvas, cv2.COLORMAP_TURBO)
    color[~mask_bool] = (0, 0, 0)
    cv2.imwrite(str(path), color)


def binary_distance(binary_image: np.ndarray, binary_reference: np.ndarray, mask: np.ndarray) -> float:
    mask_bool = mask > 0
    if np.count_nonzero(mask_bool) < 16:
        return 1.0
    a = (binary_image > 0).astype(np.float32)
    b = binary_reference.astype(np.float32)
    return float(np.mean(np.abs(a[mask_bool] - b[mask_bool])))


def corr01(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    mask_bool = mask > 0
    if np.count_nonzero(mask_bool) < 64:
        return 0.0
    av = a[mask_bool].astype(np.float32)
    bv = b[mask_bool].astype(np.float32)
    if float(np.std(av)) < 1e-6 or float(np.std(bv)) < 1e-6:
        return 0.0
    corr = np.corrcoef(av, bv)[0, 1]
    if np.isnan(corr):
        return 0.0
    return float((corr + 1.0) / 2.0)


def asymmetry_metrics(norm_map: np.ndarray, binary_image: np.ndarray, mask: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    height, width = norm_map.shape
    half = width // 2
    if half < 8:
        return 1.0, 0.0, 1.0, np.zeros_like(norm_map, dtype=np.float32)
    left_map = norm_map[:, :half]
    right_map = np.fliplr(norm_map[:, width - half :])
    left_bin = (binary_image[:, :half] > 0).astype(np.float32)
    right_bin = np.fliplr((binary_image[:, width - half :] > 0).astype(np.float32))
    left_mask = mask[:, :half]
    right_mask = np.fliplr(mask[:, width - half :])
    overlap = ((left_mask > 0) & (right_mask > 0)).astype(np.uint8) * 255
    correlation = corr01(left_map, right_map, overlap)
    binary_gap = binary_distance((left_bin * 255).astype(np.uint8), right_bin, overlap)
    asymmetry = float((0.6 * (1.0 - correlation)) + (0.4 * binary_gap))
    diff_half = np.abs(left_map - right_map) * (overlap > 0)
    diff_full = np.zeros_like(norm_map, dtype=np.float32)
    diff_full[:, :half] = diff_half
    diff_full[:, width - half :] = np.fliplr(diff_half)
    return asymmetry, correlation, binary_gap, diff_full


def write_summary_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    output_dir = Path(args.output) if args.output else (project_dir / "outputs" / "pattern_variation_run")
    output_dirs = ensure_dirs(output_dir)

    landmarks_path = Path(args.landmarks) if args.landmarks else (project_dir / "config" / "axis_belt_landmarks.csv")
    landmarks = load_landmarks(landmarks_path)
    selected_records = select_records(args)
    if not selected_records:
        raise ValueError("No images were selected for pattern-variation analysis.")

    features: list[SpotFeature] = []
    missing_landmarks: list[str] = []
    for record in selected_records:
        landmark_entry = landmarks.get(record.relative_path.replace("/", "\\"))
        if landmark_entry is None:
            missing_landmarks.append(record.relative_path)
            continue
        feature = preprocess_belt_feature(
            record=record,
            landmark_entry=landmark_entry,
            output_dirs=output_dirs,
            max_side=args.max_side,
            preview_side=args.preview_side,
            thumb_size=args.thumb_size,
            belt_width=args.belt_width,
            belt_height=args.belt_height,
            belt_breadth_fraction=args.belt_breadth_fraction,
            belt_breadth_px_override=args.belt_breadth_px,
            inner_margin=args.inner_margin,
        )
        features.append(feature)

    if not features:
        raise ValueError("No selected images had usable 5-point landmarks.")

    first_shape = features[0].spot_map.shape
    sum_map = np.zeros(first_shape, dtype=np.float32)
    sum_binary = np.zeros(first_shape, dtype=np.float32)
    sum_mask = np.zeros(first_shape, dtype=np.float32)

    normalized_maps: dict[str, np.ndarray] = {}
    masks: dict[str, np.ndarray] = {}
    for feature in features:
        mask = feature_mask(feature)
        norm_map = normalize_masked_map(feature.spot_map, mask)
        normalized_maps[feature.relative_path] = norm_map
        masks[feature.relative_path] = mask
        mask_float = (mask > 0).astype(np.float32)
        sum_map += norm_map * mask_float
        sum_binary += (feature.spot_binary > 0).astype(np.float32) * mask_float
        sum_mask += mask_float

    consensus_mask = np.where(sum_mask > 0.5, 255, 0).astype(np.uint8)
    consensus_map = np.divide(sum_map, sum_mask, out=np.zeros_like(sum_map), where=sum_mask > 0)
    consensus_binary_freq = np.divide(sum_binary, sum_mask, out=np.zeros_like(sum_binary), where=sum_mask > 0)
    consensus_binary = np.where(consensus_binary_freq >= 0.5, 255, 0).astype(np.uint8)

    mean_abs_diff = np.zeros(first_shape, dtype=np.float32)
    image_rows: list[dict[str, object]] = []

    specimen_binary_sum: dict[str, np.ndarray] = {}
    specimen_map_sum: dict[str, np.ndarray] = {}
    specimen_mask_sum: dict[str, np.ndarray] = {}
    specimen_counts: dict[str, int] = {}

    for feature in features:
        relative_path = feature.relative_path
        mask = masks[relative_path]
        norm_map = normalized_maps[relative_path]
        mask_bool = mask > 0
        abs_diff = np.abs(norm_map - consensus_map) * mask_bool
        mean_abs_diff += abs_diff

        map_similarity = corr01(norm_map, consensus_map, mask)
        binary_gap = binary_distance(feature.spot_binary, consensus_binary_freq, mask)
        deviation_score = float((0.6 * (1.0 - map_similarity)) + (0.4 * binary_gap))
        asymmetry_score, asym_corr, asym_binary_gap, asym_diff = asymmetry_metrics(norm_map, feature.spot_binary, mask)

        deviation_path = output_dirs["deviation"] / feature.split / f"specimen_{feature.specimen_id}" / f"{feature.image_path.stem}_deviation.png"
        asymmetry_path = output_dirs["asymmetry"] / feature.split / f"specimen_{feature.specimen_id}" / f"{feature.image_path.stem}_asymmetry.png"
        deviation_path.parent.mkdir(parents=True, exist_ok=True)
        asymmetry_path.parent.mkdir(parents=True, exist_ok=True)
        save_heatmap(deviation_path, abs_diff, mask)
        save_heatmap(asymmetry_path, asym_diff, mask)

        image_rows.append(
            {
                "specimen_id": feature.specimen_id,
                "split": feature.split,
                "relative_path": feature.relative_path,
                "image_file": feature.image_path.name,
                "deviation_score": round(deviation_score, 6),
                "consensus_map_similarity": round(map_similarity, 6),
                "consensus_binary_distance": round(binary_gap, 6),
                "asymmetry_score": round(asymmetry_score, 6),
                "left_right_map_similarity": round(asym_corr, 6),
                "left_right_binary_distance": round(asym_binary_gap, 6),
                "quality_flag": feature.quality_flag,
                "belt_file": str(feature.preview_path),
                "spots_file": str(feature.spot_path),
                "deviation_file": str(deviation_path),
                "asymmetry_file": str(asymmetry_path),
            }
        )

        specimen_binary_sum.setdefault(feature.specimen_id, np.zeros(first_shape, dtype=np.float32))
        specimen_map_sum.setdefault(feature.specimen_id, np.zeros(first_shape, dtype=np.float32))
        specimen_mask_sum.setdefault(feature.specimen_id, np.zeros(first_shape, dtype=np.float32))
        specimen_counts.setdefault(feature.specimen_id, 0)
        mask_float = (mask > 0).astype(np.float32)
        specimen_binary_sum[feature.specimen_id] += (feature.spot_binary > 0).astype(np.float32) * mask_float
        specimen_map_sum[feature.specimen_id] += norm_map * mask_float
        specimen_mask_sum[feature.specimen_id] += mask_float
        specimen_counts[feature.specimen_id] += 1

    mean_abs_diff = np.divide(mean_abs_diff, sum_mask, out=np.zeros_like(mean_abs_diff), where=sum_mask > 0)

    consensus_dir = output_dirs["consensus"]
    save_grayscale_map(consensus_dir / "consensus_pattern.png", consensus_map, consensus_mask)
    save_heatmap(consensus_dir / "consensus_spot_frequency.png", consensus_binary_freq, consensus_mask)
    cv2.imwrite(str(consensus_dir / "consensus_outline.png"), make_spot_outline_preview_bgr(consensus_binary, consensus_mask))
    save_heatmap(consensus_dir / "mean_absolute_deviation.png", mean_abs_diff, consensus_mask)

    specimen_preview_rows: list[dict[str, object]] = []
    for specimen_id in sorted(specimen_counts.keys(), key=lambda value: (len(value), value)):
        specimen_mask = np.where(specimen_mask_sum[specimen_id] > 0.5, 255, 0).astype(np.uint8)
        specimen_map = np.divide(
            specimen_map_sum[specimen_id],
            specimen_mask_sum[specimen_id],
            out=np.zeros_like(specimen_map_sum[specimen_id]),
            where=specimen_mask_sum[specimen_id] > 0,
        )
        specimen_binary_freq = np.divide(
            specimen_binary_sum[specimen_id],
            specimen_mask_sum[specimen_id],
            out=np.zeros_like(specimen_binary_sum[specimen_id]),
            where=specimen_mask_sum[specimen_id] > 0,
        )
        specimen_binary = np.where(specimen_binary_freq >= 0.5, 255, 0).astype(np.uint8)
        specimen_dir = output_dirs["specimens"] / f"specimen_{specimen_id}"
        specimen_dir.mkdir(parents=True, exist_ok=True)
        pattern_path = specimen_dir / "mean_pattern.png"
        outline_path = specimen_dir / "mean_outline.png"
        frequency_path = specimen_dir / "spot_frequency.png"
        save_grayscale_map(pattern_path, specimen_map, specimen_mask)
        cv2.imwrite(str(outline_path), make_spot_outline_preview_bgr(specimen_binary, specimen_mask))
        save_heatmap(frequency_path, specimen_binary_freq, specimen_mask)
        specimen_preview_rows.append(
            {
                "specimen_id": specimen_id,
                "n_images": specimen_counts[specimen_id],
                "mean_pattern_file": str(pattern_path),
                "mean_outline_file": str(outline_path),
                "spot_frequency_file": str(frequency_path),
            }
        )

    image_df = pd.DataFrame(image_rows).sort_values(["specimen_id", "split", "relative_path"]).reset_index(drop=True)
    specimen_stats = (
        image_df.groupby("specimen_id", as_index=False)
        .agg(
            n_images=("relative_path", "count"),
            mean_deviation_score=("deviation_score", "mean"),
            sd_deviation_score=("deviation_score", "std"),
            mean_consensus_map_similarity=("consensus_map_similarity", "mean"),
            mean_consensus_binary_distance=("consensus_binary_distance", "mean"),
            mean_asymmetry_score=("asymmetry_score", "mean"),
            sd_asymmetry_score=("asymmetry_score", "std"),
            mean_left_right_map_similarity=("left_right_map_similarity", "mean"),
            mean_left_right_binary_distance=("left_right_binary_distance", "mean"),
        )
        .fillna(0.0)
        .sort_values("specimen_id")
        .reset_index(drop=True)
    )
    specimen_preview_df = pd.DataFrame(specimen_preview_rows).sort_values("specimen_id").reset_index(drop=True)
    specimen_df = specimen_stats.merge(specimen_preview_df, on=["specimen_id", "n_images"], how="left")

    image_csv = output_dir / "image_variation.csv"
    specimen_csv = output_dir / "specimen_variation.csv"
    image_df.to_csv(image_csv, index=False)
    specimen_df.to_csv(specimen_csv, index=False)

    split_counts = image_df["split"].value_counts().to_dict()
    most_deviant = image_df.sort_values("deviation_score", ascending=False).iloc[0].to_dict()
    most_asymmetric = image_df.sort_values("asymmetry_score", ascending=False).iloc[0].to_dict()
    summary = {
        "mode": "pattern_variation",
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "landmarks": str(landmarks_path),
        "include_split": args.include_split,
        "n_selected_records": len(selected_records),
        "n_processed_images": int(len(features)),
        "n_missing_landmarks": int(len(missing_landmarks)),
        "n_specimens": int(image_df["specimen_id"].nunique()),
        "split_counts": split_counts,
        "belt_breadth_fraction": args.belt_breadth_fraction,
        "belt_breadth_px": args.belt_breadth_px,
        "mean_deviation_score": round(float(image_df["deviation_score"].mean()), 6),
        "mean_asymmetry_score": round(float(image_df["asymmetry_score"].mean()), 6),
        "median_deviation_score": round(float(image_df["deviation_score"].median()), 6),
        "median_asymmetry_score": round(float(image_df["asymmetry_score"].median()), 6),
        "most_deviant_image": most_deviant,
        "most_asymmetric_image": most_asymmetric,
        "consensus_files": {
            "consensus_pattern": str(consensus_dir / "consensus_pattern.png"),
            "consensus_outline": str(consensus_dir / "consensus_outline.png"),
            "consensus_spot_frequency": str(consensus_dir / "consensus_spot_frequency.png"),
            "mean_absolute_deviation": str(consensus_dir / "mean_absolute_deviation.png"),
        },
        "outputs": {
            "image_variation_csv": str(image_csv),
            "specimen_variation_csv": str(specimen_csv),
            "belt_dir": str(output_dirs["belt"]),
            "spots_dir": str(output_dirs["spots"]),
            "overlay_dir": str(output_dirs["overlay"]),
            "consensus_dir": str(output_dirs["consensus"]),
            "deviation_dir": str(output_dirs["deviation"]),
            "asymmetry_dir": str(output_dirs["asymmetry"]),
            "specimens_dir": str(output_dirs["specimens"]),
        },
    }
    write_summary_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
