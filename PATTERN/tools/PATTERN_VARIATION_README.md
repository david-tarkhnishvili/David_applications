# Darevskia Pattern Variation Workflow

## Purpose

`darevskia_pattern_variation.py` extends the current `5-point curved belt` workflow from identification to morphological pattern analysis.

It is designed for questions such as:

- what is the consensus spotted dorsal pattern across a sample?
- which specimens deviate most strongly from that consensus?
- how asymmetric is the dorsal pattern within each specimen?

The script reuses the same successful preprocessing as the identification workflow:

1. `5` landmarks are placed along the vertebral stripe.
2. A curved dorsal belt is extracted in a shared coordinate system.
3. Fine scale reflections and scale-level texture are suppressed.
4. A broad dark-spot representation is derived from the belt.

This makes pattern analysis possible on homologous body regions rather than on arbitrary raw photographs.

## Biological Logic

The method assumes that:

- the most informative structure is the dorsal dark-spot pattern, not the exact brightness of individual scales
- homologous points along the dorsum can be aligned with the `5-point belt` workflow
- large-spot shape and spatial arrangement are more biologically meaningful than tiny scale-scale differences

So the analysis focuses on:

- belt-aligned dark-pattern intensity
- belt-aligned large-spot outlines
- left-right similarity after mirroring around the dorsal midline

## Main Inputs

The script expects the same project organization as the matcher:

```text
project_folder/
  gallery/
  query/
  config/
    manifest.csv
    axis_belt_landmarks.csv
  outputs/
```

Minimum requirements:

- a project folder with images already arranged into `gallery` and `query`
- `5-point` landmarks saved in `axis_belt_landmarks.csv`

Optional:

- `manifest.csv`
- `source_images` folder

## Main Command

Example:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe "E:\Darevskia_ID\darevskia_pattern_variation.py" --project-dir "E:\Darevskia_ID" --landmarks "E:\Darevskia_ID\config\axis_belt_landmarks.csv" --include-split both --max-specimens 12 --gallery-per-specimen 4 --gallery-sampling last --query-per-specimen 1 --belt-breadth-fraction 0.14 --output "E:\Darevskia_ID\outputs\pattern_variation_run_1"
```

## Methodology

### 1. Belt standardization

Each image is converted into a curved dorsal belt using the `5` landmarks:

- neck
- anterior dorsum
- middle dorsum
- posterior dorsum
- hindbody / tail-base

This gives each specimen a standardized dorsal strip in the same coordinate system.

### 2. Pattern enhancement

Inside the belt:

- bright scale reflections are suppressed
- fine scale texture is smoothed
- a dark-spot map is extracted
- a large-spot outline representation is generated

This reduces the influence of scale-by-scale brightness and emphasizes larger blotches and spot fields.

### 3. Consensus image

All selected images are normalized into the same belt coordinates and averaged.

The script saves several consensus views:

- `consensus_pattern.png`
  Mean dark-pattern intensity in belt space
- `consensus_outline.png`
  Thresholded mean spot-outline structure
- `consensus_spot_frequency.png`
  Heatmap showing where dark spots occur most often across the sample
- `mean_absolute_deviation.png`
  Pixelwise average deviation from the consensus pattern

### 4. Deviation from consensus

For each image, the script compares the belt pattern to the global consensus using:

- similarity of the normalized pattern map
- difference from the consensus spot-distribution map

These are combined into a `deviation_score`.

Interpretation:

- lower `deviation_score` = more similar to the sample consensus
- higher `deviation_score` = more unusual pattern

### 5. Left-right asymmetry

For each image:

1. the belt is split into left and right halves
2. the right half is mirrored
3. the mirrored right half is compared to the left half

The script combines:

- map similarity
- binary spot-pattern difference

into an `asymmetry_score`.

Interpretation:

- lower `asymmetry_score` = more symmetric dorsal pattern
- higher `asymmetry_score` = more asymmetric dorsal pattern

## Main Outputs

Inside the chosen output folder:

- `summary.json`
  Overall run summary
- `image_variation.csv`
  Per-image deviation and asymmetry values
- `specimen_variation.csv`
  Per-specimen means and standard deviations
- `belt/`
  Standardized curved belts
- `spots/`
  Large-spot outline representations
- `overlay/`
  Original images with the belt placement shown
- `consensus/`
  Global consensus images and heatmaps
- `deviation/`
  Per-image heatmaps showing where each image differs from the consensus
- `asymmetry/`
  Per-image heatmaps showing left-right mismatch
- `specimens/`
  Mean pattern and mean outline summaries for each specimen

## How to Read the Results

### `image_variation.csv`

Important columns:

- `deviation_score`
  How far the image lies from the consensus pattern
- `consensus_map_similarity`
  Correlation-like similarity to the consensus pattern map
- `consensus_binary_distance`
  Difference from the consensus spot distribution
- `asymmetry_score`
  Overall left-right asymmetry
- `left_right_map_similarity`
  Similarity between left and mirrored right pattern maps
- `left_right_binary_distance`
  Difference between left and mirrored right spot distributions

### `specimen_variation.csv`

This file summarizes each specimen across all selected images:

- `mean_deviation_score`
- `sd_deviation_score`
- `mean_asymmetry_score`
- `sd_asymmetry_score`

This is usually the best table for biological interpretation.

## Practical Recommendations

- Use the same successful landmarking protocol as the identification workflow.
- Keep `belt-breadth-fraction = 0.14` as the baseline unless there is a biological reason to change it.
- Use the same image subset definition when comparing different runs.
- Inspect `belt` and `spots` together with the numeric tables.
- Treat images with very poor belt quality cautiously, even if they still receive numeric scores.

## Current Limitations

- The method measures variation in a standardized belt, not whole-body appearance.
- It is still sensitive to landmark placement quality.
- Consensus images are sample-dependent: changing which images are included changes the consensus.
- The asymmetry metric is dorsal-pattern asymmetry in belt coordinates, not a general body asymmetry measure.

## Recommended Use

This workflow is best used for:

- exploratory pattern-variation analysis
- ranking specimens by pattern unusualness
- estimating relative asymmetry across specimens
- building visual consensus references for a dataset

It is not a substitute for formal population-genetic or developmental analysis, but it provides a reproducible phenotype-based summary of dorsal pattern variation.
