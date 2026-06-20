from __future__ import annotations

import argparse
import csv
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageTk

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
WINDOW_NAME = "Darevskia Neck Patch Annotation"
RESAMPLING = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS


@dataclass(frozen=True)
class ManifestRecord:
    specimen_id: str
    split: str
    image_path: Path
    relative_path: str
    source_file: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate a polygon patch for Darevskia images.")
    parser.add_argument("--project-dir", required=True, help="Project folder containing gallery/, query/, config/, and outputs/.")
    parser.add_argument("--manifest", help="Optional manifest CSV. Defaults to project_dir/config/manifest.csv.")
    parser.add_argument("--source-images", help="Optional folder with the original source photos. When provided, images are opened from this folder via manifest source_file.")
    parser.add_argument("--output-csv", help="Where to save landmarks. Defaults to project_dir/config/neck_patch_landmarks.csv.")
    parser.add_argument("--split", choices=("gallery", "query", "both"), default="both", help="Which split to annotate.")
    parser.add_argument("--specimen", action="append", help="Optional specimen ID filter. Can be passed multiple times.")
    parser.add_argument("--max-images", type=int, default=None, help="Optional cap on the number of images to annotate this session.")
    parser.add_argument("--max-specimens", type=int, default=None, help="Optional cap on the number of specimens included, in manifest/specimen order.")
    parser.add_argument("--gallery-per-specimen", type=int, default=None, help="Optional cap on gallery images per specimen.")
    parser.add_argument("--gallery-sampling", choices=("first", "spaced", "last"), default="first", help="How to sample gallery images when gallery_per_specimen is smaller than the available images.")
    parser.add_argument("--query-per-specimen", type=int, default=None, help="Optional cap on query images per specimen.")
    parser.add_argument("--display-mode", choices=("viewer", "raw", "fit"), default="viewer", help="Viewer mode uses a zoomable scrollable image canvas. Older raw/fit aliases now use the same viewer.")
    parser.add_argument("--window-width", type=int, default=1600, help="Initial annotation window width.")
    parser.add_argument("--window-height", type=int, default=950, help="Initial annotation window height.")
    parser.add_argument("--point-count", type=int, default=10, help="Number of polygon points to click for each region.")
    parser.add_argument("--overwrite", action="store_true", help="Re-annotate images that already have saved landmarks.")
    return parser.parse_args()


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


def load_existing_annotations(csv_path: Path) -> dict[str, dict[str, str]]:
    if not csv_path.exists():
        return {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return {str(row["relative_path"]).replace("/", "\\"): row for row in reader}


def save_annotations(csv_path: Path, rows: dict[str, dict[str, str]]) -> None:
    max_points = 0
    for row in rows.values():
        if "point_count" in row:
            max_points = max(max_points, int(row["point_count"]))
        else:
            max_points = max(max_points, sum(1 for key in row if key.startswith("x")))
    fieldnames = ["relative_path", "specimen_id", "split", "image_width", "image_height", "point_count"]
    for idx in range(1, max_points + 1):
        fieldnames.extend([f"x{idx}", f"y{idx}"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])


def filter_records(records: list[ManifestRecord], split: str, specimens: set[str] | None) -> list[ManifestRecord]:
    filtered = []
    for record in records:
        if split != "both" and record.split != split:
            continue
        if specimens is not None and record.specimen_id not in specimens:
            continue
        filtered.append(record)
    return filtered


def sample_records(records: list[ManifestRecord], limit: int | None, strategy: str) -> list[ManifestRecord]:
    if limit is None or len(records) <= limit:
        return list(records)
    if strategy == "first":
        return list(records[:limit])
    if strategy == "last":
        return list(records[-limit:])

    raw_indices = np.linspace(0, len(records) - 1, num=limit)
    chosen_indices: list[int] = []
    for index in raw_indices:
        rounded = int(round(float(index)))
        if rounded not in chosen_indices:
            chosen_indices.append(rounded)
    if len(chosen_indices) < limit:
        for idx in range(len(records)):
            if idx not in chosen_indices:
                chosen_indices.append(idx)
            if len(chosen_indices) >= limit:
                break
    chosen_indices = sorted(chosen_indices[:limit])
    return [records[idx] for idx in chosen_indices]


def sample_annotation_records(
    records: list[ManifestRecord],
    max_specimens: int | None,
    gallery_per_specimen: int | None,
    gallery_sampling: str,
    query_per_specimen: int | None,
) -> list[ManifestRecord]:
    selected_specimens: list[str] = []
    selected_specimen_set: set[str] = set()
    gallery_by_specimen: dict[str, list[ManifestRecord]] = {}
    query_by_specimen: dict[str, list[ManifestRecord]] = {}

    for record in records:
        if record.specimen_id not in selected_specimen_set:
            if max_specimens is not None and len(selected_specimens) >= max_specimens:
                continue
            selected_specimens.append(record.specimen_id)
            selected_specimen_set.add(record.specimen_id)

        if record.specimen_id not in selected_specimen_set:
            continue

        if record.split == "gallery":
            gallery_by_specimen.setdefault(record.specimen_id, []).append(record)
        elif record.split == "query":
            query_by_specimen.setdefault(record.specimen_id, []).append(record)

    sampled: list[ManifestRecord] = []
    for specimen_id in selected_specimens:
        sampled.extend(sample_records(gallery_by_specimen.get(specimen_id, []), gallery_per_specimen, gallery_sampling))
        sampled.extend(sample_records(query_by_specimen.get(specimen_id, []), query_per_specimen, "first"))
    return sampled


def load_annotation_image(image_path: Path) -> Image.Image:
    return Image.open(image_path).convert("RGB")


def point_order_hint(point_count: int) -> str:
    if point_count == 3:
        return "Click 3 landmarks in order: neck center, middle dorsum, hindbody/tail-base center."
    if point_count == 5:
        return "Click 5 landmarks in order along the dorsal midline: neck, anterior dorsum, middle dorsum, posterior dorsum, hindbody/tail-base."
    if point_count == 4:
        return "Click 4 corners in order: upper-left, upper-right, lower-right, lower-left."
    return f"Click {point_count} points in a consistent order."


class ViewerAnnotator:
    def __init__(
        self,
        record: ManifestRecord,
        done_count: int,
        total_count: int,
        window_width: int,
        window_height: int,
        point_count: int,
    ) -> None:
        self.record = record
        self.done_count = done_count
        self.total_count = total_count
        self.window_width = max(900, window_width)
        self.window_height = max(650, window_height)
        self.point_count = max(3, point_count)
        self.original_image = load_annotation_image(record.image_path)
        self.image_width, self.image_height = self.original_image.size
        self.scale = min((self.window_width - 40) / self.image_width, (self.window_height - 140) / self.image_height, 1.0)
        self.min_scale = max(0.05, self.scale * 0.35)
        self.max_scale = max(6.0, self.scale * 10.0)
        self.offset_x = 20.0
        self.offset_y = 20.0
        self.drag_last: tuple[int, int] | None = None
        self.points: list[tuple[float, float]] = []
        self.result: list[tuple[float, float]] | None = None
        self.photo_image: ImageTk.PhotoImage | None = None

        self.root = tk.Tk()
        self.root.title(WINDOW_NAME)
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_quit)

        self.status_var = tk.StringVar()
        self.help_var = tk.StringVar()

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x")
        tk.Label(top_frame, textvariable=self.status_var, anchor="w", justify="left").pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(top_frame, textvariable=self.help_var, anchor="w", justify="left").pack(fill="x", padx=8, pady=(0, 6))

        self.canvas = tk.Canvas(self.root, background="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.root.bind("<Return>", self.on_save)
        self.root.bind("<space>", self.on_save)
        self.root.bind("<Escape>", self.on_quit)
        self.root.bind("q", self.on_quit)
        self.root.bind("Q", self.on_quit)
        self.root.bind("u", self.on_undo)
        self.root.bind("U", self.on_undo)
        self.root.bind("<BackSpace>", self.on_undo)
        self.root.bind("s", self.on_skip)
        self.root.bind("S", self.on_skip)
        self.root.bind("<Left>", lambda event: self.pan(100, 0))
        self.root.bind("<Right>", lambda event: self.pan(-100, 0))
        self.root.bind("<Up>", lambda event: self.pan(0, 100))
        self.root.bind("<Down>", lambda event: self.pan(0, -100))
        self.root.bind("a", lambda event: self.pan(100, 0))
        self.root.bind("A", lambda event: self.pan(100, 0))
        self.root.bind("d", lambda event: self.pan(-100, 0))
        self.root.bind("D", lambda event: self.pan(-100, 0))
        self.root.bind("w", lambda event: self.pan(0, 100))
        self.root.bind("W", lambda event: self.pan(0, 100))
        self.root.bind("x", lambda event: self.pan(0, -100))
        self.root.bind("X", lambda event: self.pan(0, -100))
        self.root.bind("z", lambda event: self.pan(0, -100))
        self.root.bind("Z", lambda event: self.pan(0, -100))
        self.root.bind("+", lambda event: self.zoom_at_canvas_center(1.15))
        self.root.bind("=", lambda event: self.zoom_at_canvas_center(1.15))
        self.root.bind("-", lambda event: self.zoom_at_canvas_center(1 / 1.15))
        self.root.bind("_", lambda event: self.zoom_at_canvas_center(1 / 1.15))
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", lambda event: self.zoom_at(event.x, event.y, 1.1))
        self.canvas.bind("<Button-5>", lambda event: self.zoom_at(event.x, event.y, 1 / 1.1))
        self.canvas.bind("<Configure>", lambda event: self.render())

        self.center_image()
        self.render()

    def center_image(self) -> None:
        canvas_width = max(1, self.window_width)
        canvas_height = max(1, self.window_height - 90)
        displayed_width = self.image_width * self.scale
        displayed_height = self.image_height * self.scale
        self.offset_x = max(0.0, (canvas_width - displayed_width) / 2.0)
        self.offset_y = max(0.0, (canvas_height - displayed_height) / 2.0)

    def clamp_offsets(self) -> None:
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        displayed_width = self.image_width * self.scale
        displayed_height = self.image_height * self.scale

        if displayed_width <= canvas_width:
            self.offset_x = (canvas_width - displayed_width) / 2.0
        else:
            min_x = canvas_width - displayed_width
            self.offset_x = min(0.0, max(min_x, self.offset_x))

        if displayed_height <= canvas_height:
            self.offset_y = (canvas_height - displayed_height) / 2.0
        else:
            min_y = canvas_height - displayed_height
            self.offset_y = min(0.0, max(min_y, self.offset_y))

    def render(self) -> None:
        self.clamp_offsets()
        displayed_width = max(1, int(round(self.image_width * self.scale)))
        displayed_height = max(1, int(round(self.image_height * self.scale)))
        rendered = self.original_image.resize((displayed_width, displayed_height), RESAMPLING)
        self.photo_image = ImageTk.PhotoImage(rendered)

        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor="nw", image=self.photo_image)

        for idx, (x_value, y_value) in enumerate(self.points, start=1):
            canvas_x = self.offset_x + (x_value * self.scale)
            canvas_y = self.offset_y + (y_value * self.scale)
            radius = 6
            self.canvas.create_oval(canvas_x - radius, canvas_y - radius, canvas_x + radius, canvas_y + radius, fill="#ffd400", outline="#1f1f1f", width=2)
            self.canvas.create_text(canvas_x + 12, canvas_y - 12, text=str(idx), fill="white", font=("Segoe UI", 11, "bold"))

        if len(self.points) >= 2:
            polygon = []
            for x_value, y_value in self.points:
                polygon.extend([self.offset_x + (x_value * self.scale), self.offset_y + (y_value * self.scale)])
            self.canvas.create_line(*polygon, fill="#44ff88", width=2)
            if len(self.points) == self.point_count:
                first_x, first_y = self.points[0]
                self.canvas.create_line(
                    self.offset_x + (self.points[-1][0] * self.scale),
                    self.offset_y + (self.points[-1][1] * self.scale),
                    self.offset_x + (first_x * self.scale),
                    self.offset_y + (first_y * self.scale),
                    fill="#44ff88",
                    width=2,
                )

        self.status_var.set(
            f"{self.record.relative_path}   specimen={self.record.specimen_id}   {self.done_count}/{self.total_count}   zoom={self.scale:.3f}x"
        )
        self.help_var.set(
            f"{point_order_hint(self.point_count)}   Left click: add point ({len(self.points)}/{self.point_count})   Right drag: pan   Wheel or +/-: zoom   U: undo   S: skip   Enter: save   Q/Esc: quit"
        )

    def canvas_to_image(self, canvas_x: float, canvas_y: float) -> tuple[float, float] | None:
        image_x = (canvas_x - self.offset_x) / self.scale
        image_y = (canvas_y - self.offset_y) / self.scale
        if 0 <= image_x < self.image_width and 0 <= image_y < self.image_height:
            return image_x, image_y
        return None

    def on_left_click(self, event: tk.Event[tk.Misc]) -> None:
        if len(self.points) >= self.point_count:
            return
        image_point = self.canvas_to_image(float(event.x), float(event.y))
        if image_point is None:
            return
        self.points.append((round(image_point[0], 3), round(image_point[1], 3)))
        self.render()

    def on_pan_start(self, event: tk.Event[tk.Misc]) -> None:
        self.drag_last = (event.x, event.y)

    def on_pan_drag(self, event: tk.Event[tk.Misc]) -> None:
        if self.drag_last is None:
            self.drag_last = (event.x, event.y)
            return
        dx = event.x - self.drag_last[0]
        dy = event.y - self.drag_last[1]
        self.offset_x += dx
        self.offset_y += dy
        self.drag_last = (event.x, event.y)
        self.render()

    def on_mouse_wheel(self, event: tk.Event[tk.Misc]) -> None:
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.zoom_at(float(event.x), float(event.y), factor)

    def zoom_at_canvas_center(self, factor: float) -> None:
        self.zoom_at(self.canvas.winfo_width() / 2.0, self.canvas.winfo_height() / 2.0, factor)

    def zoom_at(self, canvas_x: float, canvas_y: float, factor: float) -> None:
        image_point = self.canvas_to_image(canvas_x, canvas_y)
        new_scale = min(self.max_scale, max(self.min_scale, self.scale * factor))
        if abs(new_scale - self.scale) < 1e-6:
            return
        if image_point is None:
            image_point = (self.image_width / 2.0, self.image_height / 2.0)
            canvas_x = self.canvas.winfo_width() / 2.0
            canvas_y = self.canvas.winfo_height() / 2.0
        self.scale = new_scale
        self.offset_x = canvas_x - (image_point[0] * self.scale)
        self.offset_y = canvas_y - (image_point[1] * self.scale)
        self.render()

    def pan(self, dx: int, dy: int) -> None:
        self.offset_x += dx
        self.offset_y += dy
        self.render()

    def on_undo(self, event: tk.Event[tk.Misc] | None = None) -> None:
        if self.points:
            self.points.pop()
            self.render()

    def on_skip(self, event: tk.Event[tk.Misc] | None = None) -> None:
        self.result = []
        self.root.destroy()

    def on_quit(self, event: tk.Event[tk.Misc] | None = None) -> None:
        self.result = None
        self.root.destroy()

    def on_save(self, event: tk.Event[tk.Misc] | None = None) -> None:
        if len(self.points) == self.point_count:
            self.result = list(self.points)
            self.root.destroy()

    def run(self) -> list[tuple[float, float]] | None:
        self.root.mainloop()
        return self.result


def resize_for_display(image_bgr: np.ndarray, max_side: int = 1500) -> tuple[np.ndarray, float]:
    height, width = image_bgr.shape[:2]
    scale = min(1.0, float(max_side) / float(max(height, width)))
    if scale >= 0.999:
        return image_bgr.copy(), 1.0
    resized = cv2.resize(image_bgr, (int(round(width * scale)), int(round(height * scale))), interpolation=cv2.INTER_AREA)
    return resized, scale


def draw_annotation_view(base_bgr: np.ndarray, points: list[tuple[int, int]], record: ManifestRecord, done_count: int, total_count: int) -> np.ndarray:
    canvas = base_bgr.copy()
    instructions = [
        f"{record.relative_path}  specimen={record.specimen_id}  {done_count}/{total_count}",
        point_order_hint(max(4, len(points) if len(points) > 0 else 4)),
        "Keys: Enter/Space save   U undo   S skip   Q quit",
    ]
    y = 28
    for line in instructions:
        cv2.putText(canvas, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (15, 15, 15), 3, cv2.LINE_AA)
        cv2.putText(canvas, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245, 245, 245), 1, cv2.LINE_AA)
        y += 28

    for idx, point in enumerate(points):
        cv2.circle(canvas, point, 7, (0, 220, 255), -1, cv2.LINE_AA)
        cv2.putText(canvas, str(idx + 1), (point[0] + 8, point[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, str(idx + 1), (point[0] + 8, point[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    if len(points) >= 2:
        cv2.polylines(canvas, [np.array(points, dtype=np.int32)], len(points) == 4, (0, 255, 120), 2, cv2.LINE_AA)
    return canvas


def clamp_view_origin(image_shape: tuple[int, int], view_width: int, view_height: int, origin_x: int, origin_y: int) -> tuple[int, int]:
    height, width = image_shape[:2]
    max_x = max(0, width - view_width)
    max_y = max(0, height - view_height)
    return max(0, min(origin_x, max_x)), max(0, min(origin_y, max_y))


def draw_raw_view(
    image_bgr: np.ndarray,
    points: list[tuple[float, float]],
    origin_x: int,
    origin_y: int,
    view_width: int,
    view_height: int,
    record: ManifestRecord,
    done_count: int,
    total_count: int,
) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    origin_x, origin_y = clamp_view_origin(image_bgr.shape, view_width, view_height, origin_x, origin_y)
    visible = image_bgr[origin_y : min(height, origin_y + view_height), origin_x : min(width, origin_x + view_width)].copy()
    if visible.shape[0] < view_height or visible.shape[1] < view_width:
        padded = np.zeros((view_height, view_width, 3), dtype=np.uint8)
        padded[: visible.shape[0], : visible.shape[1]] = visible
        visible = padded

    overlay_points: list[tuple[int, int]] = []
    for x_value, y_value in points:
        local_x = int(round(x_value - origin_x))
        local_y = int(round(y_value - origin_y))
        if 0 <= local_x < view_width and 0 <= local_y < view_height:
            overlay_points.append((local_x, local_y))

    instructions = [
        f"{record.relative_path}  specimen={record.specimen_id}  {done_count}/{total_count}",
        f"Raw view at 1:1 pixels. origin=({origin_x},{origin_y}) size={view_width}x{view_height}",
        point_order_hint(max(4, len(points) if len(points) > 0 else 4)),
        "Keys: Enter/Space save   U undo   S skip   Q quit   Arrows/WASD pan",
    ]
    y = 28
    for line in instructions:
        cv2.putText(visible, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (15, 15, 15), 3, cv2.LINE_AA)
        cv2.putText(visible, line, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (245, 245, 245), 1, cv2.LINE_AA)
        y += 28

    for idx, point in enumerate(overlay_points):
        cv2.circle(visible, point, 7, (0, 220, 255), -1, cv2.LINE_AA)
        cv2.putText(visible, str(idx + 1), (point[0] + 8, point[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(visible, str(idx + 1), (point[0] + 8, point[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    if len(overlay_points) >= 2:
        cv2.polylines(visible, [np.array(overlay_points, dtype=np.int32)], len(overlay_points) == 4, (0, 255, 120), 2, cv2.LINE_AA)
    return visible


def annotate_image(
    record: ManifestRecord,
    done_count: int,
    total_count: int,
    display_mode: str,
    window_width: int,
    window_height: int,
    point_count: int,
) -> list[tuple[float, float]] | None:
    viewer = ViewerAnnotator(
        record,
        done_count,
        total_count,
        window_width,
        window_height,
        point_count,
    )
    return viewer.run()


def row_from_points(record: ManifestRecord, image_shape: tuple[int, int], points: list[tuple[float, float]]) -> dict[str, str]:
    height, width = image_shape
    row = {
        "relative_path": record.relative_path,
        "specimen_id": record.specimen_id,
        "split": record.split,
        "image_width": str(width),
        "image_height": str(height),
        "point_count": str(len(points)),
    }
    for idx, (x_value, y_value) in enumerate(points, start=1):
        row[f"x{idx}"] = f"{x_value:.3f}"
        row[f"y{idx}"] = f"{y_value:.3f}"
    return row


def main() -> None:
    args = parse_args()
    project_dir = Path(args.project_dir)
    source_dir = Path(args.source_images) if args.source_images else None
    output_csv = Path(args.output_csv) if args.output_csv else project_dir / "config" / "neck_patch_landmarks.csv"
    existing = load_existing_annotations(output_csv)
    records = infer_records(project_dir, Path(args.manifest) if args.manifest else None, source_dir)
    specimens = set(args.specimen) if args.specimen else None
    filtered = filter_records(records, args.split, specimens)
    filtered = sample_annotation_records(
        filtered,
        args.max_specimens,
        args.gallery_per_specimen,
        args.gallery_sampling,
        args.query_per_specimen,
    )

    pending: list[ManifestRecord] = []
    for record in filtered:
        already_done = record.relative_path in existing
        if already_done and not args.overwrite:
            continue
        pending.append(record)

    if args.max_images is not None:
        pending = pending[: args.max_images]

    if not pending:
        print("No images need annotation with the current filters.")
        return

    completed = 0
    try:
        for index, record in enumerate(pending, start=1):
            points = annotate_image(
                record,
                completed,
                len(pending),
                args.display_mode,
                args.window_width,
                args.window_height,
                args.point_count,
            )
            if points is None:
                break
            if len(points) == 0:
                continue

            annotation_image = load_annotation_image(record.image_path)
            existing[record.relative_path] = row_from_points(record, (annotation_image.height, annotation_image.width), points)
            save_annotations(output_csv, existing)
            completed += 1
    finally:
        cv2.destroyAllWindows()

    print(f"Saved landmarks to: {output_csv}")
    print(f"Annotated this session: {completed}")


if __name__ == "__main__":
    main()
