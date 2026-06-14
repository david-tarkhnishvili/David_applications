from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from stochastic import draw_beta_mean_sd, draw_lognormal_mean_sd

AGE_CLASSES = 20
SURVIVAL_CLASSES = AGE_CLASSES - 1


@dataclass(slots=True)
class PatchConfig:
    name: str
    k_mean: float
    k_sd: float
    quality: float
    catastrophe_interval_years: float


@dataclass(slots=True)
class SpeciesConfig:
    name: str
    maturity_age: int
    initial_population: list[int]
    initial_population_by_patch: list[list[int]]
    fecundity_mean: list[float]
    fecundity_sd: float
    survival_mean: list[float]
    survival_sd: float
    migration_weights: list[float]
    baseline_emigration: list[float]
    density_emigration: list[float]
    movement_matrix: list[list[float]]
    catastrophe_affects_reproduction: bool


@dataclass(slots=True)
class GeneralConfig:
    years: int
    replicates: int
    seed: int
    mode: str
    spatial_mode: str
    patch_count: int


@dataclass(slots=True)
class EnvironmentConfig:
    k_mean: float
    k_sd: float
    heavy_tail: bool
    heavy_tail_df: float
    catastrophe_enabled: bool
    catastrophe_interval_years: float
    patch_specific_catastrophes: bool
    joint_k: bool
    species_weights: list[float]


@dataclass(slots=True)
class SimulationConfig:
    general: GeneralConfig
    environment: EnvironmentConfig
    patches: list[PatchConfig]
    species: list[SpeciesConfig]


@dataclass(slots=True)
class SimulationResult:
    config: SimulationConfig
    years: np.ndarray
    species_names: list[str]
    patch_names: list[str]
    total: np.ndarray
    reproductive: np.ndarray
    local_total: np.ndarray
    local_reproductive: np.ndarray
    catastrophe_years: np.ndarray
    patch_catastrophe_years: np.ndarray
    reproduction_failure_years: np.ndarray
    patch_reproduction_failure_years: np.ndarray
    community_total: np.ndarray
    community_reproductive: np.ndarray
    species_extinction_year: np.ndarray
    community_extinction_year: np.ndarray


def _default_patch_configs(environment: dict, patch_count: int) -> list[dict]:
    return [
        {
            "name": f"Patch {idx + 1}",
            "k_mean": float(environment["k_mean"]),
            "k_sd": float(environment["k_sd"]),
            "quality": 1.0,
            "catastrophe_interval_years": float(environment.get("catastrophe_interval_years", 10.0)),
        }
        for idx in range(patch_count)
    ]


def _default_movement_matrix(patch_count: int) -> list[list[float]]:
    if patch_count <= 1:
        return [[1.0]]
    matrix: list[list[float]] = []
    for source in range(patch_count):
        row = []
        destinations = patch_count - 1
        for dest in range(patch_count):
            if source == dest:
                row.append(0.0)
            else:
                row.append(1.0 / destinations)
        matrix.append(row)
    return matrix


def _ensure_patch_population(pop_by_patch: list[list[int]] | None, fallback: list[int], patch_count: int) -> list[list[int]]:
    if pop_by_patch:
        adjusted = [[int(round(x)) for x in row[:AGE_CLASSES]] for row in pop_by_patch[:patch_count]]
    else:
        adjusted = [list(fallback) for _ in range(patch_count)]
    while len(adjusted) < patch_count:
        adjusted.append(list(fallback))
    return adjusted


def _ensure_matrix(matrix: list[list[float]] | None, patch_count: int) -> list[list[float]]:
    if not matrix:
        return _default_movement_matrix(patch_count)
    adjusted = []
    for row in matrix[:patch_count]:
        trimmed = [float(x) for x in row[:patch_count]]
        while len(trimmed) < patch_count:
            trimmed.append(0.0)
        adjusted.append(trimmed)
    while len(adjusted) < patch_count:
        adjusted.append(_default_movement_matrix(patch_count)[len(adjusted)])
    return adjusted


def config_from_dict(data: dict) -> SimulationConfig:
    general = data["general"]
    environment = data["environment"]
    patch_count = int(general.get("patch_count", len(data.get("patches", [])) or 1))
    patches_raw = data.get("patches", _default_patch_configs(environment, patch_count))
    patches = [
        PatchConfig(
            name=str(item["name"]),
            k_mean=float(item["k_mean"]),
            k_sd=float(item["k_sd"]),
            quality=float(item.get("quality", 1.0)),
            catastrophe_interval_years=float(item.get("catastrophe_interval_years", environment.get("catastrophe_interval_years", 10.0))),
        )
        for item in patches_raw[:patch_count]
    ]
    while len(patches) < patch_count:
        patches.append(
            PatchConfig(
                name=f"Patch {len(patches) + 1}",
                k_mean=float(environment["k_mean"]),
                k_sd=float(environment["k_sd"]),
                quality=1.0,
                catastrophe_interval_years=float(environment.get("catastrophe_interval_years", 10.0)),
            )
        )

    species = []
    for item in data["species"]:
        fallback_initial = [int(round(x)) for x in item["initial_population"]]
        species.append(
            SpeciesConfig(
                name=str(item["name"]),
                maturity_age=int(item["maturity_age"]),
                initial_population=fallback_initial,
                initial_population_by_patch=_ensure_patch_population(
                    item.get("initial_population_by_patch"),
                    fallback_initial,
                    patch_count,
                ),
                fecundity_mean=[float(x) for x in item["fecundity_mean"]],
                fecundity_sd=float(item["fecundity_sd"]),
                survival_mean=[float(x) for x in item["survival_mean"]],
                survival_sd=float(item["survival_sd"]),
                migration_weights=[float(x) for x in item["migration_weights"]],
                baseline_emigration=[float(x) for x in item.get("baseline_emigration", [0.0] * AGE_CLASSES)],
                density_emigration=[float(x) for x in item.get("density_emigration", [0.0] * AGE_CLASSES)],
                movement_matrix=_ensure_matrix(item.get("movement_matrix"), patch_count),
                catastrophe_affects_reproduction=bool(item.get("catastrophe_affects_reproduction", False)),
            )
        )

    return SimulationConfig(
        general=GeneralConfig(
            years=int(general["years"]),
            replicates=int(general["replicates"]),
            seed=int(general["seed"]),
            mode=str(general["mode"]),
            spatial_mode=str(general.get("spatial_mode", "single_location")),
            patch_count=patch_count,
        ),
        environment=EnvironmentConfig(
            k_mean=float(environment["k_mean"]),
            k_sd=float(environment["k_sd"]),
            heavy_tail=bool(environment["heavy_tail"]),
            heavy_tail_df=float(environment["heavy_tail_df"]),
            catastrophe_enabled=bool(environment.get("catastrophe_enabled", False)),
            catastrophe_interval_years=float(environment.get("catastrophe_interval_years", 10.0)),
            patch_specific_catastrophes=bool(environment.get("patch_specific_catastrophes", False)),
            joint_k=bool(environment["joint_k"]),
            species_weights=[float(x) for x in environment["species_weights"]],
        ),
        patches=patches,
        species=species,
    )


def _draw_k(mean: float, sd: float, environment: EnvironmentConfig, rng: np.random.Generator) -> float:
    return float(
        draw_lognormal_mean_sd(
            mean,
            sd,
            rng,
            heavy_tail=environment.heavy_tail,
            heavy_tail_df=environment.heavy_tail_df,
        )
    )


def _draw_catastrophe(enabled: bool, interval_years: float, rng: np.random.Generator) -> bool:
    if not enabled:
        return False
    interval = max(interval_years, 1.0)
    probability = min(1.0, 1.0 / interval)
    return bool(rng.random() < probability)


def _patch_k_t(patch: PatchConfig, environment: EnvironmentConfig, rng: np.random.Generator) -> float:
    return _draw_k(max(patch.k_mean * patch.quality, 0.01), patch.k_sd, environment, rng)


def _project_species(
    current_population: np.ndarray,
    species: SpeciesConfig,
    environment: EnvironmentConfig,
    rng: np.random.Generator,
    reproduction_blocked: bool = False,
) -> np.ndarray:
    next_population = np.zeros(AGE_CLASSES, dtype=int)
    if current_population.sum() <= 0:
        return next_population

    if reproduction_blocked:
        births = 0
    else:
        fecundity = draw_lognormal_mean_sd(
            np.asarray(species.fecundity_mean, dtype=float),
            species.fecundity_sd,
            rng,
            heavy_tail=environment.heavy_tail,
            heavy_tail_df=environment.heavy_tail_df,
        )
        maturity_index = max(species.maturity_age - 1, 0)
        fecundity[:maturity_index] = 0.0
        births = rng.poisson(current_population * fecundity).sum()

    survival = draw_beta_mean_sd(np.asarray(species.survival_mean, dtype=float), species.survival_sd, rng)

    next_population[0] = int(births)
    for age_idx in range(SURVIVAL_CLASSES):
        count = int(current_population[age_idx])
        if count <= 0:
            continue
        next_population[age_idx + 1] = int(rng.binomial(count, float(survival[age_idx])))

    return next_population


def _age_removal_probabilities(population: np.ndarray, migration_weights: np.ndarray) -> np.ndarray:
    weighted = np.asarray(population, dtype=float) * np.maximum(migration_weights, 0.0)
    if weighted.sum() <= 0:
        weighted = np.asarray(population, dtype=float)
    if weighted.sum() <= 0:
        return np.zeros_like(weighted, dtype=float)
    return weighted / weighted.sum()


def _reproductive_removal_probabilities(
    population: np.ndarray,
    migration_weights: np.ndarray,
    maturity_age: int,
) -> np.ndarray:
    maturity_index = max(maturity_age - 1, 0)
    adult_population = np.asarray(population, dtype=float).copy()
    adult_population[:maturity_index] = 0.0
    adult_weights = np.asarray(migration_weights, dtype=float).copy()
    adult_weights[:maturity_index] = 0.0
    return _age_removal_probabilities(adult_population, adult_weights)


def _apply_single_species_emigration(
    projected_population: np.ndarray,
    species: SpeciesConfig,
    k_t: float,
    rng: np.random.Generator,
) -> np.ndarray:
    cap = max(int(np.floor(k_t)), 0)
    reproductive_total = _reproductive_total(projected_population, species.maturity_age)
    excess = max(reproductive_total - cap, 0)
    if excess <= 0:
        return projected_population

    probabilities = _reproductive_removal_probabilities(
        projected_population,
        np.asarray(species.migration_weights, dtype=float),
        species.maturity_age,
    )
    emigrants = rng.multinomial(excess, probabilities)
    adjusted = projected_population - emigrants
    adjusted[adjusted < 0] = 0
    return adjusted


def _allocate_species_emigration_counts(
    projected_populations: list[np.ndarray],
    species: list[SpeciesConfig],
    species_weights: np.ndarray,
    k_t: float,
    rng: np.random.Generator,
) -> np.ndarray:
    reproductive_totals = np.asarray(
        [_reproductive_total(pop, species[idx].maturity_age) for idx, pop in enumerate(projected_populations)],
        dtype=int,
    )
    weighted_total = float(np.dot(species_weights, reproductive_totals))
    if weighted_total <= k_t or reproductive_totals.sum() <= 0:
        return np.zeros(len(projected_populations), dtype=int)

    migration_mass = []
    for pop, config, weight in zip(projected_populations, species, species_weights, strict=True):
        pop_float = np.asarray(pop, dtype=float).copy()
        maturity_index = max(config.maturity_age - 1, 0)
        pop_float[:maturity_index] = 0.0
        mig = np.maximum(np.asarray(config.migration_weights, dtype=float), 0.0).copy()
        mig[:maturity_index] = 0.0
        mass = weight * float(np.dot(pop_float, mig))
        if mass <= 0 and pop_float.sum() > 0:
            mass = weight * float(pop_float.sum())
        migration_mass.append(mass)

    migration_mass_arr = np.asarray(migration_mass, dtype=float)
    if migration_mass_arr.sum() <= 0:
        migration_mass_arr = species_weights * reproductive_totals

    species_prob = migration_mass_arr / migration_mass_arr.sum()
    weighted_excess = weighted_total - k_t
    removal_counts = np.floor(weighted_excess * species_prob / np.maximum(species_weights, 1e-9)).astype(int)
    removal_counts = np.minimum(removal_counts, reproductive_totals)

    current_weighted = weighted_total - float(np.dot(species_weights, removal_counts))
    available = reproductive_totals - removal_counts
    while current_weighted > k_t + 1e-9 and available.sum() > 0:
        candidate_probs = np.where(available > 0, species_prob, 0.0)
        candidate_probs = candidate_probs / candidate_probs.sum()
        chosen = int(rng.choice(len(projected_populations), p=candidate_probs))
        removal_counts[chosen] += 1
        available[chosen] -= 1
        current_weighted -= species_weights[chosen]

    return removal_counts


def _apply_joint_emigration(
    projected_populations: list[np.ndarray],
    species: list[SpeciesConfig],
    environment: EnvironmentConfig,
    k_t: float,
    rng: np.random.Generator,
) -> list[np.ndarray]:
    adjusted = [pop.copy() for pop in projected_populations]
    weights = np.asarray(environment.species_weights[: len(species)], dtype=float)
    removal_counts = _allocate_species_emigration_counts(adjusted, species, weights, k_t, rng)

    for idx, remove_n in enumerate(removal_counts):
        if remove_n <= 0:
            continue
        probs = _reproductive_removal_probabilities(
            adjusted[idx],
            np.asarray(species[idx].migration_weights, dtype=float),
            species[idx].maturity_age,
        )
        emigrants = rng.multinomial(int(remove_n), probs)
        adjusted[idx] = adjusted[idx] - emigrants
        adjusted[idx][adjusted[idx] < 0] = 0

    return adjusted


def _reproductive_total(population: np.ndarray, maturity_age: int) -> int:
    maturity_index = max(maturity_age - 1, 0)
    return int(population[maturity_index:].sum())


def _migration_probabilities(row: np.ndarray, source_idx: int) -> np.ndarray:
    probs = np.asarray(row, dtype=float).copy()
    if probs.size == 1:
        return np.array([1.0], dtype=float)
    probs[source_idx] = 0.0
    probs = np.maximum(probs, 0.0)
    total = probs.sum()
    if total <= 0:
        probs[source_idx] = 1.0
        total = 1.0
    return probs / total


def _apply_metapopulation_dispersal(
    projected_by_species: list[list[np.ndarray]],
    config: SimulationConfig,
    k_values: np.ndarray,
    rng: np.random.Generator,
) -> list[list[np.ndarray]]:
    species_count = len(config.species)
    patch_count = config.general.patch_count
    reproductive_by_species_patch = np.asarray(
        [
            [_reproductive_total(projected_by_species[s][p], config.species[s].maturity_age) for p in range(patch_count)]
            for s in range(species_count)
        ],
        dtype=float,
    )
    if config.general.mode == "two_coexisting" and species_count > 1:
        weights = np.asarray(config.environment.species_weights[:species_count], dtype=float)
        crowding = np.dot(weights, reproductive_by_species_patch) / np.maximum(k_values, 1e-9)
        crowding_by_species = np.tile(crowding, (species_count, 1))
    else:
        crowding_by_species = reproductive_by_species_patch / np.maximum(k_values[None, :], 1e-9)

    adjusted = [[pop.copy() for pop in projected_by_species[s]] for s in range(species_count)]
    immigrants = [[np.zeros(AGE_CLASSES, dtype=int) for _ in range(patch_count)] for _ in range(species_count)]

    for s_idx, species_cfg in enumerate(config.species):
        base = np.asarray(species_cfg.baseline_emigration, dtype=float)
        density = np.asarray(species_cfg.density_emigration, dtype=float)
        movement = np.asarray(species_cfg.movement_matrix, dtype=float)
        for p_idx in range(patch_count):
            local_crowding = max(crowding_by_species[s_idx, p_idx] - 1.0, 0.0)
            probs = np.clip(base + density * local_crowding, 0.0, 1.0)
            destination_probs = _migration_probabilities(movement[p_idx], p_idx)
            for age_idx in range(AGE_CLASSES):
                count = int(adjusted[s_idx][p_idx][age_idx])
                if count <= 0:
                    continue
                emigrants = int(rng.binomial(count, float(probs[age_idx])))
                if emigrants <= 0:
                    continue
                adjusted[s_idx][p_idx][age_idx] -= emigrants
                moved = rng.multinomial(emigrants, destination_probs)
                for dest_idx in range(patch_count):
                    immigrants[s_idx][dest_idx][age_idx] += int(moved[dest_idx])

    for s_idx in range(species_count):
        for p_idx in range(patch_count):
            adjusted[s_idx][p_idx] = adjusted[s_idx][p_idx] + immigrants[s_idx][p_idx]

    return adjusted


def _apply_patch_capacity_regulation(
    populations_by_species: list[list[np.ndarray]],
    config: SimulationConfig,
    k_values: np.ndarray,
    rng: np.random.Generator,
) -> list[list[np.ndarray]]:
    species_count = len(config.species)
    patch_count = config.general.patch_count
    adjusted = [[pop.copy() for pop in populations_by_species[s_idx]] for s_idx in range(species_count)]

    for p_idx in range(patch_count):
        k_t = float(k_values[p_idx])
        if config.general.mode == "two_coexisting" and species_count > 1:
            patch_populations = [adjusted[s_idx][p_idx] for s_idx in range(species_count)]
            regulated = _apply_joint_emigration(patch_populations, config.species, config.environment, k_t, rng)
            for s_idx in range(species_count):
                adjusted[s_idx][p_idx] = regulated[s_idx]
        else:
            for s_idx, species_cfg in enumerate(config.species):
                adjusted[s_idx][p_idx] = _apply_single_species_emigration(adjusted[s_idx][p_idx], species_cfg, k_t, rng)

    return adjusted


def simulate_population(
    config: SimulationConfig,
    progress_callback: Callable[[int, int], None] | None = None,
) -> SimulationResult:
    rng = np.random.default_rng(config.general.seed)
    years = np.arange(config.general.years + 1, dtype=int)
    species_count = len(config.species)
    species_names = [item.name for item in config.species]
    patch_names = [item.name for item in config.patches]
    patch_count = config.general.patch_count

    total = np.zeros((config.general.replicates, config.general.years + 1, species_count), dtype=int)
    reproductive = np.zeros_like(total)
    local_total = np.zeros((config.general.replicates, config.general.years + 1, species_count, patch_count), dtype=int)
    local_reproductive = np.zeros_like(local_total)
    catastrophe_years = np.zeros((config.general.replicates, config.general.years + 1), dtype=bool)
    patch_catastrophe_years = np.zeros((config.general.replicates, config.general.years + 1, patch_count), dtype=bool)
    reproduction_failure_years = np.zeros((config.general.replicates, config.general.years + 1, species_count), dtype=bool)
    patch_reproduction_failure_years = np.zeros(
        (config.general.replicates, config.general.years + 1, species_count, patch_count),
        dtype=bool,
    )
    community_total = np.zeros((config.general.replicates, config.general.years + 1), dtype=int)
    community_reproductive = np.zeros_like(community_total)
    species_extinction_year = np.full((config.general.replicates, species_count), config.general.years + 1, dtype=int)
    community_extinction_year = np.full(config.general.replicates, config.general.years + 1, dtype=int)

    for rep_idx in range(config.general.replicates):
        populations = [
            [np.asarray(spec.initial_population_by_patch[p_idx], dtype=int).copy() for p_idx in range(patch_count)]
            for spec in config.species
        ]

        for sp_idx, species_cfg in enumerate(config.species):
            species_total = 0
            species_reproductive = 0
            for p_idx in range(patch_count):
                population = populations[sp_idx][p_idx]
                patch_total = int(population.sum())
                patch_reproductive = _reproductive_total(population, species_cfg.maturity_age)
                local_total[rep_idx, 0, sp_idx, p_idx] = patch_total
                local_reproductive[rep_idx, 0, sp_idx, p_idx] = patch_reproductive
                species_total += patch_total
                species_reproductive += patch_reproductive
            total[rep_idx, 0, sp_idx] = species_total
            reproductive[rep_idx, 0, sp_idx] = species_reproductive
            if species_total == 0:
                species_extinction_year[rep_idx, sp_idx] = 0

        community_total[rep_idx, 0] = int(total[rep_idx, 0].sum())
        community_reproductive[rep_idx, 0] = int(reproductive[rep_idx, 0].sum())
        if community_total[rep_idx, 0] == 0:
            community_extinction_year[rep_idx] = 0

        for year_idx in range(1, config.general.years + 1):
            if config.general.spatial_mode == "metapopulation" and config.environment.patch_specific_catastrophes:
                patch_catastrophes = np.asarray(
                    [
                        _draw_catastrophe(
                            config.environment.catastrophe_enabled,
                            patch_cfg.catastrophe_interval_years,
                            rng,
                        )
                        for patch_cfg in config.patches
                    ],
                    dtype=bool,
                )
            else:
                shared_catastrophe = _draw_catastrophe(
                    config.environment.catastrophe_enabled,
                    config.environment.catastrophe_interval_years,
                    rng,
                )
                patch_catastrophes = np.full(patch_count, shared_catastrophe, dtype=bool)

            patch_catastrophe_years[rep_idx, year_idx, :] = patch_catastrophes
            catastrophe_years[rep_idx, year_idx] = bool(patch_catastrophes.any())
            projected = []
            for sp_idx, species_cfg in enumerate(config.species):
                species_projected = []
                species_failed = False
                for p_idx in range(patch_count):
                    population = populations[sp_idx][p_idx]
                    reproduction_blocked = bool(
                        patch_catastrophes[p_idx]
                        and species_cfg.catastrophe_affects_reproduction
                        and population.sum() > 0
                    )
                    patch_reproduction_failure_years[rep_idx, year_idx, sp_idx, p_idx] = reproduction_blocked
                    species_failed = species_failed or reproduction_blocked
                    species_projected.append(
                        _project_species(
                            population,
                            species_cfg,
                            config.environment,
                            rng,
                            reproduction_blocked=reproduction_blocked,
                        )
                    )
                reproduction_failure_years[rep_idx, year_idx, sp_idx] = species_failed
                projected.append(species_projected)

            if config.general.spatial_mode == "single_location":
                local_projected = [species_patch_list[0] for species_patch_list in projected]
                patch = config.patches[0]
                if config.general.mode == "single":
                    k_t = _patch_k_t(patch, config.environment, rng)
                    local_projected[0] = _apply_single_species_emigration(local_projected[0], config.species[0], k_t, rng)
                elif config.general.mode == "two_isolated":
                    for idx, species_cfg in enumerate(config.species):
                        k_t = _patch_k_t(patch, config.environment, rng)
                        local_projected[idx] = _apply_single_species_emigration(local_projected[idx], species_cfg, k_t, rng)
                else:
                    k_t = _patch_k_t(patch, config.environment, rng)
                    local_projected = _apply_joint_emigration(local_projected, config.species, config.environment, k_t, rng)
                populations = [[local_projected[s_idx]] for s_idx in range(species_count)]
            else:
                patch_k_values = np.asarray([_patch_k_t(patch_cfg, config.environment, rng) for patch_cfg in config.patches], dtype=float)
                dispersed = _apply_metapopulation_dispersal(projected, config, patch_k_values, rng)
                populations = _apply_patch_capacity_regulation(dispersed, config, patch_k_values, rng)

            for sp_idx, species_cfg in enumerate(config.species):
                species_total = 0
                species_reproductive = 0
                for p_idx in range(patch_count):
                    population = populations[sp_idx][p_idx]
                    patch_total = int(population.sum())
                    patch_reproductive = _reproductive_total(population, species_cfg.maturity_age)
                    local_total[rep_idx, year_idx, sp_idx, p_idx] = patch_total
                    local_reproductive[rep_idx, year_idx, sp_idx, p_idx] = patch_reproductive
                    species_total += patch_total
                    species_reproductive += patch_reproductive
                total[rep_idx, year_idx, sp_idx] = species_total
                reproductive[rep_idx, year_idx, sp_idx] = species_reproductive
                if species_total == 0 and species_extinction_year[rep_idx, sp_idx] > config.general.years:
                    species_extinction_year[rep_idx, sp_idx] = year_idx

            community_total[rep_idx, year_idx] = int(total[rep_idx, year_idx].sum())
            community_reproductive[rep_idx, year_idx] = int(reproductive[rep_idx, year_idx].sum())
            if community_total[rep_idx, year_idx] == 0 and community_extinction_year[rep_idx] > config.general.years:
                community_extinction_year[rep_idx] = year_idx
                break

        if progress_callback:
            progress_callback(rep_idx + 1, config.general.replicates)

    return SimulationResult(
        config=config,
        years=years,
        species_names=species_names,
        patch_names=patch_names,
        total=total,
        reproductive=reproductive,
        local_total=local_total,
        local_reproductive=local_reproductive,
        catastrophe_years=catastrophe_years,
        patch_catastrophe_years=patch_catastrophe_years,
        reproduction_failure_years=reproduction_failure_years,
        patch_reproduction_failure_years=patch_reproduction_failure_years,
        community_total=community_total,
        community_reproductive=community_reproductive,
        species_extinction_year=species_extinction_year,
        community_extinction_year=community_extinction_year,
    )
