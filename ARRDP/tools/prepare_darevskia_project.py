from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a Darevskia gallery/query project.")
    parser.add_argument("--source-images", required=True, help="Flat source folder containing the original images.")
    parser.add_argument("--ranges", required=True, help="CSV with specimen_id,start_file,end_file.")
    parser.add_argument("--project-dir", required=True, help="Target project directory to create.")
    return parser.parse_args()


def parse_image_index(filename: str) -> int:
    digits = "".join(ch for ch in Path(filename).stem if ch.isdigit())
    if not digits:
        raise ValueError(f"Could not parse image index from '{filename}'")
    return int(digits)


def load_ranges(ranges_csv: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with ranges_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "specimen_id": str(row["specimen_id"]).strip(),
                    "start_index": parse_image_index(row["start_file"]),
                    "end_index": parse_image_index(row["end_file"]),
                }
            )
    return rows


def collect_images(source_dir: Path) -> list[Path]:
    images = [path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    return sorted(images, key=lambda path: parse_image_index(path.name))


def assign_specimen(image_path: Path, ranges: list[dict[str, object]]) -> str:
    index = parse_image_index(image_path.name)
    for record in ranges:
        if record["start_index"] <= index <= record["end_index"]:
            return str(record["specimen_id"])
    raise ValueError(f"Image {image_path.name} does not belong to any configured specimen range.")


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_images)
    ranges_csv = Path(args.ranges)
    project_dir = Path(args.project_dir)

    gallery_dir = project_dir / "gallery"
    query_dir = project_dir / "query"
    config_dir = project_dir / "config"
    outputs_dir = project_dir / "outputs"

    for path in (gallery_dir, query_dir, config_dir, outputs_dir):
        path.mkdir(parents=True, exist_ok=True)

    ranges = load_ranges(ranges_csv)
    images = collect_images(source_dir)
    grouped: dict[str, list[Path]] = {}
    for image_path in images:
        grouped.setdefault(assign_specimen(image_path, ranges), []).append(image_path)

    manifest_rows: list[dict[str, str]] = []
    for specimen_id, specimen_images in sorted(grouped.items(), key=lambda item: int(item[0])):
        specimen_images = sorted(specimen_images, key=lambda path: parse_image_index(path.name))
        if len(specimen_images) < 2:
            raise ValueError(f"Specimen {specimen_id} has fewer than 2 images.")

        query_image = specimen_images[-1]
        gallery_images = specimen_images[:-1]
        gallery_specimen_dir = gallery_dir / f"specimen_{specimen_id}"
        query_specimen_dir = query_dir / f"specimen_{specimen_id}"
        gallery_specimen_dir.mkdir(parents=True, exist_ok=True)
        query_specimen_dir.mkdir(parents=True, exist_ok=True)

        for image_path in gallery_images:
            target = gallery_specimen_dir / image_path.name
            shutil.copy2(image_path, target)
            manifest_rows.append(
                {
                    "specimen_id": specimen_id,
                    "split": "gallery",
                    "relative_path": str(target.relative_to(project_dir)),
                    "source_file": image_path.name,
                }
            )

        query_target = query_specimen_dir / query_image.name
        shutil.copy2(query_image, query_target)
        manifest_rows.append(
            {
                "specimen_id": specimen_id,
                "split": "query",
                "relative_path": str(query_target.relative_to(project_dir)),
                "source_file": query_image.name,
            }
        )

    manifest_path = config_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["specimen_id", "split", "relative_path", "source_file"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    shutil.copy2(ranges_csv, config_dir / "specimen_ranges.csv")
    settings = {
        "query_policy": "last_image_of_each_specimen",
        "expected_structure": {
            "gallery": "One subfolder per specimen with reference images.",
            "query": "One subfolder per specimen with a single recapture image.",
            "outputs": "Program results are written here.",
        },
    }
    with (config_dir / "settings.json").open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)

    summary = {
        "project_dir": str(project_dir),
        "source_dir": str(source_dir),
        "n_total_images": len(images),
        "n_gallery_images": sum(1 for row in manifest_rows if row["split"] == "gallery"),
        "n_query_images": sum(1 for row in manifest_rows if row["split"] == "query"),
        "n_specimens": len(grouped),
        "manifest_path": str(manifest_path),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
