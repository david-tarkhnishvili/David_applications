from __future__ import annotations

AGE_CLASSES = 20


def _build_species(name: str, maturity_age: int, fecundity_scale: float, survival_shift: float) -> dict:
    initial_population = [0] * AGE_CLASSES
    fecundity_mean = [0.0] * AGE_CLASSES
    survival_mean = [0.0] * (AGE_CLASSES - 1)
    migration_weights = [0.0] * AGE_CLASSES
    baseline_emigration = [0.0] * AGE_CLASSES
    density_emigration = [0.0] * AGE_CLASSES

    return {
        "name": name,
        "maturity_age": maturity_age,
        "initial_population": initial_population,
        "initial_population_by_patch": [initial_population],
        "fecundity_mean": [round(x * fecundity_scale, 4) for x in fecundity_mean],
        "fecundity_sd": 0.20,
        "survival_mean": [max(0.0, min(0.99, round(x + survival_shift, 4))) for x in survival_mean],
        "survival_sd": 0.05,
        "migration_weights": migration_weights,
        "baseline_emigration": baseline_emigration,
        "density_emigration": density_emigration,
        "movement_matrix": [[1.0]],
        "catastrophe_affects_reproduction": True,
    }


def default_config_dict() -> dict:
    return {
        "general": {
            "years": 100,
            "replicates": 250,
            "seed": 42,
            "mode": "single",
            "spatial_mode": "single_location",
            "patch_count": 1,
        },
        "environment": {
            "k_mean": 500.0,
            "k_sd": 50.0,
            "heavy_tail": False,
            "heavy_tail_df": 5.0,
            "catastrophe_enabled": False,
            "catastrophe_interval_years": 10.0,
            "patch_specific_catastrophes": True,
            "joint_k": True,
            "species_weights": [1.0, 1.0],
        },
        "patches": [
            {
                "name": "Patch 1",
                "k_mean": 500.0,
                "k_sd": 50.0,
                "quality": 1.0,
                "catastrophe_interval_years": 10.0,
            }
        ],
        "species": [
            _build_species("Species 1", maturity_age=2, fecundity_scale=1.0, survival_shift=0.0),
            _build_species("Species 2", maturity_age=3, fecundity_scale=0.9, survival_shift=-0.03),
        ],
    }
