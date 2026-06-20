# Darevskia Web App

## Launch

Run:

```powershell
C:\Users\HP\lizard_ai_env\Scripts\python.exe "g:\My Drive\Lizards\RUDIS_GROUP\darevskia_web_src\darevskia_web_app.py"
```

By default, the app starts at:

- `http://127.0.0.1:8094/`

and opens a browser tab automatically.

## What this first version does

- launch landmark annotation jobs
- launch matcher jobs
- let you edit many parameters from the browser
- show recent jobs
- show approximate progress
- show summaries, prediction tables, QC thumbnails, and logs

## Supported matcher modes

- `5-point curved belt`
- `3-point windows`
- `4-point quadrilateral`

The current recommended mode is:

- `5-point curved belt`
- `belt breadth fraction = 0.14`
- `consensus top-k = 2`

## Notes

- The browser app does not replace the annotation window; it launches the existing Tkinter annotator.
- Point count in the annotation form is fully adjustable, but the built-in matchers currently use the existing 3-, 4-, and 5-point workflows.
