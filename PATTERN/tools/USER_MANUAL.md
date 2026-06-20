# Darevskia ID User Manual

## Purpose

This tool is used to identify individual `Darevskia` lizards from dorsal photographs.

The current best-performing workflow is:

1. Organize images into `gallery` and `query` folders by specimen.
2. Mark `5` landmarks along the vertebral stripe on each image.
3. Build a curved dorsal belt from those landmarks.
4. Compare the dorsal belt of each query image against the gallery.
5. Inspect the match table and visual QC panels.

This manual is written for routine use, not for software development.

## Current extra analysis

Besides specimen identification, the current application can also run a `pattern variation` analysis.

That workflow uses the same successful `5-point curved belt` landmarking and can:

- build a consensus dorsal-pattern image
- estimate deviation of each image and specimen from that consensus
- estimate left-right asymmetry of the dorsal pattern

For the methodology and output interpretation, see:

- `PATTERN_VARIATION_README.md`

## Folder structure

The recommended project folder is:

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
    axis_belt_landmarks.csv
  outputs/
```

Meaning:

- `gallery/`: reference photos of known individuals
- `query/`: photos to identify
- `config/`: configuration and landmark files
- `outputs/`: results of each run

## How individuals should be organized

This is one of the most important points.

The program does **not** create individuals from the field `Specimen IDs`.
Individuals must already be organized by the folder structure itself.

Correct organization:

```text
gallery/
  specimen_1/
    image_a.jpg
    image_b.jpg
  specimen_2/
    image_c.jpg
    image_d.jpg

query/
  specimen_1/
    query_1.jpg
  specimen_2/
    query_2.jpg
```

Meaning:

- all gallery images of one known individual go into one `specimen_X` subfolder
- query images are also grouped by specimen if you are validating the method
- if you are doing a true unknown identification task, you can still keep query images in `query/`, but their true identity is then only for your own record

So:

- the **subfolders** define specimen identity
- the `Specimen IDs` box only selects which already existing specimen folders should be processed

## What the web app fields mean

The browser app shows many fields because it exposes both the current recommended workflow and some older experimental options.
Below is the practical meaning of the most important fields.

### Project Folder

This should be the main folder that contains:

- `gallery/`
- `query/`
- `config/`
- `outputs/`

Example:

- `E:\Darevskia_ID`

In normal use, this is the main path you set once and then keep reusing.

### Split

The `Split` field controls which images will be opened for annotation.

Options:

- `gallery`: annotate only gallery images
- `query`: annotate only query images
- `both`: annotate both gallery and query images in one session

Why `both` exists:

- sometimes you may want one continuous annotation pass without reopening the tool

In practice, the clearest workflow is usually:

- first `gallery`
- then `query`

### Specimen IDs (comma separated, optional)

This field is only a **filter**.

Example:

- `1,2,3`

means:

- work only on `specimen_1`, `specimen_2`, and `specimen_3`

If left empty:

- all specimen folders in the selected split are eligible

What it does **not** do:

- it does not create individuals
- it does not assign images to individuals
- it does not rename folders

### Manifest CSV

`manifest.csv` is a table describing the project contents.

It associates images with:

- specimen ID
- split (`gallery` or `query`)
- relative path
- source file name

So yes, in practical terms it is a CSV that helps associate images with individuals and splits.

For routine use, you usually do **not** need to edit it manually.

### Source Images Folder

This field is optional.

Use it only if you want the annotator or matcher to open images from the original source folder instead of the copies stored inside the project.

Example:

- project folder: `E:\Darevskia_ID`
- original photos: `E:\Lizard _ AI`

Then `Source Images Folder` can be set to:

- `E:\Lizard _ AI`

If left empty:

- the program uses the images inside the project folder itself

In most everyday use, leaving it empty is simpler.

### Display Mode

This controls how images are shown in the annotation window.

Current options:

- `viewer`
- `fit`
- `raw`

Practical meaning:

- `viewer`: recommended; zoomable image viewer
- `fit`: image more directly fitted to the screen
- `raw`: less fitted view, closer to original pixel layout

For most users:

- use `viewer`

### Gallery Sampling

This matters only when you are **not** using all gallery images of a specimen.

If you set, for example:

- `gallery_per_specimen = 4`

but a specimen has more than 4 gallery images, then `gallery_sampling` decides **which 4** are used.

Options:

- `first`: earliest images in folder order
- `spaced`: spread images across the full series
- `last`: latest images in folder order

Current recommended setting:

- `last`

because in your dataset the later images are usually more relevant than the earliest white-background ones.

### Point Count

This controls how many landmarks the annotator asks you to place.

Important:

- the app allows more values because the annotator is general
- but the current best matcher uses `5` points

So for the current recommended workflow:

- set `Point Count = 5`

If you enter more than 5:

- the annotation tool can save them
- but the current curved-belt matcher does not yet use those extra points

The field is still useful because longer-bodied animals, such as salamanders, may later benefit from a more detailed body axis.

### Matcher Mode

The app currently shows three matcher modes:

- `5-point curved belt`
- `3-point windows`
- `4-point quadrilateral`

At present, the recommended routine workflow is:

- `5-point curved belt`

The other two remain available because they are older experimental workflows and can still be useful for comparison or troubleshooting.

### Belt Breadth Fraction

This controls how wide the extracted curved dorsal belt is.

Current recommended value:

- `0.14`

Smaller values:

- narrower belt

Larger values:

- broader belt

This is one of the main biological tuning parameters.

### Consensus Top-K

This controls how many gallery images per specimen contribute to the final specimen score.

Current recommended value:

- `2`

This means the program does not trust only one winning gallery image, but instead uses consensus from the best supporting images of the same specimen.

## Recommended workflow

### Step 1. Prepare the project

If the images are still in one flat folder, use the project preparation script first.

If the project is already organized into:

- `gallery/specimen_X/`
- `query/specimen_X/`

then you can work directly in the browser app.

### Step 2. Mark landmarks

For each image, place `5` landmarks along the dorsal midline in this order:

1. neck
2. anterior dorsum
3. middle dorsum
4. posterior dorsum
5. hindbody / tail-base

These landmarks are used to build a curved dorsal belt that follows the lizard body even when the animal is bent.

For the current best workflow, all 5 points should lie roughly along the vertebral stripe.

### Step 3. Run identification

The current best settings are:

- curved belt workflow
- `belt-breadth-fraction = 0.14`
- `consensus-top-k = 2`

These settings compare each query specimen against multiple gallery images of each specimen and use specimen-level consensus instead of only one winning image.

### Step 4. Check results

Inspect:

- `summary.json`
- `predictions.csv`
- `qc/`
- `belt/`

The most important files are:

- `predictions.csv`: table of matches
- `qc/`: side-by-side visual comparison panels

## Recommended browser-app workflow

If you are using the browser app, the easiest routine workflow is:

1. Set `Project Folder` to your project path, for example `E:\Darevskia_ID`.
2. In the annotation form:
   - choose `split = gallery`
   - choose `point_count = 5`
   - annotate the gallery images
3. Repeat for:
   - `split = query`
4. In the matcher form:
   - choose `matcher_mode = 5-point curved belt`
   - set `belt_breadth_fraction = 0.14`
   - set `consensus_top_k = 2`
5. Run the matcher.
6. Inspect:
   - `summary.json`
   - `predictions.csv`
   - `qc/`

## How to read predictions.csv

Important columns:

- `query_file`: the query image
- `true_specimen`: the known specimen ID, if available
- `predicted_specimen`: predicted specimen
- `best_score`: best specimen-level score
- `second_specimen`: runner-up specimen
- `second_score`: runner-up score
- `score_margin`: difference between best and second score
- `consensus_gallery_files`: gallery images that supported the final specimen-level decision

Interpretation:

- High `best_score` and large `score_margin`: more convincing match
- Small `score_margin`: ambiguous match, inspect QC carefully

## Practical advice for landmark placement

Try to follow one consistent rule for all specimens:

- stay near the dorsal midline
- avoid the head itself
- avoid the tail beyond the tail-base
- avoid putting points on limbs
- keep the landmarks on the patterned back, not on surrounding background

Consistency matters more than drawing a “perfect” axis on one image.

## Practical advice for belt width

The belt width controls how much of the dorsum is included.

- Too broad: may include body edges, limbs, or irrelevant texture
- Too narrow: may miss informative lateral blotches

Current recommended starting value:

- `0.14`

If needed:

- try `0.12` for slightly narrower
- try `0.16` for slightly broader

## What counts as a good result

A good result has:

- the correct specimen predicted
- a clearly higher best score than second score
- visually similar belts and spot maps in the QC panel

## What counts as a warning sign

Be cautious if:

- the top two scores are very close
- the belt includes too much irrelevant area
- the QC panel looks biologically wrong even if the table says “correct”

## Current limitations

The current system is still a prototype.

Known limitations:

- some specimens can still be very similar
- small score margins can produce unstable labels
- the user still needs to place landmarks manually

## Recommended current usage

At the moment, the safest practical workflow is:

1. run the curved-belt matcher
2. inspect `predictions.csv`
3. use the QC panels as final human control

This is already useful for speeding up manual identification, even if it is not yet fully automatic.
