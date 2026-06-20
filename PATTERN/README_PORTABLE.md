# Darevskia Portable Bundle

This folder is a self-contained launcher bundle for the current
`Darevskia` identification workflow.

It is meant to live inside a project folder like:

```text
Darevskia_ID/
  gallery/
  query/
  config/
  outputs/
  portable_app/
```

The browser app inside `portable_app/` assumes that its parent folder is the
project folder.

## What to copy to another computer

Copy the entire project folder, for example:

```text
E:\Darevskia_ID
```

This includes:

- `gallery/`
- `query/`
- `config/`
- `outputs/`
- `cache/`
- `portable_app/`

## What is inside `portable_app`

- `darevskia_web_app.py`
- `launch_web_app.bat`
- `requirements.txt`
- `tools/`

The `tools/` folder contains the scripts and manuals required by the browser app.

## How to use on another computer

1. Install Python.
2. Open a terminal in `portable_app/`.
3. Install packages:

```powershell
python -m pip install -r requirements.txt
```

4. Launch:

```powershell
launch_web_app.bat
```

Or:

```powershell
python darevskia_web_app.py
```

5. Open the shown local address in a browser if it does not open automatically.

## Important note

Copying only `darevskia_web_app.py` is not enough.

The web app also needs:

- the `tools/` folder
- the project folder structure
- Python packages listed in `requirements.txt`
