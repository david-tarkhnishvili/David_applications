#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import mimetypes
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
PORTABLE_TOOLS_DIR = SCRIPT_DIR / "tools"
PORTABLE_PROJECT_DIR = SCRIPT_DIR.parent if PORTABLE_TOOLS_DIR.exists() else None
TOOLS_DIR = PORTABLE_TOOLS_DIR if PORTABLE_TOOLS_DIR.exists() else (PROJECT_ROOT / "darevskia_id")

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from annotate_neck_patch import (  # noqa: E402
    filter_records as annotation_filter_records,
    infer_records as annotation_infer_records,
    load_existing_annotations,
    sample_annotation_records,
)
from darevskia_spot_matcher import infer_records as matcher_infer_records, split_records  # noqa: E402


ANNOTATOR_PATH = TOOLS_DIR / "annotate_neck_patch.py"
AXIS_BELT_PATH = TOOLS_DIR / "darevskia_axis_belt_matcher.py"
PATTERN_VARIATION_PATH = TOOLS_DIR / "darevskia_pattern_variation.py"
TRIPOINT_PATH = TOOLS_DIR / "darevskia_tripoint_spot_matcher.py"
QUAD_PATH = TOOLS_DIR / "darevskia_quad_spot_matcher.py"
MANUAL_PATH = TOOLS_DIR / "USER_MANUAL.md"
SPEC_PATH = TOOLS_DIR / "WEB_APP_SPEC.md"
VARIATION_MANUAL_PATH = TOOLS_DIR / "PATTERN_VARIATION_README.md"

WEB_RUNS_DIR = SCRIPT_DIR / "web_runs"
JOBS_DIR = WEB_RUNS_DIR / "jobs"
RUNS_DIR = WEB_RUNS_DIR / "runs"

DEFAULT_PROJECT_DIR = str(PORTABLE_PROJECT_DIR) if PORTABLE_PROJECT_DIR else r"E:\Darevskia_ID"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8094

JOB_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Any]] = {}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_directories() -> None:
    for path in (WEB_RUNS_DIR, JOBS_DIR, RUNS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def job_json_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def save_job(job: dict[str, Any]) -> None:
    with JOB_LOCK:
        JOBS[job["id"]] = job
        job_json_path(job["id"]).write_text(json.dumps(job, indent=2), encoding="utf-8")


def update_job(job_id: str, **changes: Any) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(changes)
        job_json_path(job_id).write_text(json.dumps(job, indent=2), encoding="utf-8")


def get_job(job_id: str) -> dict[str, Any] | None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        return json.loads(json.dumps(job))


def list_jobs() -> list[dict[str, Any]]:
    with JOB_LOCK:
        jobs = list(JOBS.values())
    return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)


def load_jobs() -> None:
    ensure_directories()
    with JOB_LOCK:
        JOBS.clear()
        for path in sorted(JOBS_DIR.glob("*.json")):
            try:
                JOBS[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local web app for Darevskia ID workflows.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind.")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open a browser tab.")
    return parser.parse_args()


def parse_request_form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def coerce_int(value: str, default: int | None = None) -> int | None:
    value = (value or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except Exception:
        return default


def checkbox_value(fields: dict[str, str], name: str) -> str:
    return "true" if fields.get(name) in {"on", "true", "1"} else "false"


def parse_specimen_text(text: str) -> list[str]:
    raw = [item.strip() for item in (text or "").replace(";", ",").split(",")]
    return [item for item in raw if item]


def normalize_path_text(text: str) -> str:
    return str(Path(text).expanduser()) if (text or "").strip() else ""


def collect_annotation_options(fields: dict[str, str]) -> dict[str, str]:
    return {
        "project_dir": normalize_path_text(fields.get("annotation_project_dir") or DEFAULT_PROJECT_DIR),
        "manifest": normalize_path_text(fields.get("annotation_manifest") or ""),
        "source_images": normalize_path_text(fields.get("annotation_source_images") or ""),
        "output_csv": normalize_path_text(fields.get("annotation_output_csv") or ""),
        "split": (fields.get("annotation_split") or "gallery").strip() or "gallery",
        "specimens": ",".join(parse_specimen_text(fields.get("annotation_specimens") or "")),
        "max_images": (fields.get("annotation_max_images") or "").strip(),
        "max_specimens": (fields.get("annotation_max_specimens") or "").strip(),
        "gallery_per_specimen": (fields.get("annotation_gallery_per_specimen") or "4").strip(),
        "gallery_sampling": (fields.get("annotation_gallery_sampling") or "last").strip() or "last",
        "query_per_specimen": (fields.get("annotation_query_per_specimen") or "1").strip(),
        "point_count": (fields.get("annotation_point_count") or "5").strip(),
        "window_width": (fields.get("annotation_window_width") or "1600").strip(),
        "window_height": (fields.get("annotation_window_height") or "950").strip(),
        "display_mode": (fields.get("annotation_display_mode") or "viewer").strip() or "viewer",
        "overwrite": checkbox_value(fields, "annotation_overwrite"),
    }


def collect_match_options(fields: dict[str, str]) -> dict[str, str]:
    return {
        "project_dir": normalize_path_text(fields.get("match_project_dir") or DEFAULT_PROJECT_DIR),
        "manifest": normalize_path_text(fields.get("match_manifest") or ""),
        "source_images": normalize_path_text(fields.get("match_source_images") or ""),
        "landmarks": normalize_path_text(fields.get("match_landmarks") or ""),
        "output_dir": normalize_path_text(fields.get("match_output_dir") or ""),
        "matcher_mode": (fields.get("matcher_mode") or "axis_belt").strip() or "axis_belt",
        "max_specimens": (fields.get("match_max_specimens") or "").strip(),
        "gallery_per_specimen": (fields.get("match_gallery_per_specimen") or "4").strip(),
        "gallery_sampling": (fields.get("match_gallery_sampling") or "last").strip() or "last",
        "query_per_specimen": (fields.get("match_query_per_specimen") or "1").strip(),
        "max_gallery": (fields.get("match_max_gallery") or "").strip(),
        "max_query": (fields.get("match_max_query") or "").strip(),
        "thumb_size": (fields.get("match_thumb_size") or "256").strip(),
        "preview_side": (fields.get("match_preview_side") or "900").strip(),
        "max_side": (fields.get("match_max_side") or "2200").strip(),
        "belt_width": (fields.get("match_belt_width") or "360").strip(),
        "belt_height": (fields.get("match_belt_height") or "900").strip(),
        "belt_breadth_fraction": (fields.get("match_belt_breadth_fraction") or "0.14").strip(),
        "belt_breadth_px": (fields.get("match_belt_breadth_px") or "").strip(),
        "consensus_top_k": (fields.get("match_consensus_top_k") or "2").strip(),
        "window_width": (fields.get("match_window_width") or "360").strip(),
        "window_height": (fields.get("match_window_height") or "520").strip(),
        "window_length_fraction": (fields.get("match_window_length_fraction") or "0.30").strip(),
        "window_width_fraction": (fields.get("match_window_width_fraction") or "0.18").strip(),
        "inner_margin": (fields.get("match_inner_margin") or "0.03").strip(),
        "allow_new_specimen": checkbox_value(fields, "match_allow_new_specimen"),
        "new_specimen_threshold": (fields.get("match_new_specimen_threshold") or "0.20").strip(),
        "new_specimen_margin": (fields.get("match_new_specimen_margin") or "0.035").strip(),
    }


def collect_variation_options(fields: dict[str, str]) -> dict[str, str]:
    return {
        "project_dir": normalize_path_text(fields.get("variation_project_dir") or DEFAULT_PROJECT_DIR),
        "manifest": normalize_path_text(fields.get("variation_manifest") or ""),
        "source_images": normalize_path_text(fields.get("variation_source_images") or ""),
        "landmarks": normalize_path_text(fields.get("variation_landmarks") or ""),
        "output_dir": normalize_path_text(fields.get("variation_output_dir") or ""),
        "include_split": (fields.get("variation_include_split") or "both").strip() or "both",
        "max_specimens": (fields.get("variation_max_specimens") or "12").strip(),
        "gallery_per_specimen": (fields.get("variation_gallery_per_specimen") or "4").strip(),
        "gallery_sampling": (fields.get("variation_gallery_sampling") or "last").strip() or "last",
        "query_per_specimen": (fields.get("variation_query_per_specimen") or "1").strip(),
        "max_gallery": (fields.get("variation_max_gallery") or "").strip(),
        "max_query": (fields.get("variation_max_query") or "").strip(),
        "thumb_size": (fields.get("variation_thumb_size") or "256").strip(),
        "preview_side": (fields.get("variation_preview_side") or "900").strip(),
        "max_side": (fields.get("variation_max_side") or "2200").strip(),
        "belt_width": (fields.get("variation_belt_width") or "360").strip(),
        "belt_height": (fields.get("variation_belt_height") or "900").strip(),
        "belt_breadth_fraction": (fields.get("variation_belt_breadth_fraction") or "0.14").strip(),
        "belt_breadth_px": (fields.get("variation_belt_breadth_px") or "").strip(),
        "inner_margin": (fields.get("variation_inner_margin") or "0.03").strip(),
    }


def collect_distance_options(fields: dict[str, str]) -> dict[str, str]:
    return {
        "project_dir": normalize_path_text(fields.get("distance_project_dir") or DEFAULT_PROJECT_DIR),
        "input_csv": normalize_path_text(fields.get("distance_input_csv") or ""),
        "output_dir": normalize_path_text(fields.get("distance_output_dir") or ""),
        "source": (fields.get("distance_source") or "mean_pattern").strip() or "mean_pattern",
        "metric": (fields.get("distance_metric") or "euclidean").strip() or "euclidean",
        "standardize": checkbox_value(fields, "distance_standardize"),
        "image_width": (fields.get("distance_image_width") or "90").strip(),
        "image_height": (fields.get("distance_image_height") or "240").strip(),
    }


def default_annotation_csv(project_dir: str, point_count: int) -> str:
    project_path = Path(project_dir)
    filename = {
        3: "tripoint_landmarks.csv",
        4: "dorsal_quad_landmarks.csv",
        5: "axis_belt_landmarks.csv",
    }.get(point_count, f"landmarks_{point_count}pt.csv")
    return str(project_path / "config" / filename)


def default_output_dir(project_dir: str, matcher_mode: str) -> str:
    project_path = Path(project_dir)
    folder = {
        "axis_belt": "axis_belt_web_run",
        "tripoint": "tripoint_web_run",
        "quad": "quad_web_run",
    }.get(matcher_mode, "darevskia_web_run")
    return str(project_path / "outputs" / folder)


def default_variation_output_dir(project_dir: str) -> str:
    return str(Path(project_dir) / "outputs" / "pattern_variation_web_run")


def default_distance_input_csv(project_dir: str) -> str:
    return str(Path(default_variation_output_dir(project_dir)) / "specimen_variation.csv")


def default_distance_output_dir(project_dir: str) -> str:
    return str(Path(project_dir) / "outputs" / "distance_tree_web_run")


def create_job(*, job_type: str, label: str, project_dir: str, options: dict[str, str]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    log_path = RUNS_DIR / f"{job_id}.log"
    job = {
        "id": job_id,
        "type": job_type,
        "label": label,
        "status": "queued",
        "created_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "project_dir": project_dir,
        "options": options,
        "log_path": str(log_path),
        "return_code": None,
        "command": [],
        "progress": 0.0,
        "progress_text": "",
        "summary": {},
        "error_message": None,
        "output_dir": options.get("output_dir", ""),
    }
    save_job(job)
    return job


def build_annotation_command(job: dict[str, Any]) -> list[str]:
    options = job["options"]
    command = [
        sys.executable,
        "-B",
        str(ANNOTATOR_PATH),
        "--project-dir",
        options["project_dir"],
        "--point-count",
        options["point_count"],
        "--split",
        options["split"],
        "--gallery-sampling",
        options["gallery_sampling"],
        "--display-mode",
        options["display_mode"],
        "--window-width",
        options["window_width"],
        "--window-height",
        options["window_height"],
    ]
    if options.get("manifest"):
        command.extend(["--manifest", options["manifest"]])
    if options.get("source_images"):
        command.extend(["--source-images", options["source_images"]])
    if options.get("output_csv"):
        command.extend(["--output-csv", options["output_csv"]])
    if options.get("specimens"):
        for specimen_id in parse_specimen_text(options["specimens"]):
            command.extend(["--specimen", specimen_id])
    if options.get("max_images"):
        command.extend(["--max-images", options["max_images"]])
    if options.get("max_specimens"):
        command.extend(["--max-specimens", options["max_specimens"]])
    if options.get("gallery_per_specimen"):
        command.extend(["--gallery-per-specimen", options["gallery_per_specimen"]])
    if options.get("query_per_specimen"):
        command.extend(["--query-per-specimen", options["query_per_specimen"]])
    if options.get("overwrite") == "true":
        command.append("--overwrite")
    return command


def build_match_command(job: dict[str, Any]) -> list[str]:
    options = job["options"]
    matcher_mode = options["matcher_mode"]
    if matcher_mode == "tripoint":
        runner = TRIPOINT_PATH
    elif matcher_mode == "quad":
        runner = QUAD_PATH
    else:
        runner = AXIS_BELT_PATH

    command = [
        sys.executable,
        "-B",
        str(runner),
        "--project-dir",
        options["project_dir"],
        "--output",
        options["output_dir"],
        "--gallery-sampling",
        options["gallery_sampling"],
        "--thumb-size",
        options["thumb_size"],
        "--preview-side",
        options["preview_side"],
        "--max-side",
        options["max_side"],
        "--inner-margin",
        options["inner_margin"],
    ]
    if options.get("manifest"):
        command.extend(["--manifest", options["manifest"]])
    if options.get("source_images"):
        command.extend(["--source-images", options["source_images"]])
    if options.get("landmarks"):
        command.extend(["--landmarks", options["landmarks"]])
    if options.get("max_specimens"):
        command.extend(["--max-specimens", options["max_specimens"]])
    if options.get("gallery_per_specimen"):
        command.extend(["--gallery-per-specimen", options["gallery_per_specimen"]])
    if options.get("query_per_specimen"):
        command.extend(["--query-per-specimen", options["query_per_specimen"]])
    if options.get("max_gallery"):
        command.extend(["--max-gallery", options["max_gallery"]])
    if options.get("max_query"):
        command.extend(["--max-query", options["max_query"]])
    if options.get("allow_new_specimen") == "true":
        command.append("--allow-new-specimen")
    if options.get("new_specimen_threshold"):
        command.extend(["--new-specimen-threshold", options["new_specimen_threshold"]])
    if options.get("new_specimen_margin"):
        command.extend(["--new-specimen-margin", options["new_specimen_margin"]])

    if matcher_mode == "axis_belt":
        command.extend(
            [
                "--belt-width",
                options["belt_width"],
                "--belt-height",
                options["belt_height"],
                "--belt-breadth-fraction",
                options["belt_breadth_fraction"],
                "--consensus-top-k",
                options["consensus_top_k"],
            ]
        )
        if options.get("belt_breadth_px"):
            command.extend(["--belt-breadth-px", options["belt_breadth_px"]])
    elif matcher_mode == "tripoint":
        command.extend(
            [
                "--window-width",
                options["window_width"],
                "--window-height",
                options["window_height"],
                "--window-length-fraction",
                options["window_length_fraction"],
                "--window-width-fraction",
                options["window_width_fraction"],
            ]
        )
    return command


def build_variation_command(job: dict[str, Any]) -> list[str]:
    options = job["options"]
    command = [
        sys.executable,
        "-B",
        str(PATTERN_VARIATION_PATH),
        "--project-dir",
        options["project_dir"],
        "--output",
        options["output_dir"],
        "--include-split",
        options["include_split"],
        "--gallery-sampling",
        options["gallery_sampling"],
        "--thumb-size",
        options["thumb_size"],
        "--preview-side",
        options["preview_side"],
        "--max-side",
        options["max_side"],
        "--belt-width",
        options["belt_width"],
        "--belt-height",
        options["belt_height"],
        "--belt-breadth-fraction",
        options["belt_breadth_fraction"],
        "--inner-margin",
        options["inner_margin"],
    ]
    if options.get("manifest"):
        command.extend(["--manifest", options["manifest"]])
    if options.get("source_images"):
        command.extend(["--source-images", options["source_images"]])
    if options.get("landmarks"):
        command.extend(["--landmarks", options["landmarks"]])
    if options.get("max_specimens"):
        command.extend(["--max-specimens", options["max_specimens"]])
    if options.get("gallery_per_specimen"):
        command.extend(["--gallery-per-specimen", options["gallery_per_specimen"]])
    if options.get("query_per_specimen"):
        command.extend(["--query-per-specimen", options["query_per_specimen"]])
    if options.get("max_gallery"):
        command.extend(["--max-gallery", options["max_gallery"]])
    if options.get("max_query"):
        command.extend(["--max-query", options["max_query"]])
    if options.get("belt_breadth_px"):
        command.extend(["--belt-breadth-px", options["belt_breadth_px"]])
    return command


def safe_float(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def load_distance_vectors(options: dict[str, str]) -> tuple[list[str], list[list[float]], list[str]]:
    input_csv = Path(options["input_csv"])
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 2:
        raise ValueError("Distance analysis needs at least two specimens.")

    labels = [str(row.get("specimen_id") or f"row_{index + 1}") for index, row in enumerate(rows)]
    source = options.get("source") or "mean_pattern"
    feature_names: list[str] = []
    vectors: list[list[float]] = []

    if source == "summary_metrics":
        excluded = {"specimen_id", "n_images"}
        path_like = ("_file", "_path", "relative_path", "image_file")
        candidates = [
            name
            for name in (rows[0].keys() if rows else [])
            if name not in excluded and not any(token in name for token in path_like)
        ]
        for name in candidates:
            values = [safe_float(row.get(name)) for row in rows]
            if all(value is not None for value in values):
                feature_names.append(name)
        if not feature_names:
            raise ValueError("No numeric specimen-level metric columns were found.")
        vectors = [[float(row[name]) for name in feature_names] for row in rows]
        if options.get("standardize"):
            vectors = standardize_vectors(vectors)
        return labels, vectors, feature_names

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on local installation
        raise RuntimeError("Pillow is required for mean-pattern image distances.") from exc

    width = max(8, coerce_int(options.get("image_width"), 90) or 90)
    height = max(8, coerce_int(options.get("image_height"), 240) or 240)
    feature_names = [f"pixel_{index}" for index in range(width * height)]
    for row in rows:
        image_path = Path(row.get("mean_pattern_file") or "")
        if not image_path.exists():
            raise FileNotFoundError(f"Mean-pattern image not found for specimen {row.get('specimen_id')}: {image_path}")
        image = Image.open(image_path).convert("L").resize((width, height))
        vectors.append([pixel / 255.0 for pixel in image.getdata()])
    return labels, vectors, feature_names


def standardize_vectors(vectors: list[list[float]]) -> list[list[float]]:
    if not vectors:
        return vectors
    n_rows = len(vectors)
    n_cols = len(vectors[0])
    means = [sum(row[col] for row in vectors) / n_rows for col in range(n_cols)]
    scales: list[float] = []
    for col in range(n_cols):
        variance = sum((row[col] - means[col]) ** 2 for row in vectors) / max(1, n_rows - 1)
        scales.append(math.sqrt(variance) or 1.0)
    return [[(row[col] - means[col]) / scales[col] for col in range(n_cols)] for row in vectors]


def vector_distance(a: list[float], b: list[float], metric: str) -> float:
    if metric == "manhattan":
        return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))
    if metric == "correlation":
        mean_a = sum(a) / len(a)
        mean_b = sum(b) / len(b)
        centered_a = [x - mean_a for x in a]
        centered_b = [y - mean_b for y in b]
        denom = math.sqrt(sum(x * x for x in centered_a) * sum(y * y for y in centered_b))
        if denom == 0:
            return 0.0 if a == b else 1.0
        return max(0.0, min(2.0, 1.0 - (sum(x * y for x, y in zip(centered_a, centered_b)) / denom)))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / max(1, len(a)))


def compute_distance_matrix(vectors: list[list[float]], metric: str) -> list[list[float]]:
    size = len(vectors)
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for i in range(size):
        for j in range(i + 1, size):
            distance = vector_distance(vectors[i], vectors[j], metric)
            matrix[i][j] = distance
            matrix[j][i] = distance
    return matrix


def quote_newick_label(label: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in label.strip())
    return safe or "specimen"


def build_upgma_tree(labels: list[str], matrix: list[list[float]]) -> tuple[dict[str, Any], str]:
    clusters: dict[int, dict[str, Any]] = {
        index: {"members": [index], "height": 0.0, "label": labels[index], "newick": quote_newick_label(labels[index])}
        for index in range(len(labels))
    }
    next_id = len(labels)
    while len(clusters) > 1:
        keys = list(clusters)
        best_pair = (keys[0], keys[1])
        best_distance = float("inf")
        for left_pos, left_key in enumerate(keys):
            for right_key in keys[left_pos + 1 :]:
                left_members = clusters[left_key]["members"]
                right_members = clusters[right_key]["members"]
                distance = sum(matrix[i][j] for i in left_members for j in right_members) / (len(left_members) * len(right_members))
                if distance < best_distance:
                    best_distance = distance
                    best_pair = (left_key, right_key)
        left = clusters.pop(best_pair[0])
        right = clusters.pop(best_pair[1])
        height = best_distance / 2.0
        left_length = max(0.0, height - float(left["height"]))
        right_length = max(0.0, height - float(right["height"]))
        merged = {
            "members": left["members"] + right["members"],
            "height": height,
            "left": left,
            "right": right,
            "newick": f"({left['newick']}:{left_length:.6f},{right['newick']}:{right_length:.6f})",
        }
        clusters[next_id] = merged
        next_id += 1
    root = next(iter(clusters.values()))
    return root, f"{root['newick']};"


def tree_leaves(node: dict[str, Any]) -> list[dict[str, Any]]:
    if "label" in node:
        return [node]
    return tree_leaves(node["left"]) + tree_leaves(node["right"])


def render_tree_svg(root: dict[str, Any]) -> str:
    leaves = tree_leaves(root)
    leaf_gap = 34
    top = 24
    left = 36
    tree_width = 560
    label_x = left + tree_width + 14
    height = max(120, top * 2 + max(1, len(leaves) - 1) * leaf_gap)
    width = label_x + 220
    root_height = max(float(root.get("height", 0.0)), 1e-9)
    y_positions = {id(leaf): top + index * leaf_gap for index, leaf in enumerate(leaves)}

    def node_x(node: dict[str, Any]) -> float:
        return left + (root_height - float(node.get("height", 0.0))) / root_height * tree_width

    def node_y(node: dict[str, Any]) -> float:
        if "label" in node:
            return y_positions[id(node)]
        return (node_y(node["left"]) + node_y(node["right"])) / 2.0

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fffdfa"/>',
        '<g stroke="#1c2d3f" stroke-width="1.6" fill="none">',
    ]

    def draw_node(node: dict[str, Any]) -> None:
        if "label" in node:
            return
        x = node_x(node)
        y = node_y(node)
        children = [node["left"], node["right"]]
        child_ys = [node_y(child) for child in children]
        lines.append(f'<line x1="{x:.2f}" y1="{min(child_ys):.2f}" x2="{x:.2f}" y2="{max(child_ys):.2f}"/>')
        for child in children:
            cx = node_x(child)
            cy = node_y(child)
            lines.append(f'<line x1="{x:.2f}" y1="{cy:.2f}" x2="{cx:.2f}" y2="{cy:.2f}"/>')
            draw_node(child)

    draw_node(root)
    lines.append("</g>")
    lines.append('<g fill="#1c2d3f" font-family="Georgia, Times New Roman, serif" font-size="14">')
    for leaf in leaves:
        y = node_y(leaf)
        lines.append(f'<text x="{label_x}" y="{y + 5:.2f}">{html.escape(str(leaf["label"]))}</text>')
    lines.append("</g></svg>")
    return "\n".join(lines)


def write_distance_outputs(job: dict[str, Any]) -> dict[str, Any]:
    options = job["options"]
    output_dir = Path(options["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    labels, vectors, feature_names = load_distance_vectors(options)
    matrix = compute_distance_matrix(vectors, options.get("metric") or "euclidean")
    root, newick = build_upgma_tree(labels, matrix)

    matrix_path = output_dir / "distance_matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["specimen_id", *labels])
        for label, row in zip(labels, matrix):
            writer.writerow([label, *[f"{value:.8f}" for value in row]])

    newick_path = output_dir / "upgma_tree.newick"
    newick_path.write_text(newick + "\n", encoding="utf-8")
    svg_path = output_dir / "upgma_tree.svg"
    svg_path.write_text(render_tree_svg(root), encoding="utf-8")

    summary = {
        "mode": "distance_tree",
        "input_csv": options["input_csv"],
        "output_dir": str(output_dir),
        "source": options.get("source"),
        "metric": options.get("metric"),
        "standardize": bool(options.get("standardize")) if options.get("source") == "summary_metrics" else False,
        "n_specimens": len(labels),
        "n_features": len(feature_names),
        "distance_matrix_csv": str(matrix_path),
        "upgma_tree_newick": str(newick_path),
        "upgma_tree_svg": str(svg_path),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_distance_tree_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    log_path = Path(job["log_path"])
    update_job(job_id, status="running", started_at=utc_now(), progress=5.0, progress_text="Reading specimen data.")
    try:
        with log_path.open("w", encoding="utf-8", newline="\n") as log_handle:
            log_handle.write("Running in-process distance matrix and UPGMA tree analysis.\n\n")
            summary = write_distance_outputs(job)
            log_handle.write(json.dumps(summary, indent=2))
        update_job(
            job_id,
            status="completed",
            finished_at=utc_now(),
            return_code=0,
            summary=summary,
            progress=100.0,
            progress_text="Finished.",
            error_message=None,
        )
    except Exception as exc:
        with log_path.open("a", encoding="utf-8", newline="\n") as log_handle:
            log_handle.write("\n" + traceback.format_exc())
        update_job(job_id, status="failed", finished_at=utc_now(), return_code=1, progress=100.0, progress_text="Failed.", error_message=str(exc))


def project_status(project_dir_text: str) -> dict[str, Any]:
    project_dir = Path(project_dir_text)
    gallery_dir = project_dir / "gallery"
    query_dir = project_dir / "query"
    outputs_dir = project_dir / "outputs"
    gallery_images = sum(1 for path in gallery_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES) if gallery_dir.exists() else 0
    query_images = sum(1 for path in query_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES) if query_dir.exists() else 0
    gallery_specimens = sum(1 for path in gallery_dir.iterdir() if path.is_dir()) if gallery_dir.exists() else 0
    query_specimens = sum(1 for path in query_dir.iterdir() if path.is_dir()) if query_dir.exists() else 0
    return {
        "exists": project_dir.exists(),
        "gallery_dir": str(gallery_dir),
        "query_dir": str(query_dir),
        "outputs_dir": str(outputs_dir),
        "gallery_images": gallery_images,
        "query_images": query_images,
        "gallery_specimens": gallery_specimens,
        "query_specimens": query_specimens,
    }


def annotation_target_records(options: dict[str, str]) -> list[Any]:
    project_dir = Path(options["project_dir"])
    manifest = Path(options["manifest"]) if options.get("manifest") else None
    source_dir = Path(options["source_images"]) if options.get("source_images") else None
    records = annotation_infer_records(project_dir, manifest, source_dir)
    specimens = set(parse_specimen_text(options.get("specimens") or "")) or None
    filtered = annotation_filter_records(records, options["split"], specimens)
    sampled = sample_annotation_records(
        filtered,
        coerce_int(options.get("max_specimens"), None),
        coerce_int(options.get("gallery_per_specimen"), None),
        options.get("gallery_sampling") or "last",
        coerce_int(options.get("query_per_specimen"), None),
    )
    max_images = coerce_int(options.get("max_images"), None)
    if max_images is not None:
        sampled = sampled[:max_images]
    return sampled


def count_completed_annotations(options: dict[str, str], target_records: list[Any]) -> int:
    point_count = coerce_int(options.get("point_count"), 5) or 5
    output_csv = Path(options.get("output_csv") or default_annotation_csv(options["project_dir"], point_count))
    existing = load_existing_annotations(output_csv)
    target_paths = {record.relative_path.replace("/", "\\") for record in target_records}
    return sum(1 for relative_path in target_paths if relative_path in existing)


def matching_counts(options: dict[str, str]) -> tuple[int, int]:
    project_dir = Path(options["project_dir"])
    manifest = Path(options["manifest"]) if options.get("manifest") else None
    source_dir = Path(options["source_images"]) if options.get("source_images") else None
    records = matcher_infer_records(project_dir, manifest, source_dir)
    gallery_records, query_records = split_records(
        records,
        coerce_int(options.get("max_gallery"), None),
        coerce_int(options.get("max_query"), None),
        coerce_int(options.get("max_specimens"), None),
        coerce_int(options.get("gallery_per_specimen"), None),
        options.get("gallery_sampling") or "last",
        coerce_int(options.get("query_per_specimen"), None),
    )
    total_gallery = sum(len(items) for items in gallery_records.values())
    total_query = sum(len(items) for items in query_records.values())
    return total_gallery, total_query


def estimate_progress(job: dict[str, Any]) -> tuple[float, str]:
    try:
        if job["type"] == "annotation":
            target_records = annotation_target_records(job["options"])
            total = len(target_records)
            completed = count_completed_annotations(job["options"], target_records)
            if total <= 0:
                return 0.0, "No target images selected."
            percent = min(100.0, round((completed / total) * 100.0, 1))
            return percent, f"Annotated {completed} of {total} selected images."

        options = job["options"]
        output_dir = Path(options["output_dir"])
        total_gallery, total_query = matching_counts(options)
        total_images = max(1, total_gallery + total_query)

        if job["type"] == "variation":
            feature_dir = output_dir / "belt"
            feature_count = sum(1 for path in feature_dir.rglob("*.png")) if feature_dir.exists() else 0
            processed_images = feature_count
            summary_exists = (output_dir / "summary.json").exists()
            feature_progress = min(1.0, processed_images / total_images)
            progress = min(100.0, round((feature_progress * 90.0) + (10.0 if summary_exists else 0.0), 1))
            return progress, f"Processed about {processed_images}/{total_images} images; consensus outputs {'ready' if summary_exists else 'pending'}."

        matcher_mode = options["matcher_mode"]
        if matcher_mode == "axis_belt":
            feature_dir = output_dir / "belt"
            feature_count = sum(1 for path in feature_dir.rglob("*.png")) if feature_dir.exists() else 0
            processed_images = feature_count
        elif matcher_mode == "tripoint":
            feature_dir = output_dir / "windows"
            feature_count = sum(1 for path in feature_dir.rglob("*.png")) if feature_dir.exists() else 0
            processed_images = int(round(feature_count / 3.0))
        else:
            feature_dir = output_dir / "warped"
            feature_count = sum(1 for path in feature_dir.rglob("*.png")) if feature_dir.exists() else 0
            processed_images = feature_count

        qc_dir = output_dir / "qc"
        qc_count = sum(1 for path in qc_dir.rglob("*.png")) if qc_dir.exists() else 0
        feature_progress = min(1.0, processed_images / total_images)
        qc_progress = min(1.0, qc_count / max(1, total_query))
        progress = min(100.0, round((feature_progress * 80.0) + (qc_progress * 20.0), 1))
        return progress, f"Processed about {processed_images}/{total_images} images; QC panels {qc_count}/{total_query}."
    except Exception:
        return 0.0, "Progress unavailable."


def build_job_command(job: dict[str, Any]) -> list[str]:
    if job["type"] == "annotation":
        return build_annotation_command(job)
    if job["type"] == "variation":
        return build_variation_command(job)
    if job["type"] == "distance_tree":
        return [sys.executable, "-B", str(Path(__file__).resolve()), "distance-tree"]
    return build_match_command(job)


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    if job["type"] == "distance_tree":
        run_distance_tree_job(job_id)
        return
    command = build_job_command(job)
    log_path = Path(job["log_path"])
    update_job(job_id, status="running", started_at=utc_now(), command=command, error_message=None)
    try:
        with open(log_path, "w", encoding="utf-8", newline="\n") as log_handle:
            log_handle.write("$ " + " ".join(command) + "\n\n")
            log_handle.flush()
            process = subprocess.Popen(
                command,
                cwd=TOOLS_DIR,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            while process.poll() is None:
                progress, progress_text = estimate_progress(job)
                update_job(job_id, progress=progress, progress_text=progress_text)
                time.sleep(1.0)
            return_code = process.wait()

        summary: dict[str, Any] = {}
        if job["type"] in {"matching", "variation"}:
            summary_path = Path(job["options"]["output_dir"]) / "summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    summary = {}
        progress, progress_text = estimate_progress(job)
        update_job(
            job_id,
            status="completed" if return_code == 0 else "failed",
            finished_at=utc_now(),
            return_code=return_code,
            summary=summary,
            progress=100.0 if return_code == 0 else progress,
            progress_text="Finished." if return_code == 0 else progress_text,
            error_message=None if return_code == 0 else "Job failed. Check the log.",
        )
    except Exception as exc:
        with open(log_path, "a", encoding="utf-8", newline="\n") as log_handle:
            log_handle.write("\n" + traceback.format_exc())
        update_job(job_id, status="failed", finished_at=utc_now(), return_code=1, error_message=str(exc))


def launch_job(job_id: str) -> None:
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()


def html_page(title: str, body: str, *, refresh_seconds: int | None = None) -> bytes:
    refresh = f'<meta http-equiv="refresh" content="{refresh_seconds}">' if refresh_seconds else ""
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh}
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --panel: #fffdfa;
      --ink: #1c2d3f;
      --muted: #627181;
      --line: #ddd4c5;
      --accent: #1d4ed8;
      --soft: #e0ecff;
      --good: #166534;
      --warn: #92400e;
      --bad: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Georgia, "Times New Roman", serif; background: linear-gradient(180deg, #f9f7f1 0%, #eee8dc 100%); color: var(--ink); }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 26px 18px 40px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px; box-shadow: 0 10px 28px rgba(28, 45, 63, 0.06); margin-bottom: 18px; }}
    .grid {{ display: grid; gap: 14px; }}
    .grid.two {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .grid.four {{ grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }}
    label {{ display: block; font-weight: 700; margin-bottom: 6px; }}
    input[type="text"], input[type="number"], select {{ width: 100%; padding: 11px 13px; border: 1px solid var(--line); border-radius: 12px; font: inherit; background: white; }}
    button, .button {{ display: inline-block; padding: 11px 18px; border-radius: 999px; border: 1px solid transparent; background: var(--accent); color: white; font: inherit; font-weight: 700; cursor: pointer; }}
    .button.secondary, button.secondary {{ background: var(--soft); color: var(--ink); border-color: #bfd4ff; }}
    .row {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
    .muted {{ color: var(--muted); }}
    .banner {{ padding: 12px 14px; border-radius: 14px; margin-bottom: 14px; }}
    .banner.error {{ background: #fee2e2; color: var(--bad); border: 1px solid #fecaca; }}
    .banner.info {{ background: #e0f2fe; color: var(--ink); border: 1px solid #bae6fd; }}
    .jobs {{ width: 100%; border-collapse: collapse; }}
    .jobs th, .jobs td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid #eadfce; vertical-align: top; }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.95rem; }}
    .pill.good {{ background: #dcfce7; color: var(--good); }}
    .pill.warn {{ background: #ffedd5; color: var(--warn); }}
    .pill.bad {{ background: #fee2e2; color: var(--bad); }}
    pre {{ white-space: pre-wrap; background: #f5efe3; border: 1px solid #e4d6bf; border-radius: 14px; padding: 14px; font-family: Consolas, "Courier New", monospace; }}
    .kv {{ display: grid; gap: 8px; grid-template-columns: 180px 1fr; }}
    .thumbs {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .thumbs img {{ width: 100%; border-radius: 12px; border: 1px solid var(--line); background: white; }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>
"""
    return document.encode("utf-8")


def status_badge(status: str) -> str:
    mapping = {
        "queued": ("pill warn", "Queued"),
        "running": ("pill warn", "Running"),
        "completed": ("pill good", "Completed"),
        "failed": ("pill bad", "Failed"),
    }
    css, label = mapping.get(status, ("pill", status))
    return f'<span class="{css}">{html.escape(label)}</span>'


def project_overview_html(project_dir_text: str) -> str:
    status = project_status(project_dir_text)
    if not status["exists"]:
        return f'<section class="panel"><h2>Project Overview</h2><p class="muted">Project folder not found: <code>{html.escape(project_dir_text)}</code></p></section>'
    return f"""
<section class="panel">
  <h2>Project Overview</h2>
  <div class="grid four">
    <div><strong>Gallery specimens</strong><br>{status['gallery_specimens']}</div>
    <div><strong>Gallery images</strong><br>{status['gallery_images']}</div>
    <div><strong>Query specimens</strong><br>{status['query_specimens']}</div>
    <div><strong>Query images</strong><br>{status['query_images']}</div>
  </div>
  <p class="muted" style="margin-top:12px;">Project folder: <code>{html.escape(project_dir_text)}</code></p>
  <p class="muted">Expected subfolders: <code>{html.escape(status['gallery_dir'])}</code>, <code>{html.escape(status['query_dir'])}</code>, <code>{html.escape(status['outputs_dir'])}</code></p>
</section>
"""


def render_jobs_table() -> str:
    rows: list[str] = []
    for job in list_jobs()[:20]:
        rows.append(
            "<tr>"
            f"<td><a href=\"/jobs/{quote(job['id'])}\">{html.escape(job.get('label') or job['id'])}</a></td>"
            f"<td>{html.escape(job.get('type', ''))}</td>"
            f"<td>{status_badge(job.get('status', 'queued'))}</td>"
            f"<td>{html.escape(str(job.get('progress', '')))}%</td>"
            f"<td>{html.escape(job.get('created_at') or '')}</td>"
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="5" class="muted">No jobs yet.</td></tr>')
    return (
        '<table class="jobs"><thead><tr><th>Job</th><th>Type</th><th>Status</th><th>Progress</th><th>Created</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_home_page(message: str | None = None, *, error: bool = False) -> bytes:
    banner = ""
    if message:
        cls = "error" if error else "info"
        banner = f'<div class="banner {cls}">{html.escape(message)}</div>'

    annotation_csv = str(Path(DEFAULT_PROJECT_DIR) / "config" / "axis_belt_landmarks.csv")
    match_output_dir = str(Path(DEFAULT_PROJECT_DIR) / "outputs" / "axis_belt_web_run")
    variation_output_dir = str(Path(DEFAULT_PROJECT_DIR) / "outputs" / "pattern_variation_web_run")
    distance_input_csv = default_distance_input_csv(DEFAULT_PROJECT_DIR)
    distance_output_dir = default_distance_output_dir(DEFAULT_PROJECT_DIR)
    body = f"""
<section class="panel">
  <h1>Darevskia ID Web App</h1>
  <p class="muted">Local browser interface for landmark annotation, curved-belt matching, progress tracking, and QC review. The current best workflow is the <strong>5-landmark curved belt</strong> with <strong>specimen-level consensus</strong>.</p>
  {banner}
  <div class="row">
    <a class="button secondary" href="/manual">User Manual</a>
    <a class="button secondary" href="/spec">Web App Spec</a>
    <a class="button secondary" href="/variation-guide">Pattern Variation Guide</a>
  </div>
</section>
{project_overview_html(DEFAULT_PROJECT_DIR)}
<section class="panel">
  <h2>Annotate Landmarks</h2>
  <p class="muted">Launch the existing annotation window from the browser. Point count is fully configurable here, so the same interface can also be used for longer-bodied animals.</p>
  <form method="post" action="/annotate" class="grid">
    <div class="grid two">
      <div><label>Project Folder</label><input type="text" name="annotation_project_dir" value="{html.escape(DEFAULT_PROJECT_DIR)}"></div>
      <div><label>Landmark CSV</label><input type="text" name="annotation_output_csv" value="{html.escape(annotation_csv)}"></div>
      <div><label>Manifest CSV (optional)</label><input type="text" name="annotation_manifest" value=""></div>
      <div><label>Source Images Folder (optional)</label><input type="text" name="annotation_source_images" value=""></div>
      <div><label>Split</label><select name="annotation_split"><option value="gallery">gallery</option><option value="query">query</option><option value="both">both</option></select></div>
      <div><label>Specimen IDs (comma separated, optional)</label><input type="text" name="annotation_specimens" placeholder="1,2,3"></div>
      <div><label>Point Count</label><input type="number" name="annotation_point_count" min="3" value="5"></div>
      <div><label>Display Mode</label><select name="annotation_display_mode"><option value="viewer">viewer</option><option value="fit">fit</option><option value="raw">raw</option></select></div>
      <div><label>Max Images (optional)</label><input type="number" name="annotation_max_images" min="1"></div>
      <div><label>Max Specimens (optional)</label><input type="number" name="annotation_max_specimens" min="1" value="4"></div>
      <div><label>Gallery Per Specimen</label><input type="number" name="annotation_gallery_per_specimen" min="1" value="4"></div>
      <div><label>Gallery Sampling</label><select name="annotation_gallery_sampling"><option value="first">first</option><option value="spaced">spaced</option><option value="last" selected>last</option></select></div>
      <div><label>Query Per Specimen</label><input type="number" name="annotation_query_per_specimen" min="1" value="1"></div>
      <div><label>Window Width</label><input type="number" name="annotation_window_width" min="800" value="1600"></div>
      <div><label>Window Height</label><input type="number" name="annotation_window_height" min="600" value="950"></div>
      <div><label><input type="checkbox" name="annotation_overwrite"> Overwrite existing annotations</label></div>
    </div>
    <div class="row"><button type="submit">Launch Annotation Job</button></div>
  </form>
</section>
<section class="panel">
  <h2>Run Matcher</h2>
  <p class="muted">The app exposes many parameters. The most stable current combination is <code>matcher_mode = axis_belt</code>, <code>point_count = 5</code>, <code>belt_breadth_fraction = 0.14</code>, and <code>consensus_top_k = 2</code>.</p>
  <form method="post" action="/match" class="grid">
    <div class="grid two">
      <div><label>Project Folder</label><input type="text" name="match_project_dir" value="{html.escape(DEFAULT_PROJECT_DIR)}"></div>
      <div><label>Landmarks CSV</label><input type="text" name="match_landmarks" value="{html.escape(annotation_csv)}"></div>
      <div><label>Manifest CSV (optional)</label><input type="text" name="match_manifest" value=""></div>
      <div><label>Source Images Folder (optional)</label><input type="text" name="match_source_images" value=""></div>
      <div><label>Output Folder</label><input type="text" name="match_output_dir" value="{html.escape(match_output_dir)}"></div>
      <div><label>Matcher Mode</label><select name="matcher_mode"><option value="axis_belt" selected>5-point curved belt</option><option value="tripoint">3-point windows</option><option value="quad">4-point quadrilateral</option></select></div>
      <div><label>Max Specimens</label><input type="number" name="match_max_specimens" min="1" value="12"></div>
      <div><label>Gallery Per Specimen</label><input type="number" name="match_gallery_per_specimen" min="1" value="4"></div>
      <div><label>Gallery Sampling</label><select name="match_gallery_sampling"><option value="first">first</option><option value="spaced">spaced</option><option value="last" selected>last</option></select></div>
      <div><label>Query Per Specimen</label><input type="number" name="match_query_per_specimen" min="1" value="1"></div>
      <div><label>Max Gallery (optional)</label><input type="number" name="match_max_gallery" min="1"></div>
      <div><label>Max Query (optional)</label><input type="number" name="match_max_query" min="1"></div>
      <div><label>Max Side</label><input type="number" name="match_max_side" min="600" value="2200"></div>
      <div><label>Preview Side</label><input type="number" name="match_preview_side" min="300" value="900"></div>
      <div><label>Thumb Size</label><input type="number" name="match_thumb_size" min="64" value="256"></div>
      <div><label>Inner Margin</label><input type="text" name="match_inner_margin" value="0.03"></div>
      <div><label>Belt Width</label><input type="number" name="match_belt_width" min="100" value="360"></div>
      <div><label>Belt Height</label><input type="number" name="match_belt_height" min="200" value="900"></div>
      <div><label>Belt Breadth Fraction</label><input type="text" name="match_belt_breadth_fraction" value="0.14"></div>
      <div><label>Belt Breadth PX (optional)</label><input type="text" name="match_belt_breadth_px" value=""></div>
      <div><label>Consensus Top-K</label><input type="number" name="match_consensus_top_k" min="1" value="2"></div>
      <div><label>Window Width (tripoint)</label><input type="number" name="match_window_width" min="80" value="360"></div>
      <div><label>Window Height (tripoint)</label><input type="number" name="match_window_height" min="120" value="520"></div>
      <div><label>Window Length Fraction (tripoint)</label><input type="text" name="match_window_length_fraction" value="0.30"></div>
      <div><label>Window Width Fraction (tripoint)</label><input type="text" name="match_window_width_fraction" value="0.18"></div>
      <div><label><input type="checkbox" name="match_allow_new_specimen"> Allow new specimen</label></div>
      <div><label>New Specimen Threshold</label><input type="text" name="match_new_specimen_threshold" value="0.20"></div>
      <div><label>New Specimen Margin</label><input type="text" name="match_new_specimen_margin" value="0.035"></div>
    </div>
    <div class="row"><button type="submit">Run Matcher Job</button></div>
  </form>
</section>
<section class="panel">
  <h2>Pattern Variation</h2>
  <p class="muted">Build a dorsal-pattern consensus image, measure per-image and per-specimen deviation from that consensus, and estimate left-right asymmetry. This analysis reuses the same successful <code>5-point curved belt</code> alignment.</p>
  <form method="post" action="/variation" class="grid">
    <div class="grid two">
      <div><label>Project Folder</label><input type="text" name="variation_project_dir" value="{html.escape(DEFAULT_PROJECT_DIR)}"></div>
      <div><label>Landmarks CSV</label><input type="text" name="variation_landmarks" value="{html.escape(annotation_csv)}"></div>
      <div><label>Manifest CSV (optional)</label><input type="text" name="variation_manifest" value=""></div>
      <div><label>Source Images Folder (optional)</label><input type="text" name="variation_source_images" value=""></div>
      <div><label>Output Folder</label><input type="text" name="variation_output_dir" value="{html.escape(variation_output_dir)}"></div>
      <div><label>Include Split</label><select name="variation_include_split"><option value="both" selected>both</option><option value="gallery">gallery</option><option value="query">query</option></select></div>
      <div><label>Max Specimens</label><input type="number" name="variation_max_specimens" min="1" value="12"></div>
      <div><label>Gallery Per Specimen</label><input type="number" name="variation_gallery_per_specimen" min="1" value="4"></div>
      <div><label>Gallery Sampling</label><select name="variation_gallery_sampling"><option value="first">first</option><option value="spaced">spaced</option><option value="last" selected>last</option></select></div>
      <div><label>Query Per Specimen</label><input type="number" name="variation_query_per_specimen" min="1" value="1"></div>
      <div><label>Max Gallery (optional)</label><input type="number" name="variation_max_gallery" min="1"></div>
      <div><label>Max Query (optional)</label><input type="number" name="variation_max_query" min="1"></div>
      <div><label>Max Side</label><input type="number" name="variation_max_side" min="600" value="2200"></div>
      <div><label>Preview Side</label><input type="number" name="variation_preview_side" min="300" value="900"></div>
      <div><label>Thumb Size</label><input type="number" name="variation_thumb_size" min="64" value="256"></div>
      <div><label>Inner Margin</label><input type="text" name="variation_inner_margin" value="0.03"></div>
      <div><label>Belt Width</label><input type="number" name="variation_belt_width" min="100" value="360"></div>
      <div><label>Belt Height</label><input type="number" name="variation_belt_height" min="200" value="900"></div>
      <div><label>Belt Breadth Fraction</label><input type="text" name="variation_belt_breadth_fraction" value="0.14"></div>
      <div><label>Belt Breadth PX (optional)</label><input type="text" name="variation_belt_breadth_px" value=""></div>
    </div>
    <div class="row"><button type="submit">Run Pattern Variation Job</button></div>
  </form>
</section>
<section class="panel">
  <h2>Distance Matrix and Tree</h2>
  <p class="muted">Build a specimen-by-specimen distance matrix and an UPGMA distance tree from pattern-variation results. Use mean-pattern images for morphology-like pattern distances, or specimen summary metrics for a compact trait table.</p>
  <form method="post" action="/distance-tree" class="grid">
    <div class="grid two">
      <div><label>Project Folder</label><input type="text" name="distance_project_dir" value="{html.escape(DEFAULT_PROJECT_DIR)}"></div>
      <div><label>Input specimen_variation.csv</label><input type="text" name="distance_input_csv" value="{html.escape(distance_input_csv)}"></div>
      <div><label>Output Folder</label><input type="text" name="distance_output_dir" value="{html.escape(distance_output_dir)}"></div>
      <div><label>Distance Source</label><select name="distance_source"><option value="mean_pattern" selected>specimen mean-pattern images</option><option value="summary_metrics">numeric specimen summary metrics</option></select></div>
      <div><label>Distance Metric</label><select name="distance_metric"><option value="euclidean" selected>Euclidean</option><option value="manhattan">Manhattan</option><option value="correlation">Correlation distance</option></select></div>
      <div><label><input type="checkbox" name="distance_standardize" checked> Standardize summary metrics</label></div>
      <div><label>Image Vector Width</label><input type="number" name="distance_image_width" min="16" max="400" value="90"></div>
      <div><label>Image Vector Height</label><input type="number" name="distance_image_height" min="16" max="800" value="240"></div>
    </div>
    <div class="row"><button type="submit">Build Distance Matrix and Tree</button></div>
  </form>
</section>
<section class="panel">
  <h2>Recent Jobs</h2>
  {render_jobs_table()}
</section>
"""
    return html_page("Darevskia ID Web App", body)


def safe_resolve(path_text: str) -> Path | None:
    if not path_text:
        return None
    try:
        return Path(path_text).resolve()
    except Exception:
        return None


def is_allowed_path(path: Path) -> bool:
    allowed_roots = [
        PROJECT_ROOT.resolve(),
        Path(DEFAULT_PROJECT_DIR).resolve(),
        WEB_RUNS_DIR.resolve(),
    ]
    try:
        resolved = path.resolve()
    except Exception:
        return False
    return any(str(resolved).startswith(str(root)) for root in allowed_roots)


def render_markdown_as_pre(path: Path, title: str) -> bytes:
    text = path.read_text(encoding="utf-8") if path.exists() else "File not found."
    body = f"""
<section class="panel">
  <div class="row"><a class="button secondary" href="/">Home</a></div>
  <h1>{html.escape(title)}</h1>
  <pre>{html.escape(text)}</pre>
</section>
"""
    return html_page(title, body)


def render_csv_table(path: Path, max_rows: int = 30) -> str:
    if not path.exists():
        return '<p class="muted">CSV file not found.</p>'
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return '<p class="muted">CSV file is empty.</p>'
    header = rows[0]
    body_rows = rows[1 : max_rows + 1]
    header_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    row_html = []
    for row in body_rows:
        row_html.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
    return '<table class="jobs"><thead><tr>' + header_html + "</tr></thead><tbody>" + "".join(row_html) + "</tbody></table>"


def render_qc_thumbnails(output_dir: Path, limit: int = 8) -> str:
    qc_dir = output_dir / "qc"
    if not qc_dir.exists():
        return '<p class="muted">No QC directory yet.</p>'
    images = sorted(qc_dir.glob("*.png"))[:limit]
    if not images:
        return '<p class="muted">No QC images yet.</p>'
    parts = ['<div class="thumbs">']
    for path in images:
        href = "/file?path=" + quote(str(path))
        parts.append(f'<a href="{href}"><img src="{href}" alt="{html.escape(path.name)}"></a>')
    parts.append("</div>")
    return "".join(parts)


def render_image_gallery(paths: list[Path]) -> str:
    if not paths:
        return '<p class="muted">No preview images yet.</p>'
    parts = ['<div class="thumbs">']
    for path in paths:
        href = "/file?path=" + quote(str(path))
        parts.append(f'<a href="{href}"><img src="{href}" alt="{html.escape(path.name)}"></a>')
    parts.append("</div>")
    return "".join(parts)


def render_variation_preview(output_dir: Path, limit: int = 8) -> str:
    consensus_candidates = [
        output_dir / "consensus" / "consensus_pattern.png",
        output_dir / "consensus" / "consensus_outline.png",
        output_dir / "consensus" / "consensus_spot_frequency.png",
        output_dir / "consensus" / "mean_absolute_deviation.png",
    ]
    specimen_candidates = sorted((output_dir / "specimens").glob("specimen_*/*.png")) if (output_dir / "specimens").exists() else []
    paths = [path for path in consensus_candidates if path.exists()]
    paths.extend(specimen_candidates[: max(0, limit - len(paths))])
    return render_image_gallery(paths[:limit])


def render_job_page(job_id: str) -> bytes:
    job = get_job(job_id)
    if not job:
        return html_page("Job not found", '<section class="panel"><h1>Job not found</h1><p><a href="/">Back</a></p></section>')

    refresh = 3 if job.get("status") in {"queued", "running"} else None
    log_path = Path(job["log_path"])
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    summary = job.get("summary") or {}
    output_dir_text = job.get("output_dir") or job["options"].get("output_dir") or ""
    output_dir = Path(output_dir_text) if output_dir_text else None

    summary_html = f'<pre>{html.escape(json.dumps(summary, indent=2))}</pre>' if summary else '<p class="muted">No summary yet.</p>'
    predictions_html = '<p class="muted">No predictions table yet.</p>'
    qc_html = '<p class="muted">No QC preview yet.</p>'
    results_title = "Predictions"
    preview_title = "QC Preview"
    links_html = ""
    if output_dir and output_dir.exists():
        summary_json = output_dir / "summary.json"
        link_parts = [
            f'<a class="button secondary" href="/browse?path={quote(str(output_dir))}">Browse output folder</a>',
            f'<a class="button secondary" href="/file?path={quote(str(summary_json))}">Open summary.json</a>',
        ]
        if job.get("type") == "variation":
            specimen_csv = output_dir / "specimen_variation.csv"
            image_csv = output_dir / "image_variation.csv"
            results_title = "Specimen Variation"
            preview_title = "Consensus Preview"
            predictions_html = render_csv_table(specimen_csv, max_rows=20)
            qc_html = render_variation_preview(output_dir, limit=8)
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(specimen_csv))}">Open specimen_variation.csv</a>')
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(image_csv))}">Open image_variation.csv</a>')
        elif job.get("type") == "distance_tree":
            matrix_csv = output_dir / "distance_matrix.csv"
            tree_newick = output_dir / "upgma_tree.newick"
            tree_svg = output_dir / "upgma_tree.svg"
            results_title = "Distance Matrix"
            preview_title = "UPGMA Tree"
            predictions_html = render_csv_table(matrix_csv, max_rows=30)
            qc_html = render_image_gallery([tree_svg] if tree_svg.exists() else [])
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(matrix_csv))}">Open distance_matrix.csv</a>')
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(tree_newick))}">Open upgma_tree.newick</a>')
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(tree_svg))}">Open upgma_tree.svg</a>')
        else:
            predictions_csv = output_dir / "predictions.csv"
            predictions_html = render_csv_table(predictions_csv, max_rows=20)
            qc_html = render_qc_thumbnails(output_dir, limit=8)
            link_parts.append(f'<a class="button secondary" href="/file?path={quote(str(predictions_csv))}">Open predictions.csv</a>')
        links_html = f'<div class="row">{"".join(link_parts)}</div>'

    body = f"""
<section class="panel">
  <div class="row"><a class="button secondary" href="/">Home</a></div>
  <h1>{html.escape(job.get('label') or job_id)}</h1>
  <div class="kv">
    <div><strong>Type</strong></div><div>{html.escape(job.get('type', ''))}</div>
    <div><strong>Status</strong></div><div>{status_badge(job.get('status', 'queued'))}</div>
    <div><strong>Progress</strong></div><div>{html.escape(str(job.get('progress', 0)))}% &nbsp; <span class="muted">{html.escape(job.get('progress_text') or '')}</span></div>
    <div><strong>Project</strong></div><div><code>{html.escape(job.get('project_dir') or '')}</code></div>
    <div><strong>Output</strong></div><div><code>{html.escape(output_dir_text)}</code></div>
    <div><strong>Created</strong></div><div>{html.escape(job.get('created_at') or '')}</div>
  </div>
  {links_html}
</section>
<section class="panel"><h2>Summary</h2>{summary_html}</section>
<section class="panel"><h2>{html.escape(results_title)}</h2>{predictions_html}</section>
<section class="panel"><h2>{html.escape(preview_title)}</h2>{qc_html}</section>
<section class="panel"><h2>Log</h2><pre>{html.escape(log_text or 'No log yet.')}</pre></section>
"""
    return html_page(job.get("label") or job_id, body, refresh_seconds=refresh)


def render_directory_page(path_text: str) -> bytes:
    path = safe_resolve(path_text)
    if path is None or not path.exists() or not path.is_dir() or not is_allowed_path(path):
        return html_page("Browse", '<section class="panel"><h1>Folder not available.</h1><p><a href="/">Home</a></p></section>')
    rows = []
    parent = path.parent if path.parent != path else None
    if parent and is_allowed_path(parent):
        rows.append(f'<tr><td><a href="/browse?path={quote(str(parent))}">..</a></td><td>parent</td></tr>')
    for child in sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        href = "/browse?path=" + quote(str(child)) if child.is_dir() else "/file?path=" + quote(str(child))
        kind = "dir" if child.is_dir() else "file"
        rows.append(f'<tr><td><a href="{href}">{html.escape(child.name)}</a></td><td>{kind}</td></tr>')
    body = (
        '<section class="panel"><div class="row"><a class="button secondary" href="/">Home</a></div>'
        f'<h1>Browse</h1><p class="muted"><code>{html.escape(str(path))}</code></p>'
        '<table class="jobs"><thead><tr><th>Name</th><th>Type</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></section>"
    )
    return html_page("Browse", body)


class DarevskiaHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.respond(HTTPStatus.OK, render_home_page())
            return
        if parsed.path == "/manual":
            self.respond(HTTPStatus.OK, render_markdown_as_pre(MANUAL_PATH, "Darevskia ID User Manual"))
            return
        if parsed.path == "/spec":
            self.respond(HTTPStatus.OK, render_markdown_as_pre(SPEC_PATH, "Darevskia ID Web App Specification"))
            return
        if parsed.path == "/variation-guide":
            self.respond(HTTPStatus.OK, render_markdown_as_pre(VARIATION_MANUAL_PATH, "Darevskia Pattern Variation Guide"))
            return
        if parsed.path.startswith("/jobs/"):
            self.respond(HTTPStatus.OK, render_job_page(unquote(parsed.path.split("/")[-1])))
            return
        if parsed.path == "/browse":
            query = parse_qs(parsed.query)
            self.respond(HTTPStatus.OK, render_directory_page(query.get("path", [""])[-1]))
            return
        if parsed.path == "/file":
            query = parse_qs(parsed.query)
            self.serve_file(query.get("path", [""])[-1])
            return
        self.respond(HTTPStatus.NOT_FOUND, html_page("Not found", '<section class="panel"><h1>Not found</h1></section>'))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        fields = parse_request_form(self.rfile.read(length))
        if self.path == "/annotate":
            options = collect_annotation_options(fields)
            point_count = coerce_int(options["point_count"], 5) or 5
            if not options["output_csv"]:
                options["output_csv"] = default_annotation_csv(options["project_dir"], point_count)
            job = create_job(
                job_type="annotation",
                label=f"Annotation {point_count}-point {options['split']}",
                project_dir=options["project_dir"],
                options=options,
            )
            launch_job(job["id"])
            self.redirect(f"/jobs/{quote(job['id'])}")
            return
        if self.path == "/match":
            options = collect_match_options(fields)
            matcher_mode = options["matcher_mode"]
            if not options["output_dir"]:
                options["output_dir"] = default_output_dir(options["project_dir"], matcher_mode)
            if not options["landmarks"]:
                options["landmarks"] = default_annotation_csv(
                    options["project_dir"],
                    5 if matcher_mode == "axis_belt" else 4 if matcher_mode == "quad" else 3,
                )
            job = create_job(
                job_type="matching",
                label=f"Matcher {matcher_mode}",
                project_dir=options["project_dir"],
                options=options,
            )
            launch_job(job["id"])
            self.redirect(f"/jobs/{quote(job['id'])}")
            return
        if self.path == "/variation":
            options = collect_variation_options(fields)
            if not options["output_dir"]:
                options["output_dir"] = default_variation_output_dir(options["project_dir"])
            if not options["landmarks"]:
                options["landmarks"] = default_annotation_csv(options["project_dir"], 5)
            job = create_job(
                job_type="variation",
                label="Pattern variation",
                project_dir=options["project_dir"],
                options=options,
            )
            launch_job(job["id"])
            self.redirect(f"/jobs/{quote(job['id'])}")
            return
        if self.path == "/distance-tree":
            options = collect_distance_options(fields)
            if not options["input_csv"]:
                options["input_csv"] = default_distance_input_csv(options["project_dir"])
            if not options["output_dir"]:
                options["output_dir"] = default_distance_output_dir(options["project_dir"])
            job = create_job(
                job_type="distance_tree",
                label="Distance matrix and UPGMA tree",
                project_dir=options["project_dir"],
                options=options,
            )
            launch_job(job["id"])
            self.redirect(f"/jobs/{quote(job['id'])}")
            return
        self.respond(HTTPStatus.NOT_FOUND, html_page("Not found", '<section class="panel"><h1>Not found</h1></section>'))

    def serve_file(self, path_text: str) -> None:
        path = safe_resolve(path_text)
        if path is None or not path.exists() or not path.is_file() or not is_allowed_path(path):
            self.respond(HTTPStatus.NOT_FOUND, b"Not found", content_type="text/plain; charset=utf-8")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        content_type = content_type or "application/octet-stream"
        self.respond(HTTPStatus.OK, path.read_bytes(), content_type=content_type)

    def respond(self, status: HTTPStatus, payload: bytes, *, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER.value)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    args = parse_args()
    ensure_directories()
    load_jobs()
    server = ThreadingHTTPServer((args.host, args.port), DarevskiaHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Darevskia ID web app running at {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
