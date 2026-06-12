# Taxonomy Trainer

This is a self-contained student training program for practicing taxonomic ranks from images.

## How to run

Open `index.html` in a browser.

The app does not need a server or internet connection for the quiz and tree exercises. The Google image search and Wikipedia buttons require internet access.

## Student workflow

1. Choose or receive a specimen image.
2. Answer randomized questions for phylum, class, order, family, and genus.
3. Only after the full taxonomic stair is correct, attempt species-level identification.
4. Use Google image search cautiously, because image matches can be wrong.
5. Record the most precise reliable identification, including forms such as `Melithaea sp.` or `Cerambicidae sp.` when species-level identification is not safe.
6. Build a simple evolutionary tree by selecting the closest two organisms first, then adding progressively more distant organisms.

## Adding new images

Put image files into `GALLERY`.

Then edit `data/specimens.js` and add a record with:

- `id`
- `commonName`
- `image`
- `sourceName`
- `sourceUrl`
- `license`
- `taxonomy`
- `candidates`
- `regions`

For classroom use, keep image filenames simple and avoid spaces, for example `helix_pomatia.jpg`.

## Starter images

The starter image set is drawn from open/public Wikimedia Commons pages. Source links and license notes are shown in the Gallery tab.
