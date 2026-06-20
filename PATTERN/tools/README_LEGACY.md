# Darevskia ID Prototype

This folder now contains two workflows.

## 1. Flat-folder prototype

Use this when all photos are still in one folder and specimen membership is defined by `specimen_ranges.csv`.

Run:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_id.py --images "E:\Lizard _ AI" --config "g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\specimen_ranges.csv" --output "g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\runs\run1"
```

## 2. Project-folder workflow

This is the cleaner capture-recapture structure:

```text
project_folder/
  gallery/
    specimen_1/
    specimen_2/
    ...
  query/
    specimen_1/
    specimen_2/
    ...
  config/
    manifest.csv
    settings.json
  outputs/
```

### Step A. Prepare the project folder

This copies the original images, puts all but the last image of each specimen into `gallery`, and places the last image into `query`.

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\prepare_darevskia_project.py --source-images "E:\Lizard _ AI" --ranges "g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\specimen_ranges.csv" --project-dir "E:\Darevskia_ID"
```

### Step B. Run the project workflow

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_project_id.py --project-dir "E:\Darevskia_ID"
```

### Optional open-set mode

If some query images may belong to individuals that are absent from the gallery, enable rejection as a likely new specimen:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_project_id.py --project-dir "E:\Darevskia_ID" --allow-new-specimen
```

The current defaults are:

- `--new-specimen-threshold 0.22`
- `--new-specimen-margin 0.04`

Those values can be tuned after inspecting real scores.

### Optional quick test

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_project_id.py --project-dir "E:\Darevskia_ID" --max-gallery 20 --max-query 4
```

### Faster balanced validation

This is usually a better quick test than raw `--max-gallery` because it samples evenly by specimen:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_project_id.py --project-dir "E:\Darevskia_ID" --max-specimens 4 --gallery-per-specimen 4 --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\balanced_run_specimens_1_4" --allow-new-specimen
```

## Main outputs

- `predictions.csv`: one row per query image
- `summary.json`: accuracy summary
- `standardized/`: aligned full-body images
- `roi/`: dorsal crops used for comparison
- `qc/`: side-by-side visual checks for each prediction

## 3. Semi-manual 4-corner neck patch workflow

This workflow is for the case where the most informative area is a very specific square near the neck and forelimb, and automatic neck detection is not reliable enough.

The idea is:

1. You click the four corners of the desired patch on each image.
2. The script warps that quadrilateral to the same square size every time.
3. Matching is done only on those standardized patch images.

### Step A. Annotate landmarks

Run:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID"
```

Suggested click order:

- corner 1: upper-left
- corner 2: upper-right
- corner 3: lower-right
- corner 4: lower-left

Useful keys:

- `Enter` or `Space`: save this image after 4 clicks
- `U`: undo the last click
- `S`: skip this image for now
- `Q` or `Esc`: quit and keep everything already saved

Landmarks are saved incrementally to:

- `E:\Darevskia_ID\config\neck_patch_landmarks.csv`

### Step B. Run patch-only matching

After annotating at least a small gallery/query subset, run:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_patch_id.py --project-dir "E:\Darevskia_ID" --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling spaced --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\manual_patch_run_1"
```

The main outputs are:

- `patch/`: the standardized square patch extracted from each image
- `overlay/`: the original image with the clicked quadrilateral drawn on top
- `qc/`: query vs best-match comparison panels
- `predictions.csv`
- `summary.json`

### Recommended first test

To keep the first annotation session short, annotate:

- specimens `1` to `4`
- about `4` gallery images per specimen
- `1` query image per specimen

Then run the command above.

This is the cleanest way to test whether the specific neck patch really carries enough individual signal before trying more automation.

## Notes

- The current matcher is still a prototype.
- The most important QC step is checking whether `standardized/` and `roi/` look biologically sensible.
- If the standardized posture or dorsal crop looks wrong, improve those steps before trusting the identification scores.
- In open-set mode, the runner may output `NEW_SPECIMEN` instead of forcing a gallery match.

## 4. Broad dorsal spot matcher

This is the newer HotSpotter-like direction for cases where the full constellation of dark dorsal spots is easier to recognize than any single small patch.

The workflow:

1. Use the original gallery/query project structure.
2. Build a broad dorsal crop automatically from each photo.
3. Convert the crop into a dark-spot map.
4. Extract local features from that map and cache gallery descriptors.
5. Match each query against the cached gallery.

Run a first small test like this:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_spot_matcher.py --project-dir "E:\Darevskia_ID" --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\spot_match_run_1" --rebuild-cache
```

Important outputs:

- `predictions.csv`
- `summary.json`
- `preview/`: broad dorsal crops used for matching
- `spots/`: dark-spot maps used for feature extraction
- `qc/`: query vs best-match panels

Because the gallery features are cached, rerunning the same gallery later should be much faster when `--rebuild-cache` is omitted.

## 5. Four-point dorsal region plus spot matcher

This is the hybrid workflow for cases where:

- the dark dorsal pattern is biologically informative
- but automatic lizard-vs-grass separation is still unreliable

The idea is:

1. You click `4` corners around a broad dorsal region.
2. The script warps that quadrilateral to the same rectangle every time.
3. The spot matcher runs only inside that warped rectangle.

This avoids most background leakage while keeping the matching step automatic.

### Step A. Annotate a 4-point dorsal quadrilateral

Annotate the gallery images:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 4 --split gallery --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --output-csv "E:\Darevskia_ID\config\dorsal_quad_landmarks.csv"
```

Then annotate the query images into the same file:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 4 --split query --max-specimens 4 --query-per-specimen 1 --output-csv "E:\Darevskia_ID\config\dorsal_quad_landmarks.csv"
```

Use this click order:

- `1`: upper-left
- `2`: upper-right
- `3`: lower-right
- `4`: lower-left

### Step B. Run the hybrid matcher

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_quad_spot_matcher.py --project-dir "E:\Darevskia_ID" --landmarks "E:\Darevskia_ID\config\dorsal_quad_landmarks.csv" --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\quad_spot_run_1" --rebuild-cache
```

Useful outputs:

- `warped/`: the standardized dorsal rectangles used for comparison
- `overlay/`: the original images with your 4-point region drawn on top
- `spots/`: dark-spot maps extracted from the warped region
- `qc/`: query vs best-match side-by-side panels
- `predictions.csv`
- `summary.json`

If the first run still includes too much boundary noise, reduce the warped border influence with a slightly larger inner trim:

```powershell
... --inner-margin 0.05
```

If you want a larger biological area, increase the marked quadrilateral rather than trying to rely on automatic segmentation.

## 6. Three-landmark, three-window dorsal matcher

This workflow is for cases where one manually chosen patch is still too unstable, but you want a scalable manual localization rule.

The idea is:

1. Click `3` landmarks in a fixed biological order:
   - neck center
   - middle dorsum center
   - hindbody / tail-base center
2. The script derives `3` standardized body-aligned windows automatically:
   - anterior
   - middle
   - posterior
3. Matching combines evidence from all three windows instead of relying on one patch.

### Step A. Annotate 3 landmarks

Annotate gallery images:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 3 --split gallery --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --output-csv "E:\Darevskia_ID\config\tripoint_landmarks.csv"
```

Then annotate query images into the same file:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 3 --split query --max-specimens 4 --query-per-specimen 1 --output-csv "E:\Darevskia_ID\config\tripoint_landmarks.csv"
```

### Step B. Run the tripoint matcher

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_tripoint_spot_matcher.py --project-dir "E:\Darevskia_ID" --landmarks "E:\Darevskia_ID\config\tripoint_landmarks.csv" --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\tripoint_spot_run_1"
```

Main outputs:

- `overlay/`: original images with the 3 landmarks and the derived windows drawn on top
- `windows/`: the three extracted standardized windows for each image
- `spots/`: dark-spot maps for each window
- `qc/`: side-by-side comparison panels
- `predictions.csv`
- `summary.json`

You can tune the window sizes if needed:

- `--window-length-fraction`
- `--window-width-fraction`
- `--inner-margin`

This is the recommended next workflow when one manually drawn quadrilateral is still too specimen-specific or unstable.

## 7. Five-landmark curved dorsal belt matcher

This workflow is for cases where body curvature makes a straight-axis model too unstable.

The idea is:

1. Click `5` landmarks along the dorsal midline in a fixed biological order:
   - neck
   - anterior dorsum
   - middle dorsum
   - posterior dorsum
   - hindbody / tail-base
2. The script fits a curved dorsal axis through those points.
3. It builds a standardized `belt` around that axis, with user-controlled breadth.
4. Matching is then done automatically on the warped belt image.
5. Specimens are now scored by `consensus` across their best supporting gallery images, not just one winning gallery photo.

This keeps the compared region broad and consistent while following bent bodies much better than one rectangle or a straight 3-point axis.

### Step A. Annotate 5 landmarks

Annotate gallery images:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 5 --split gallery --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --output-csv "E:\Darevskia_ID\config\axis_belt_landmarks.csv"
```

Then annotate query images into the same file:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\annotate_neck_patch.py --project-dir "E:\Darevskia_ID" --point-count 5 --split query --max-specimens 4 --query-per-specimen 1 --output-csv "E:\Darevskia_ID\config\axis_belt_landmarks.csv"
```

Use this click order:

- `1`: neck
- `2`: anterior dorsum
- `3`: middle dorsum
- `4`: posterior dorsum
- `5`: hindbody / tail-base

### Step B. Run the curved-belt matcher

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe g:\My Drive\Lizards\RUDIS_GROUP\darevskia_id\darevskia_axis_belt_matcher.py --project-dir "E:\Darevskia_ID" --landmarks "E:\Darevskia_ID\config\axis_belt_landmarks.csv" --max-specimens 4 --gallery-per-specimen 4 --gallery-sampling last --query-per-specimen 1 --output "E:\Darevskia_ID\outputs\axis_belt_run_1"
```

The current default belt breadth is:

- `--belt-breadth-fraction 0.14`

To make the belt broader or narrower, adjust:

- `--belt-breadth-fraction 0.18`

For example, a broader belt:

```powershell
... --belt-breadth-fraction 0.24
```

Or specify an absolute breadth in pixels on the resized working image:

```powershell
... --belt-breadth-px 220
```

Useful outputs:

- `overlay/`: original images with the 5-point axis and belt boundaries drawn
- `belt/`: standardized curved dorsal belt images
- `spots/`: dark-spot maps derived from the belt
- `qc/`: query vs best-match side-by-side panels
- `predictions.csv`
- `summary.json`

This is the best current workflow when curvature is one of the main reasons for mismatch.
