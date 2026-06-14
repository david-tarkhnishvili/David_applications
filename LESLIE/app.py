from __future__ import annotations

import base64
from pathlib import Path

import pandas as pd
import streamlit as st

from defaults import AGE_CLASSES, default_config_dict
from io_utils import config_to_json_bytes, dataframe_to_csv_bytes
from model import SimulationConfig, config_from_dict, simulate_population
from plots import (
    make_extinction_comparison_figure,
    make_extinction_histogram,
    make_occupancy_comparison_figure,
    make_occupancy_figure,
    make_persistence_comparison_figure,
    make_persistence_figure,
    make_population_comparison_figure,
    make_population_figure,
)
from summaries import summarize_simulation
from validators import validate_config


st.set_page_config(page_title="Leslie Population Dynamics", layout="wide")

APP_AUTHOR = "David Tarkhnishvili"
APP_CITATION = (
    "Tarkhnishvili, D. 2026. LESLIE: Leslie Population Dynamics App. "
    "Python/Streamlit application for stochastic age-structured population simulation."
)
ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
SILHOUETTE_ASSETS = [
    ("Lizard", "silhouette_lizard.png"),
    ("Spider", "silhouette_spider.png"),
    ("Rodent", "silhouette_rodent.png"),
    ("Fish", "silhouette_fish.png"),
]
GRAPH_ASSET = "population_graph.gif"


def _asset_data_uri(filename: str) -> str:
    path = ASSET_DIR / filename
    mime = "image/gif" if path.suffix.lower() == ".gif" else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _render_header() -> None:
    silhouette_tiles = "".join(
        f'<div class="silhouette-tile" aria-label="{label} silhouette"><img src="{_asset_data_uri(filename)}" alt="{label} silhouette" /></div>'
        for label, filename in SILHOUETTE_ASSETS
    )
    graph_uri = _asset_data_uri(GRAPH_ASSET)
    st.markdown(
        f"""
        <style>
            [data-testid="stHeader"], [data-testid="stToolbar"] {{ display: none !important; height: 0 !important; }}
            [data-testid="stAppViewContainer"] .main .block-container, .block-container {{ padding-top: 0 !important; padding-left: 0 !important; padding-right: 0 !important; max-width: 100% !important; }}
            .block-container > div:not(:first-child) {{ padding-left: 1rem; padding-right: 1rem; }}
            .leslie-hero {{ width: 100vw; min-height: 170px; margin: 0 calc(50% - 50vw) 1rem calc(50% - 50vw); padding: 1rem max(1rem, calc((100vw - 1180px) / 2)); box-sizing: border-box; background: linear-gradient(112deg, #0e3735 0%, #17605b 48%, #d7a441 100%); color: #f7fbf7; display: grid; grid-template-columns: minmax(320px, 0.95fr) minmax(520px, 1.05fr); gap: 1rem; align-items: center; box-shadow: 0 8px 24px rgba(17, 63, 60, 0.18); }}
            .leslie-title {{ font-size: clamp(1.65rem, 2.25vw, 2.35rem); font-weight: 780; line-height: 1.05; margin: 0 0 0.42rem 0; letter-spacing: 0; }}
            .leslie-subtitle {{ font-size: 0.9rem; line-height: 1.34; max-width: 48rem; margin: 0; color: rgba(247, 251, 247, 0.92); }}
            .leslie-visual {{ display: grid; grid-template-columns: 230px minmax(320px, 1fr); gap: 0.75rem; align-items: stretch; }}
            .silhouette-strip {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem; }}
            .silhouette-tile {{ height: 64px; border-radius: 8px; background: rgba(226, 238, 226, 0.42); border: 1px solid rgba(255, 255, 255, 0.38); display: flex; align-items: center; justify-content: center; overflow: hidden; }}
            .silhouette-tile img {{ max-width: 92%; max-height: 84%; object-fit: contain; filter: brightness(0); opacity: 0.96; animation: silhouetteTone 7.5s ease-in-out infinite alternate; }}
            .silhouette-tile:nth-child(2) img {{ animation-delay: 0.8s; }} .silhouette-tile:nth-child(3) img {{ animation-delay: 1.6s; }} .silhouette-tile:nth-child(4) img {{ animation-delay: 2.4s; }}
            .population-card {{ min-width: 0; border-radius: 8px; background: rgba(226, 238, 226, 0.22); border: 1px solid rgba(255, 255, 255, 0.34); padding: 0.55rem 0.7rem 0.42rem 0.7rem; }}
            .population-card img {{ width: 100%; height: 86px; display: block; object-fit: contain; }}
            .mini-label {{ font-size: 0.68rem; color: rgba(247, 251, 247, 0.84); margin-top: 0.2rem; }}
            .leslie-footer {{ margin-top: 2rem; padding: 0.9rem 1rem; border-top: 1px solid #d8e2df; color: #31514d; font-size: 0.92rem; }}
            .citation-box {{ margin-top: 0.55rem; padding: 0.75rem 0.85rem; border-radius: 8px; background: #f2f7f5; border: 1px solid #d8e2df; color: #213b38; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.84rem; line-height: 1.45; }}
            @keyframes silhouetteTone {{ 0%, 12% {{ filter: brightness(0); opacity: 0.96; }} 88%, 100% {{ filter: brightness(0) invert(1); opacity: 1; }} }}
            @media (max-width: 760px) {{ .leslie-hero {{ grid-template-columns: minmax(0, 0.82fr) minmax(0, 1.18fr); min-height: 138px; padding: 0.45rem 0.5rem 0.48rem 0.5rem; gap: 0.5rem; margin-bottom: 0.58rem; align-items: center; }} .leslie-title {{ font-size: 1.05rem; line-height: 1.08; margin-bottom: 0; word-break: normal; overflow-wrap: normal; }} .leslie-subtitle {{ display: none; }} .leslie-visual {{ grid-template-columns: 1fr; gap: 0.34rem; }} .silhouette-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.28rem; }} .silhouette-tile {{ height: 28px; border-radius: 6px; }} .population-card {{ padding: 0.24rem 0.32rem 0.2rem 0.32rem; border-radius: 6px; }} .population-card img {{ height: 38px; }} .mini-label {{ font-size: 0.48rem; line-height: 1.05; }} }}
        </style>
        <section class="leslie-hero" aria-label="LESLIE application header"><div><div class="leslie-title">Leslie Population Dynamics</div><p class="leslie-subtitle">Stochastic age-structured simulation with replicate summaries, density-dependent emigration, catastrophes, and metapopulation comparisons.</p></div><div class="leslie-visual"><div class="silhouette-strip" aria-label="Changing animal silhouettes">{silhouette_tiles}</div><div class="population-card" aria-label="Animated population dynamics graph"><img src="{graph_uri}" alt="Animated population dynamics line graph" /><div class="mini-label">population trajectories across stochastic years</div></div></div></section>
        """,
        unsafe_allow_html=True,
    )

def _render_footer() -> None:
    st.markdown(
        f"""
        <div class="leslie-footer">
            <strong>© {APP_AUTHOR}</strong>. Please cite this program if it is used in research, teaching, reports, or derivative software.
            <div class="citation-box">{APP_CITATION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _expanded_patch_defaults(defaults: dict, patch_count: int, k_mean: float, k_sd: float) -> list[dict]:
    patches = [dict(item) for item in defaults.get("patches", [])]
    for patch in patches:
        patch.setdefault("catastrophe_interval_years", float(defaults["environment"].get("catastrophe_interval_years", 10.0)))
    while len(patches) < patch_count:
        patches.append(
            {
                "name": f"Patch {len(patches) + 1}",
                "k_mean": float(k_mean),
                "k_sd": float(k_sd),
                "quality": 1.0,
                "catastrophe_interval_years": float(defaults["environment"].get("catastrophe_interval_years", 10.0)),
            }
        )
    return patches[:patch_count]


def _expanded_species_defaults(species_defaults: dict, patch_count: int) -> dict:
    expanded = dict(species_defaults)
    initial_by_patch = [list(row) for row in species_defaults.get("initial_population_by_patch", [species_defaults["initial_population"]])]
    while len(initial_by_patch) < patch_count:
        initial_by_patch.append(list(species_defaults["initial_population"]))
    expanded["initial_population_by_patch"] = initial_by_patch[:patch_count]

    movement_matrix = [list(row) for row in species_defaults.get("movement_matrix", [[1.0]])]
    while len(movement_matrix) < patch_count:
        row = [0.0] * patch_count
        for idx in range(patch_count):
            if idx != len(movement_matrix):
                row[idx] = 1.0 / max(patch_count - 1, 1)
        movement_matrix.append(row)
    adjusted_matrix = []
    for row_idx in range(patch_count):
        row = movement_matrix[row_idx][:patch_count]
        while len(row) < patch_count:
            row.append(0.0)
        adjusted_matrix.append(row)
    expanded["movement_matrix"] = adjusted_matrix
    return expanded


def _species_editor(prefix: str, defaults: dict, patch_names: list[str], spatial_mode: str) -> dict:
    st.subheader(defaults["name"])
    col1, col2, col3 = st.columns(3)
    with col1:
        name = st.text_input("Species name", value=defaults["name"], key=f"{prefix}_name")
    with col2:
        maturity_age = st.number_input(
            "First reproductive age class",
            min_value=2,
            max_value=AGE_CLASSES,
            value=int(defaults["maturity_age"]),
            step=1,
            key=f"{prefix}_maturity_age",
        )
    with col3:
        fecundity_sd = st.number_input(
            "Fecundity SD",
            min_value=0.0,
            value=float(defaults["fecundity_sd"]),
            step=0.01,
            format="%.3f",
            key=f"{prefix}_fecundity_sd",
        )
    survival_sd = st.number_input(
        "Survival SD",
        min_value=0.0,
        value=float(defaults["survival_sd"]),
        step=0.01,
        format="%.3f",
        key=f"{prefix}_survival_sd",
    )
    catastrophe_affects_reproduction = st.checkbox(
        "Reproduction fails in catastrophe years",
        value=bool(defaults.get("catastrophe_affects_reproduction", False)),
        key=f"{prefix}_catastrophe_affects_reproduction",
        help="If checked, this species produces no offspring during catastrophe years affecting the local patch or the whole system.",
    )

    demographic_table = pd.DataFrame(
        {
            "age_class": list(range(1, AGE_CLASSES + 1)),
            "initial_population": defaults["initial_population"],
            "fecundity_mean": defaults["fecundity_mean"],
            "survival_to_next": defaults["survival_mean"] + [None],
            "migration_weight": defaults["migration_weights"],
        }
    )

    st.markdown("**Local demographic schedule**")
    edited = st.data_editor(
        demographic_table,
        key=f"{prefix}_table",
        hide_index=True,
        use_container_width=True,
        disabled=["age_class"],
        num_rows="fixed",
        column_config={
            "age_class": st.column_config.NumberColumn("Age class", format="%d"),
            "initial_population": st.column_config.NumberColumn("Initial population", min_value=0, step=1),
            "fecundity_mean": st.column_config.NumberColumn("Mean fecundity", min_value=0.0),
            "survival_to_next": st.column_config.NumberColumn("Mean survival to next age", min_value=0.0, max_value=1.0),
            "migration_weight": st.column_config.NumberColumn("Migration weight", min_value=0.0),
        },
    )

    survival_values = edited["survival_to_next"].tolist()[:-1]
    survival_values = [0.0 if pd.isna(value) else float(value) for value in survival_values]

    st.markdown("**Age-specific emigration schedule**")
    emigration_table = pd.DataFrame(
        {
            "age_class": list(range(1, AGE_CLASSES + 1)),
            "baseline_emigration": defaults.get("baseline_emigration", [0.0] * AGE_CLASSES),
            "density_emigration": defaults.get("density_emigration", [0.0] * AGE_CLASSES),
        }
    )
    edited_emigration = st.data_editor(
        emigration_table,
        key=f"{prefix}_emigration_table",
        hide_index=True,
        use_container_width=True,
        disabled=["age_class"],
        num_rows="fixed",
        column_config={
            "age_class": st.column_config.NumberColumn("Age class", format="%d"),
            "baseline_emigration": st.column_config.NumberColumn("Baseline emigration", min_value=0.0, max_value=1.0),
            "density_emigration": st.column_config.NumberColumn("Density emigration", min_value=0.0, max_value=1.0),
        },
    )

    edited_initial_population = [int(round(float(value))) for value in edited["initial_population"].tolist()]
    initial_population_by_patch = [edited_initial_population]
    movement_matrix = defaults.get("movement_matrix", [[1.0]])
    if spatial_mode == "metapopulation":
        st.markdown("**Initial population by patch**")
        initial_patch_table = pd.DataFrame({"age_class": list(range(1, AGE_CLASSES + 1))})
        for patch_idx, patch_name in enumerate(patch_names):
            initial_patch_table[patch_name] = defaults["initial_population_by_patch"][patch_idx]
        edited_initial = st.data_editor(
            initial_patch_table,
            key=f"{prefix}_initial_by_patch",
            hide_index=True,
            use_container_width=True,
            disabled=["age_class"],
            num_rows="fixed",
        )
        initial_population_by_patch = [
            [int(round(float(value))) for value in edited_initial[patch_name].tolist()]
            for patch_name in patch_names
        ]

        st.markdown("**Movement matrix**")
        movement_table = pd.DataFrame(defaults["movement_matrix"], index=patch_names, columns=patch_names)
        edited_movement = st.data_editor(
            movement_table,
            key=f"{prefix}_movement_matrix",
            use_container_width=True,
            num_rows="fixed",
        )
        movement_matrix = [
            [float(edited_movement.loc[source, dest]) for dest in patch_names]
            for source in patch_names
        ]

    return {
        "name": name,
        "maturity_age": int(maturity_age),
        "initial_population": edited_initial_population,
        "initial_population_by_patch": initial_population_by_patch,
        "fecundity_mean": [float(value) for value in edited["fecundity_mean"].tolist()],
        "fecundity_sd": float(fecundity_sd),
        "survival_mean": survival_values,
        "survival_sd": float(survival_sd),
        "migration_weights": [float(value) for value in edited["migration_weight"].tolist()],
        "baseline_emigration": [float(value) for value in edited_emigration["baseline_emigration"].tolist()],
        "density_emigration": [float(value) for value in edited_emigration["density_emigration"].tolist()],
        "movement_matrix": movement_matrix,
        "catastrophe_affects_reproduction": bool(catastrophe_affects_reproduction),
    }


def _build_config_from_widgets() -> SimulationConfig:
    defaults = default_config_dict()

    st.sidebar.header("General Settings")
    spatial_mode = st.sidebar.selectbox(
        "Spatial mode",
        options=["single_location", "metapopulation"],
        index=["single_location", "metapopulation"].index(defaults["general"].get("spatial_mode", "single_location")),
        help="Use metapopulation mode to simulate several connected habitat patches.",
    )
    patch_count = 1
    if spatial_mode == "metapopulation":
        default_patch_count = max(2, int(defaults["general"].get("patch_count", 2)))
        patch_count = int(
            st.sidebar.number_input(
                "Number of patches",
                min_value=2,
                max_value=12,
                value=default_patch_count,
                step=1,
            )
        )
    mode = st.sidebar.selectbox(
        "Simulation mode",
        options=["single", "two_isolated", "two_coexisting"],
        index=["single", "two_isolated", "two_coexisting"].index(defaults["general"]["mode"]),
        help="Use two_isolated to run both species separately under the same parameter template.",
    )
    years = st.sidebar.number_input("Years", min_value=2, max_value=1000, value=defaults["general"]["years"], step=1)
    replicates = st.sidebar.number_input(
        "Replicates",
        min_value=1,
        max_value=1000,
        value=defaults["general"]["replicates"],
        step=1,
    )
    seed = st.sidebar.number_input("Random seed", value=defaults["general"]["seed"], step=1)

    st.sidebar.header("Carrying Capacity")
    k_mean = st.sidebar.number_input("Mean K", min_value=0.01, value=defaults["environment"]["k_mean"], step=10.0)
    k_sd = st.sidebar.number_input("K SD", min_value=0.0, value=defaults["environment"]["k_sd"], step=5.0)
    heavy_tail = st.sidebar.checkbox("Use heavy-tailed annual shocks", value=defaults["environment"]["heavy_tail"])
    heavy_tail_df = st.sidebar.number_input(
        "Heavy-tail degrees of freedom",
        min_value=2.1,
        value=defaults["environment"]["heavy_tail_df"],
        step=0.5,
        disabled=not heavy_tail,
    )
    weight_col1, weight_col2 = st.sidebar.columns(2)
    with weight_col1:
        weight_1 = st.number_input("Species 1 load weight", min_value=0.01, value=1.0, step=0.1)
    with weight_col2:
        weight_2 = st.number_input("Species 2 load weight", min_value=0.01, value=1.0, step=0.1)

    st.sidebar.header("Catastrophes")
    catastrophe_enabled = st.sidebar.checkbox(
        "Enable catastrophic reproductive failure years",
        value=bool(defaults["environment"].get("catastrophe_enabled", False)),
        help="When enabled, catastrophe years are drawn randomly around the chosen average interval, either system-wide or patch by patch.",
    )
    catastrophe_interval_years = st.sidebar.number_input(
        "Average catastrophe interval (years)",
        min_value=1.0,
        value=float(defaults["environment"].get("catastrophe_interval_years", 10.0)),
        step=1.0,
        disabled=not catastrophe_enabled,
        help="The simulator uses yearly probability 1 / interval, so realized catastrophe years vary randomly around this average spacing.",
    )
    patch_specific_catastrophes = False
    if spatial_mode == "metapopulation":
        patch_specific_catastrophes = st.sidebar.checkbox(
            "Use patch-specific catastrophe timing",
            value=bool(defaults["environment"].get("patch_specific_catastrophes", True)),
            disabled=not catastrophe_enabled,
            help="If checked, each patch draws catastrophe years independently around its own average interval.",
        )

    species_defaults = defaults["species"]
    species_count = 1 if mode == "single" else 2
    patch_defaults = _expanded_patch_defaults(defaults, patch_count, float(k_mean), float(k_sd))
    patch_names = [item["name"] for item in patch_defaults]

    patches = patch_defaults
    if spatial_mode == "metapopulation":
        st.subheader("Patch settings")
        patch_table = pd.DataFrame(patch_defaults)
        edited_patches = st.data_editor(
            patch_table,
            key="patch_table",
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "name": st.column_config.TextColumn("Patch name"),
                "k_mean": st.column_config.NumberColumn("Mean K", min_value=0.01),
                "k_sd": st.column_config.NumberColumn("K SD", min_value=0.0),
                "quality": st.column_config.NumberColumn("Quality", min_value=0.01),
                "catastrophe_interval_years": st.column_config.NumberColumn(
                    "Catastrophe interval",
                    min_value=1.0,
                    help="Average years between catastrophes for this patch when patch-specific catastrophe timing is enabled.",
                ),
            },
        )
        patches = edited_patches.to_dict("records")
        patch_names = [str(item["name"]) for item in patches]

    tabs = st.tabs([f"Species {idx + 1}" for idx in range(species_count)])
    species = []
    for idx, tab in enumerate(tabs):
        with tab:
            species.append(
                _species_editor(
                    f"species_{idx + 1}",
                    _expanded_species_defaults(species_defaults[idx], len(patch_names)),
                    patch_names,
                    spatial_mode,
                )
            )

    config_dict = {
        "general": {
            "years": int(years),
            "replicates": int(replicates),
            "seed": int(seed),
            "mode": mode,
            "spatial_mode": spatial_mode,
            "patch_count": len(patch_names),
        },
        "environment": {
            "k_mean": float(k_mean),
            "k_sd": float(k_sd),
            "heavy_tail": bool(heavy_tail),
            "heavy_tail_df": float(heavy_tail_df),
            "catastrophe_enabled": bool(catastrophe_enabled),
            "catastrophe_interval_years": float(catastrophe_interval_years),
            "patch_specific_catastrophes": bool(patch_specific_catastrophes),
            "joint_k": mode == "two_coexisting",
            "species_weights": [float(weight_1), float(weight_2)],
        },
        "patches": patches if spatial_mode == "metapopulation" else [{"name": "Patch 1", "k_mean": float(k_mean), "k_sd": float(k_sd), "quality": 1.0, "catastrophe_interval_years": float(catastrophe_interval_years)}],
        "species": species,
    }
    return config_from_dict(config_dict)


def _show_config_messages(config: SimulationConfig) -> tuple[list[str], list[str]]:
    errors, warnings = validate_config(config)
    if errors:
        for message in errors:
            st.error(message)
    if warnings:
        with st.expander("Validation warnings", expanded=False):
            for message in warnings:
                st.warning(message)
    return errors, warnings


def _render_results() -> None:
    result = st.session_state.get("simulation_result")
    summary = st.session_state.get("simulation_summary")
    if result is None or summary is None:
        return

    st.header("Results")
    species_labels = summary.get("species_labels", [])
    if len(species_labels) > 1:
        st.subheader("Species comparison")
        comparison_frames = {label: summary["trajectories"][label] for label in species_labels}
        compare_col1, compare_col2 = st.columns(2)
        with compare_col1:
            st.plotly_chart(
                make_population_comparison_figure(comparison_frames, metric="total", include_sd=True),
                use_container_width=True,
            )
        with compare_col2:
            st.plotly_chart(
                make_population_comparison_figure(comparison_frames, metric="reproductive", include_sd=True),
                use_container_width=True,
            )
        compare_col3, compare_col4 = st.columns(2)
        with compare_col3:
            st.plotly_chart(make_persistence_comparison_figure(comparison_frames), use_container_width=True)
        with compare_col4:
            extinction_years_by_label = {
                label: summary["extinction_replicates"][f"{label.replace(':', '').replace(' ', '_').lower()}_extinction_year"]
                for label in species_labels
            }
            st.plotly_chart(
                make_extinction_comparison_figure(extinction_years_by_label, result.config.general.years),
                use_container_width=True,
            )
        if result.config.general.spatial_mode == "metapopulation":
            st.subheader("Patch occupancy and local populations")
            st.plotly_chart(
                make_occupancy_comparison_figure({label: summary["occupancy_trajectories"][label] for label in species_labels}),
                use_container_width=True,
            )
            patch_names = result.patch_names
            selected_patch = st.selectbox("Patch to compare", patch_names, index=0, key="patch_compare")
            patch_frames = {
                label: summary["patch_trajectories"][f"{label} | {selected_patch}"]
                for label in species_labels
            }
            patch_col1, patch_col2 = st.columns(2)
            with patch_col1:
                st.plotly_chart(
                    make_population_comparison_figure(
                        patch_frames,
                        metric="total",
                        include_sd=True,
                        title=f"{selected_patch}: total population by species",
                    ),
                    use_container_width=True,
                )
            with patch_col2:
                st.plotly_chart(
                    make_population_comparison_figure(
                        patch_frames,
                        metric="reproductive",
                        include_sd=True,
                        title=f"{selected_patch}: reproductive population by species",
                    ),
                    use_container_width=True,
                )

    trajectory_labels = list(summary["trajectories"].keys())
    entity = st.selectbox("Entity to display", trajectory_labels, index=0)
    frame = summary["trajectories"][entity]

    if len(species_labels) == 1 or entity == "Community":
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(make_population_figure(frame, entity, metric="total"), use_container_width=True)
        with col2:
            st.plotly_chart(make_population_figure(frame, entity, metric="reproductive"), use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(make_persistence_figure(frame, entity), use_container_width=True)
        with col4:
            if entity == "Community":
                years = summary["extinction_replicates"]["community_extinction_year"]
            else:
                safe_label = entity.replace(":", "").replace(" ", "_").lower()
                years = summary["extinction_replicates"][f"{safe_label}_extinction_year"]
            st.plotly_chart(make_extinction_histogram(years, result.config.general.years, entity), use_container_width=True)

    st.subheader("Extinction summary")
    st.dataframe(summary["extinction_summary"], use_container_width=True)

    st.subheader("Lambda and growth summary")
    st.dataframe(summary["growth_summary"], use_container_width=True)

    st.subheader("Yearly trajectory summary")
    st.dataframe(frame, use_container_width=True)

    if result.config.general.spatial_mode == "metapopulation" and len(species_labels) == 1:
        st.subheader("Patch occupancy and local populations")
        occupancy_entity = st.selectbox("Species occupancy entity", species_labels, index=0, key="occupancy_entity")
        occupancy_col1, occupancy_col2 = st.columns(2)
        with occupancy_col1:
            st.plotly_chart(make_occupancy_figure(summary["occupancy_trajectories"][occupancy_entity], occupancy_entity), use_container_width=True)
        with occupancy_col2:
            patch_options = [key for key in summary["patch_trajectories"].keys() if key.startswith(occupancy_entity)]
            patch_entity = st.selectbox("Patch trajectory", patch_options, index=0, key="patch_entity")
            st.plotly_chart(make_population_figure(summary["patch_trajectories"][patch_entity], patch_entity, metric="total"), use_container_width=True)
        st.subheader("Patch summary")
        st.dataframe(summary["patch_summary"], use_container_width=True)
    elif result.config.general.spatial_mode == "metapopulation":
        st.subheader("Patch summary")
        st.dataframe(summary["patch_summary"], use_container_width=True)

    download_col1, download_col2, download_col3, download_col4, download_col5 = st.columns(5)
    with download_col1:
        st.download_button(
            "Download current trajectory CSV",
            data=dataframe_to_csv_bytes(frame),
            file_name=f"{entity.lower().replace(' ', '_')}_trajectory.csv",
            mime="text/csv",
        )
    with download_col2:
        st.download_button(
            "Download lambda summary CSV",
            data=dataframe_to_csv_bytes(summary["growth_summary"]),
            file_name="growth_summary.csv",
            mime="text/csv",
        )
    with download_col3:
        st.download_button(
            "Download replicate extinction CSV",
            data=dataframe_to_csv_bytes(summary["extinction_replicates"]),
            file_name="replicate_extinction_years.csv",
            mime="text/csv",
        )
    with download_col4:
        st.download_button(
            "Download extinction summary CSV",
            data=dataframe_to_csv_bytes(summary["extinction_summary"]),
            file_name="extinction_summary.csv",
            mime="text/csv",
        )
    with download_col5:
        patch_summary = summary.get("patch_summary")
        st.download_button(
            "Download patch summary CSV",
            data=dataframe_to_csv_bytes(patch_summary if patch_summary is not None else pd.DataFrame()),
            file_name="patch_summary.csv",
            mime="text/csv",
        )


def main() -> None:
    _render_header()

    config = _build_config_from_widgets()
    st.download_button(
        "Download current config JSON",
        data=config_to_json_bytes(config),
        file_name="leslie_config.json",
        mime="application/json",
    )

    errors, _warnings = _show_config_messages(config)

    run_clicked = st.button("Run simulation", type="primary", disabled=bool(errors))
    if run_clicked and not errors:
        progress_bar = st.progress(0)
        status = st.empty()

        def _progress(done: int, total_reps: int) -> None:
            progress_bar.progress(done / total_reps, text=f"Running replicate {done} of {total_reps}")
            status.caption(f"Completed {done} of {total_reps} replicates.")

        with st.spinner("Simulating population dynamics..."):
            result = simulate_population(config, progress_callback=_progress)
            summary = summarize_simulation(result)
        progress_bar.empty()
        status.empty()
        st.session_state["simulation_result"] = result
        st.session_state["simulation_summary"] = summary

    _render_results()
    _render_footer()


if __name__ == "__main__":
    main()























