# Darevskia ID Web App Specification

## Goal

Build a simple local browser app for routine use of the current best workflow:

- `5` landmarks along the vertebral stripe
- curved dorsal belt extraction
- specimen-level consensus matching

This app should reduce command-line work and make project execution easier for end users.

## Recommended architecture

Use the same style as the existing local web apps in this workspace:

- Python script
- built-in `http.server`
- background job threads
- JSON job records
- browser UI on `127.0.0.1`

This avoids extra dependencies and matches existing patterns already used in the project.

## Main screens

### 1. Home

Purpose:

- choose or review project folder
- see recent runs
- open latest outputs

Show:

- selected project path
- current landmark file
- last run summary
- list of recent jobs

### 2. Project setup

Purpose:

- define where `gallery` and `query` are
- optionally prepare a new project from a flat image folder

Inputs:

- project folder
- source image folder
- ranges file, if needed

Actions:

- prepare project
- refresh manifest

### 3. Landmarking

Purpose:

- guide the user through landmark placement

Inputs:

- split: `gallery` or `query`
- specimens to annotate
- number of points, default `5`

Behavior:

- launch the existing annotation tool
- after the annotation window closes, refresh status in the browser

Show:

- how many images already have landmarks
- how many remain
- percent complete

### 4. Matching

Purpose:

- run the curved-belt matcher with user-friendly settings

Inputs:

- max specimens
- gallery images per specimen
- query images per specimen
- belt breadth fraction
- consensus top-k
- output run name

Advanced options:

- allow new specimen
- new specimen threshold
- new specimen margin

Actions:

- run matcher

Show:

- live job status
- estimated progress
- output folder

### 5. Results

Purpose:

- inspect outputs without browsing folders manually

Show:

- summary table
- predictions table
- QC images
- links to belt and overlay images

Filters:

- specimen
- correct / incorrect
- low score margin

## Progress reporting

The app should show a simple percentage indicator.

Two kinds of progress:

### Annotation progress

Progress can be estimated as:

- annotated images / expected images

This is easy to calculate from:

- `manifest.csv`
- landmark CSV

### Matching progress

Progress can be estimated from output counts:

- overlays written
- belts written
- spots written
- QC panels written

For a more robust version later, the matcher could also emit a small JSON status file during the run.

## Recommended default settings

For the current workflow, the app should default to:

- `point_count = 5`
- `belt_breadth_fraction = 0.14`
- `consensus_top_k = 2`
- `gallery_sampling = last`

## Recommended output behavior

For every run, the app should create a named run folder under:

```text
project_folder/outputs/
```

The browser should then show:

- summary
- predictions
- QC thumbnails

## Manual and help text inside the app

The app should include a short built-in help panel explaining:

- click order for the 5 landmarks
- meaning of belt breadth
- meaning of score margin
- why QC images still need to be checked

## Scope for first version

The first web app version does not need to:

- do automatic landmarking
- replace the existing Tkinter annotator
- make final biological decisions automatically

It only needs to:

- launch the existing workflow cleanly
- track progress
- present results in one place

## Recommended implementation order

1. Create local web app skeleton
2. Add project selection and recent jobs
3. Add annotation launcher and annotation progress
4. Add matcher form and background run
5. Add results table and QC browser

This would already be a major usability improvement over pure command-line usage.
