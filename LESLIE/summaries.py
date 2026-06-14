from __future__ import annotations

import numpy as np
import pandas as pd

from model import SimulationResult


def _species_display_labels(names: list[str]) -> list[str]:
    return [f"Species {idx + 1}: {name}" for idx, name in enumerate(names)]


def _mean_leslie_matrix(species) -> np.ndarray:
    fecundity = np.asarray(species.fecundity_mean, dtype=float).copy()
    maturity_index = max(species.maturity_age - 1, 0)
    fecundity[:maturity_index] = 0.0
    matrix = np.zeros((len(fecundity), len(fecundity)), dtype=float)
    matrix[0, :] = fecundity
    survival = np.asarray(species.survival_mean, dtype=float)
    for idx, value in enumerate(survival):
        matrix[idx + 1, idx] = value
    return matrix


def _dominant_lambda(species) -> float:
    matrix = _mean_leslie_matrix(species)
    eigenvalues = np.linalg.eigvals(matrix)
    return float(np.max(eigenvalues.real))


def _lambda_metrics(series: np.ndarray) -> tuple[float, float]:
    previous = series[:, :-1].astype(float)
    current = series[:, 1:].astype(float)
    valid = previous > 0
    if not np.any(valid):
        return np.nan, np.nan

    ratios = np.full(previous.shape, np.nan, dtype=float)
    ratios[valid] = current[valid] / previous[valid]
    valid_ratios = ratios[np.isfinite(ratios)]
    arithmetic_mean = float(valid_ratios.mean()) if valid_ratios.size else np.nan

    positive_ratios = valid_ratios[valid_ratios > 0]
    geometric_mean = float(np.exp(np.log(positive_ratios).mean())) if positive_ratios.size else np.nan
    return arithmetic_mean, geometric_mean


def _trajectory_frame(
    years: np.ndarray,
    total: np.ndarray,
    reproductive: np.ndarray,
    catastrophe_years: np.ndarray | None = None,
    reproduction_failure_years: np.ndarray | None = None,
) -> pd.DataFrame:
    alive = (total > 0).mean(axis=0)
    extinct = 1.0 - alive
    frame = pd.DataFrame(
        {
            "year": years,
            "mean_total": total.mean(axis=0),
            "sd_total": total.std(axis=0, ddof=0),
            "mean_reproductive": reproductive.mean(axis=0),
            "sd_reproductive": reproductive.std(axis=0, ddof=0),
            "persistence_probability": alive,
            "extinction_probability": extinct,
        }
    )
    if catastrophe_years is not None:
        frame["catastrophe_probability"] = catastrophe_years.mean(axis=0)
    if reproduction_failure_years is not None:
        frame["reproduction_failure_probability"] = reproduction_failure_years.mean(axis=0)
    return frame


def _occupancy_frame(years: np.ndarray, local_total: np.ndarray, patch_count: int) -> pd.DataFrame:
    occupied_counts = (local_total > 0).sum(axis=2)
    return pd.DataFrame(
        {
            "year": years,
            "mean_occupied_patches": occupied_counts.mean(axis=0),
            "sd_occupied_patches": occupied_counts.std(axis=0, ddof=0),
            "occupancy_proportion": occupied_counts.mean(axis=0) / max(patch_count, 1),
        }
    )


def _extinction_metrics(
    extinction_years: np.ndarray,
    horizon: int,
    label: str,
    catastrophe_years: np.ndarray,
    reproduction_failure_years: np.ndarray,
) -> dict:
    extinct_mask = extinction_years <= horizon
    extinct_years_observed = extinction_years[extinct_mask]
    mean_extinction = float(extinct_years_observed.mean()) if extinct_years_observed.size else np.nan
    sd_extinction = float(extinct_years_observed.std(ddof=0)) if extinct_years_observed.size else np.nan
    median_extinction = float(np.median(extinct_years_observed)) if extinct_years_observed.size else np.nan
    restricted_mean = float(np.minimum(extinction_years, horizon).mean())

    return {
        "entity": label,
        "extinction_probability": float(extinct_mask.mean()),
        "survival_probability": float(1.0 - extinct_mask.mean()),
        "mean_extinction_year": mean_extinction,
        "sd_extinction_year": sd_extinction,
        "median_extinction_year": median_extinction,
        "restricted_mean_persistence": restricted_mean,
        "mean_catastrophe_years": float(catastrophe_years[:, 1:].sum(axis=1).mean()),
        "mean_reproduction_failure_years": float(reproduction_failure_years[:, 1:].sum(axis=1).mean()),
    }


def summarize_simulation(result: SimulationResult) -> dict:
    trajectories: dict[str, pd.DataFrame] = {}
    horizon = result.config.general.years
    species_labels = _species_display_labels(result.species_names)
    patch_trajectories: dict[str, pd.DataFrame] = {}
    occupancy_trajectories: dict[str, pd.DataFrame] = {}

    for idx, label in enumerate(species_labels):
        trajectories[label] = _trajectory_frame(
            result.years,
            result.total[:, :, idx],
            result.reproductive[:, :, idx],
            catastrophe_years=result.catastrophe_years,
            reproduction_failure_years=result.reproduction_failure_years[:, :, idx],
        )
        occupancy_trajectories[label] = _occupancy_frame(result.years, result.local_total[:, :, idx, :], len(result.patch_names))
        for patch_idx, patch_name in enumerate(result.patch_names):
            patch_label = f"{label} | {patch_name}"
            patch_trajectories[patch_label] = _trajectory_frame(
                result.years,
                result.local_total[:, :, idx, patch_idx],
                result.local_reproductive[:, :, idx, patch_idx],
                catastrophe_years=result.patch_catastrophe_years[:, :, patch_idx],
                reproduction_failure_years=result.patch_reproduction_failure_years[:, :, idx, patch_idx],
            )

    trajectories["Community"] = _trajectory_frame(
        result.years,
        result.community_total,
        result.community_reproductive,
        catastrophe_years=result.catastrophe_years,
        reproduction_failure_years=result.reproduction_failure_years.any(axis=2),
    )

    extinction_rows = [
        _extinction_metrics(
            result.species_extinction_year[:, idx],
            horizon,
            label,
            result.catastrophe_years,
            result.reproduction_failure_years[:, :, idx],
        )
        for idx, label in enumerate(species_labels)
    ]
    extinction_rows.append(
        _extinction_metrics(
            result.community_extinction_year,
            horizon,
            "Community",
            result.catastrophe_years,
            result.reproduction_failure_years.any(axis=2),
        )
    )
    extinction_summary = pd.DataFrame(extinction_rows)

    growth_rows: list[dict] = []
    for idx, label in enumerate(species_labels):
        total_arithmetic, total_geometric = _lambda_metrics(result.total[:, :, idx])
        reproductive_arithmetic, reproductive_geometric = _lambda_metrics(result.reproductive[:, :, idx])
        growth_rows.append(
            {
                "entity": label,
                "deterministic_leslie_lambda": _dominant_lambda(result.config.species[idx]),
                "realized_arithmetic_lambda_total": total_arithmetic,
                "realized_geometric_lambda_total": total_geometric,
                "realized_arithmetic_lambda_reproductive": reproductive_arithmetic,
                "realized_geometric_lambda_reproductive": reproductive_geometric,
            }
        )

    community_total_arithmetic, community_total_geometric = _lambda_metrics(result.community_total)
    community_reproductive_arithmetic, community_reproductive_geometric = _lambda_metrics(result.community_reproductive)
    growth_rows.append(
        {
            "entity": "Community",
            "deterministic_leslie_lambda": np.nan,
            "realized_arithmetic_lambda_total": community_total_arithmetic,
            "realized_geometric_lambda_total": community_total_geometric,
            "realized_arithmetic_lambda_reproductive": community_reproductive_arithmetic,
            "realized_geometric_lambda_reproductive": community_reproductive_geometric,
        }
    )
    growth_summary = pd.DataFrame(growth_rows)

    patch_rows: list[dict] = []
    for idx, label in enumerate(species_labels):
        for patch_idx, patch_name in enumerate(result.patch_names):
            patch_totals = result.local_total[:, :, idx, patch_idx]
            patch_reproductive = result.local_reproductive[:, :, idx, patch_idx]
            patch_rows.append(
                {
                    "entity": label,
                    "patch": patch_name,
                    "final_mean_total": float(patch_totals[:, -1].mean()),
                    "final_mean_reproductive": float(patch_reproductive[:, -1].mean()),
                    "final_occupancy_probability": float((patch_totals[:, -1] > 0).mean()),
                    "mean_occupancy_probability": float((patch_totals > 0).mean()),
                    "mean_catastrophe_probability": float(result.patch_catastrophe_years[:, 1:, patch_idx].mean()),
                    "mean_reproduction_failure_probability": float(
                        result.patch_reproduction_failure_years[:, 1:, idx, patch_idx].mean()
                    ),
                }
            )
    patch_summary = pd.DataFrame(patch_rows)

    extinction_replicates = pd.DataFrame(
        {
            "replicate": np.arange(1, result.config.general.replicates + 1, dtype=int),
            "community_extinction_year": result.community_extinction_year,
            "catastrophe_year_count": result.catastrophe_years[:, 1:].sum(axis=1),
        }
    )
    for idx, label in enumerate(species_labels):
        safe_label = label.replace(":", "").replace(" ", "_").lower()
        extinction_replicates[f"{safe_label}_extinction_year"] = result.species_extinction_year[:, idx]
        extinction_replicates[f"{safe_label}_reproduction_failure_year_count"] = result.reproduction_failure_years[:, 1:, idx].sum(axis=1)

    return {
        "species_labels": species_labels,
        "trajectories": trajectories,
        "patch_trajectories": patch_trajectories,
        "occupancy_trajectories": occupancy_trajectories,
        "extinction_summary": extinction_summary,
        "growth_summary": growth_summary,
        "patch_summary": patch_summary,
        "extinction_replicates": extinction_replicates,
    }
