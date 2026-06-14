# GitHub upload notes for LESLIE

Upload these helper files to the GitHub folder:

- index.html
- .gitignore

The file index.html is a GitHub Pages launcher. Before it can redirect visitors, replace this placeholder in index.html:

REPLACE_WITH_STREAMLIT_APP_URL

with the final Streamlit Cloud URL for the running LESLIE app.

Remove these from GitHub if they were uploaded:

- .venv/
- __pycache__/
- any *.pyc files
- .streamlit/secrets.toml, if present
- assets/header_banner.gif, because the current app no longer uses this old oversized banner
- Leslie_old/
- Leslie.xlsx, unless you intentionally want to distribute the spreadsheet as a separate source file

Keep these important app assets:

- assets/silhouette_lizard.png
- assets/silhouette_spider.png
- assets/silhouette_rodent.png
- assets/silhouette_fish.png
- assets/population_graph.gif
