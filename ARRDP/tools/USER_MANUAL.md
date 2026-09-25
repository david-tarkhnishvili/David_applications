# ARRDP User Manual

## Purpose and scope

ARRDP (Amphibian and Reptile Recognition by Dorsal Pattern) is a local decision-support application for comparing dorsal photographs. It was developed from *Darevskia* lizard photographs. It can be explored with other amphibians or reptiles, but its accuracy for another taxon, camera setup, or pattern type must be validated before it is used for biological conclusions or individual identification.

ARRDP is not a fully automatic identification authority. Review its visual quality-control panels and scores before accepting any match.

## What you need

- Windows, macOS, or Linux with Python 3.10 or later.
- A folder of reference images for known individuals.
- Query images to compare against the references.
- Images showing the dorsum clearly enough to place five landmarks.

## One-time installation

Open a terminal in the ARRDP folder and run:

```powershell
python -m pip install -r requirements.txt
```

Then start the program by double-clicking `START_ARRDP.bat`. It opens locally at `http://127.0.0.1:8094/`; no account or password is required.

## Project layout

```text
ARRDP/
  gallery/
    individual_A/
      reference_1.jpg
      reference_2.jpg
  query/
    sample_1/
      image_to_identify.jpg
  config/
  outputs/
```

Each gallery subfolder represents one known individual from the reference session. Put photographs from a later capture session into `query/`; their identity is genuinely unknown when the analysis begins. You may use neutral query-subfolder labels such as `session2_001`, `session2_002`, and so on. ARRDP compares every query photograph with the reference gallery and proposes the most similar known individual. It does not use the query-subfolder name to decide the match.

## Recommended workflow

1. Put known-individual images in `gallery/<individual>/` and images to identify in `query/<sample>/`.
2. Start ARRDP.
3. In **Annotation**, select `gallery`, set `Point count = 5`, and mark every gallery image.
4. Repeat for `query` images.
5. In **Matching**, select **5-point curved belt**.
6. Begin with belt breadth fraction `0.14` and consensus top-k `2`.
7. Run the matcher and inspect the outputs.
8. Treat the ranking as a shortlist: use the QC panels and direct visual comparison of the dorsal patterns to establish or reject identity.

Place the five points in this order: neck, anterior dorsum, middle dorsum, posterior dorsum, and hindbody/tail base. Keep them on the dorsal midline, avoid the limbs and background, and use the same anatomical rule for every image.

## Reading results

Each run creates a new directory in `outputs/`. The important items are:

- `predictions.csv`: predicted individual, score, runner-up, and score margin.
- `summary.json`: run parameters and validation summary.
- `qc/`: side-by-side query/reference checks.
- `belt/`: standardised curved dorsal regions used for comparison.

Large score margins and biologically similar QC panels are more convincing than a prediction alone. A close top-two score, an implausible belt, or a mismatch in QC means the result should be treated as uncertain. Direct expert visual comparison is the safest final identity check.

## Other modes

The 3-point window and 4-point quadrilateral modes are retained experimental alternatives. Pattern variation analyses use the same five-point landmarks. Use these only after comparison against labelled data.

## Python code and processing design

ARRDP is written in Python. `arrdp_web_app.py` runs a local `http.server` browser interface and sends annotation, matching, variation, and distance-tree jobs to Python scripts in `tools/`. Long jobs run in background threads, so the browser can show job records and output links. The annotation tool uses a desktop Tkinter image window for the landmark clicks. Numerical operations use NumPy, pandas, OpenCV, scikit-learn, Pillow, and matplotlib.

The recommended `darevskia_axis_belt_matcher.py` workflow is: (1) obtain five user landmarks; (2) fit a curved dorsal centreline; (3) resample a fixed-size belt around that line; (4) calculate dark-spot, geometry, map, and histogram evidence; (5) compare each query with gallery photographs; and (6) calculate an individual-level consensus score from the best `K` gallery photographs for every candidate individual. `K = 2` means that the top two supporting reference photographs are averaged rather than trusting one photograph.

This matching consensus is a consensus *score*, not a newly generated pixel-average reference image. The Pattern Variation tool does generate visual consensus pattern, outline, and spot-frequency images from multiple aligned belts. These can be compared between sampling sessions visually and through the variation/distance outputs.

## Establishing identity and calibrating thresholds

The matcher always reports the leading candidate, but it should not be accepted automatically. Start with relatively low threshold and margin values so that potentially useful matches are not rejected before inspection. Review the highest-scoring candidates first: compare the query and reference QC images and decide whether their dorsal patterns truly support the same individual. Then inspect progressively lower scores.

When a score is too low to support identity after visual examination, set the threshold above that value, or close to the lowest score that still supported a credible identity. Apply the same logic to the score margin: close top-two scores demand more caution because two reference individuals are similarly plausible. This calibration must be based on the user's own photographs, taxon, imaging conditions, and manual expert control; no single numerical threshold is universally valid.

If **Allow new specimen** is enabled, ARRDP assigns `NEW_SPECIMEN` when the best score is below the new-specimen threshold, or when the score margin is below the new-specimen margin and the best score is still weak. Threshold and margin are decision-support settings, not biological proof.

Establish thresholds using labelled photographs from the same taxon, camera method, season, and field protocol. Inspect the QC panels, record correct and incorrect matches, then choose values that meet the desired false-match risk. Keep the selected settings and calibration results with every run.

## Interface reference

### Annotation fields

- **Project Folder**: folder containing `gallery`, `query`, `config`, and `outputs`.
- **Landmark CSV**: file where click coordinates are saved; use the same file for gallery and query.
- **Manifest CSV**: optional explicit image list; leave blank to infer records from folders.
- **Source Images Folder**: optional original-image location; otherwise use project copies.
- **Split**: `gallery`, `query`, or `both` images to annotate.
- **Specimen IDs**: optional comma-separated filter of existing subfolder IDs.
- **Point Count**: use 5 for the curved-belt matcher.
- **Display Mode**: `viewer` is zoomable and recommended; `fit` scales to window; `raw` uses less fitting.
- **Max Images / Max Specimens**: optional limits for a trial run.
- **Gallery Per Specimen / Query Per Specimen**: number selected from each individual.
- **Gallery Sampling**: `first`, `spaced`, or `last` selects which gallery photos are used when limited.
- **Window Width / Height**: annotation-window pixels only; they do not alter the biological belt.
- **Overwrite existing annotations**: replace stored clicks; otherwise existing work is retained.

### Matching fields

- **Project, Landmarks, Manifest, Source Images, Output Folder**: same meanings as above; Output Folder receives this run's products.
- **Matcher Mode**: choose 5-point curved belt for the recommended method; 3-point and 4-point modes are experimental.
- **Max Specimens, Gallery/Query Per Specimen, Max Gallery, Max Query, Gallery Sampling**: sampling limits for the run.
- **Max Side**: maximum working-image dimension before processing; lower is faster but loses detail.
- **Preview Side / Thumb Size**: sizes of preview and thumbnail outputs; do not change biological scores materially.
- **Inner Margin**: fraction trimmed from belt boundaries to reduce edge/background noise.
- **Belt Width / Belt Height**: output dimensions of the rectified belt image; 360 x 900 is the current starting size.
- **Belt Breadth Fraction**: biological belt half-width relative to body scale; start at 0.14. Larger values include more flanks but risk limbs/background.
- **Belt Breadth PX**: absolute-pixel alternative to breadth fraction; leave blank to use the fraction.
- **Consensus Top-K**: number of best gallery photos averaged per candidate individual; start at 2.
- **Window Width/Height/Length Fraction/Width Fraction**: only for the experimental 3-point mode.
- **Allow New Specimen**: enables rejection instead of forcing every query into an existing gallery individual.
- **New Specimen Threshold**: minimum best score required before a match is accepted. Start low enough to review candidate matches, then set it above scores that manual inspection judged insufficient, or near the lowest score that supported identity.
- **New Specimen Margin**: required difference between the best and second candidate. Start permissively, inspect close competitions, then raise it if small margins repeatedly produce uncertain or false identities.

### Pattern variation and distance fields

Pattern Variation repeats the shared project, image-selection, processing-size, inner-margin, belt-size, and belt-breadth fields. **Include Split** controls whether it uses gallery, query, or both. The analysis builds aligned consensus pattern, outline, and spot-frequency images from multiple photographs, quantifies how much each photograph and specimen deviates from that consensus, and measures left-right dorsal-pattern asymmetry. It is useful for comparing change or variation among photographs, individuals, or capture sessions.

Distance Matrix and Tree uses `specimen_variation.csv` to quantify dorsal-pattern dissimilarity among individuals. **Input specimen_variation.csv** selects the variation summary; **Distance Source** selects mean-pattern images or numeric summaries; **Distance Metric** selects Euclidean, Manhattan, or correlation distance; **Standardize summary metrics** scales numeric variables equally; **Image Vector Width/Height** control the resolution used when converting mean patterns to distance vectors. The resulting matrix gives pairwise pattern distances and the UPGMA tree groups more similar dorsal patterns together. It describes pattern similarity; it is not a phylogenetic tree unless separately justified.

## Output-file reference

### predictions.csv

- `query_file`, `true_specimen`, `known_in_gallery`: query identity information; `true_specimen` is for validation only.
- `predicted_specimen`, `best_gallery_specimen`, `new_specimen_flag`, `correct`, `decision_reason`: decision and validation fields.
- `best_score`, `second_specimen`, `second_score`, `score_margin`: rank and confidence evidence.
- `best_match_file`, `consensus_top_k`, `consensus_support_count`, `consensus_score`, `representative_score`, `consensus_gallery_files`: supporting gallery evidence and multi-image consensus details.
- `good_matches`, `inlier_count`, `geom_score`, `map_score`, `hist_score`, `quality_flag`: technical matching diagnostics; use them mainly when investigating a poor result.
- `overlay_file`, `belt_file`, `spot_file`, `qc_file`: paths to the visual audit products.

### Pattern-variation CSV files

`image_variation.csv` contains `specimen_id`, `split`, paths/filenames, `deviation_score`, consensus map/binary measures, left-right asymmetry measures, `quality_flag`, and paths to belt, spots, deviation, and asymmetry images. Higher deviation/asymmetry values indicate greater difference, but must be judged together with images.

`specimen_variation.csv` aggregates each individual: `n_images`, means and standard deviations of deviation/asymmetry, mean consensus and left-right measures, and paths to mean-pattern, mean-outline, and spot-frequency images. `distance_matrix.csv` has one row and column per specimen; diagonal values are zero and larger off-diagonal values mean less similar patterns under the selected distance method.

`summary.json` records parameters, selected image counts, missing-landmark counts, accuracy where known identities exist, and output locations. It is the primary reproducibility record for a run.

## Citation

Until a versioned archival release and DOI exist, cite the exact GitHub release, version, access date, and developer. Suggested form:

`Tarkhnishvili, D. (YEAR). ARRDP: Amphibian and Reptile Recognition by Dorsal Pattern (Version X.Y.Z) [Computer software]. GitHub. https://github.com/david-tarkhnishvili/David_applications`

For a published analysis, also cite the data source and state the ARRDP settings: matcher mode, point count, belt breadth, consensus top-K, threshold, margin, and the human QC rule used.

## Troubleshooting

- If the page does not open, browse to `http://127.0.0.1:8094/`.
- If Python is not found, install Python and enable its command-line option during installation.
- If a matcher says no landmarks are available, annotate both gallery and query images using the same landmark CSV.
- Do not upload field photographs, result folders, cache files, or credentials to a public repository unless they are intended to be public.
