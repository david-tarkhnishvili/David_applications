# ARRDP

ARRDP means **Amphibian and Reptile Recognition by Dorsal Pattern**. It is a free, local web application that compares dorsal-pattern images of known and query specimens.

## Start

1. Install Python 3.10 or later.
2. In this folder, run `python -m pip install -r requirements.txt` once.
3. Double-click `START_ARRDP.bat`.
4. Open `http://127.0.0.1:8094/` if the browser does not open automatically.

ARRDP runs only on the local computer. It does not need an account, password, administrator permission, or internet access after packages are installed.

## Project folders

Place images as follows:

```text
ARRDP/
  gallery/<known-individual>/
  query/<unknown-or-test-individual>/
  config/
  outputs/
```

Read `ARRDP_Algorithm_and_User_Manual_Final.pdf` before use. The present implementation was developed and tested with *Darevskia* lizards; applying it to other reptile or amphibian groups requires validation with labelled photographs from that group.

## GitHub release notes

Do not upload photographs, landmark files, result tables, `web_runs/`, caches, or credentials unless you intend to make them public. GitHub Release assets display total download counts, but GitHub cannot require free registration for a public download or identify anonymous downloaders.
