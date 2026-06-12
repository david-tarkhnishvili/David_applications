Ecosystem Guild Builder
=======================

How to open
-----------
1. Unzip the whole folder.
2. Double-click open_ecosystem_app.bat.
3. The app should open at http://127.0.0.1:8765/.

What is included
----------------
- index.html, styles.css, app.js: the learning web application.
- species.csv: the example species list.
- vendor/d3.v7.min.js: the graph library, included locally so the interaction web works without downloading D3.
- open_ecosystem_app.bat: Windows launcher.
- start_ecosystem_server.ps1: fallback local server for computers without Python.

Notes
-----
- Internet notes still require internet access because they query Wikipedia.
- Manual corrections are stored in the browser on each computer. They are not written back into the CSV.
- If Windows shows a security warning, choose to run the batch file from the extracted folder.
