from __future__ import annotations

import math

from model import AGE_CLASSES, SURVIVAL_CLASSES, SimulationConfig


def validate_config(config: SimulationConfig) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if config.general.years < 2 or config.general.years > 1000:
        errors.append("Simulation years must be between 2 and 1000.")
    if config.general.replicates < 1 or config.general.replicates > 1000:
        errors.append("Replicates must be between 1 and 1000.")
    if config.general.mode not in {"single", "two_isolated", "two_coexisting"}:
        errors.append("Mode must be one of: single, two_isolated, two_coexisting.")
    if config.general.spatial_mode not in {"single_location", "metapopulation"}:
        errors.append("Spatial mode must be either single_location or metapopulation.")
    if config.general.patch_count < 1:
        errors.append("Patch count must be at least 1.")
    if config.general.spatial_mode == "metapopulation" and config.general.patch_count < 2:
        warnings.append("Metapopulation mode usually requires at least 2 patches.")
    if config.general.mode == "single" and len(config.species) != 1:
        errors.append("Single-species mode requires exactly one species.")
    if config.general.mode != "single" and len(config.species) != 2:
        errors.append("Two-species modes require exactly two species.")

    if config.environment.k_mean <= 0:
        errors.append("Mean carrying capacity K must be positive.")
    if config.environment.k_sd < 0:
        errors.append("Carrying-capacity SD cannot be negative.")
    if config.environment.catastrophe_interval_years < 1:
        errors.append("Average catastrophe interval must be at least 1 year.")
    if config.general.spatial_mode == "single_location" and config.environment.patch_specific_catastrophes:
        warnings.append("Patch-specific catastrophe timing is ignored in single-location mode.")
    if len(config.environment.species_weights) < len(config.species):
        errors.append("Not enough species weights were provided for the selected number of species.")
    if len(config.patches) != config.general.patch_count:
        errors.append("Patch configuration count does not match patch_count.")

    for patch in config.patches:
        if patch.k_mean <= 0:
            errors.append(f"{patch.name}: mean carrying capacity must be positive.")
        if patch.k_sd < 0:
            errors.append(f"{patch.name}: carrying-capacity SD cannot be negative.")
        if patch.quality <= 0:
            errors.append(f"{patch.name}: patch quality must be positive.")
        if patch.catastrophe_interval_years < 1:
            errors.append(f"{patch.name}: catastrophe interval must be at least 1 year.")

    for species in config.species:
        if not (2 <= species.maturity_age <= AGE_CLASSES):
            errors.append(f"{species.name}: maturity age must be between 2 and {AGE_CLASSES}.")
        if len(species.initial_population) != AGE_CLASSES:
            errors.append(f"{species.name}: initial population must have {AGE_CLASSES} age classes.")
        if len(species.initial_population_by_patch) != config.general.patch_count:
            errors.append(f"{species.name}: initial population by patch must match the number of patches.")
        for patch_idx, patch_population in enumerate(species.initial_population_by_patch, start=1):
            if len(patch_population) != AGE_CLASSES:
                errors.append(f"{species.name}: patch {patch_idx} initial population must have {AGE_CLASSES} age classes.")
        if len(species.fecundity_mean) != AGE_CLASSES:
            errors.append(f"{species.name}: fecundity mean must have {AGE_CLASSES} age classes.")
        if len(species.survival_mean) != SURVIVAL_CLASSES:
            errors.append(f"{species.name}: survival mean must have {SURVIVAL_CLASSES} annual transitions.")
        if len(species.migration_weights) != AGE_CLASSES:
            errors.append(f"{species.name}: migration weights must have {AGE_CLASSES} age classes.")
        if len(species.baseline_emigration) != AGE_CLASSES:
            errors.append(f"{species.name}: baseline emigration must have {AGE_CLASSES} age classes.")
        if len(species.density_emigration) != AGE_CLASSES:
            errors.append(f"{species.name}: density-dependent emigration must have {AGE_CLASSES} age classes.")
        if len(species.movement_matrix) != config.general.patch_count:
            errors.append(f"{species.name}: movement matrix must match the number of patches.")
        for row_idx, row in enumerate(species.movement_matrix, start=1):
            if len(row) != config.general.patch_count:
                errors.append(f"{species.name}: movement matrix row {row_idx} must match the number of patches.")

        if any(value < 0 for value in species.initial_population):
            errors.append(f"{species.name}: initial population cannot contain negative values.")
        if any(value < 0 for row in species.initial_population_by_patch for value in row):
            errors.append(f"{species.name}: patch initial populations cannot contain negative values.")
        if any(value < 0 for value in species.fecundity_mean):
            errors.append(f"{species.name}: fecundity mean cannot contain negative values.")
        if any((value < 0 or value > 1) for value in species.survival_mean):
            errors.append(f"{species.name}: survival mean values must lie between 0 and 1.")
        if species.fecundity_sd < 0:
            errors.append(f"{species.name}: fecundity SD cannot be negative.")
        if species.survival_sd < 0:
            errors.append(f"{species.name}: survival SD cannot be negative.")
        if any(value < 0 for value in species.migration_weights):
            errors.append(f"{species.name}: migration weights cannot be negative.")
        if any((value < 0 or value > 1) for value in species.baseline_emigration):
            errors.append(f"{species.name}: baseline emigration values must lie between 0 and 1.")
        if any((value < 0 or value > 1) for value in species.density_emigration):
            errors.append(f"{species.name}: density-dependent emigration values must lie between 0 and 1.")
        if any(value < 0 for row in species.movement_matrix for value in row):
            errors.append(f"{species.name}: movement matrix values cannot be negative.")
        for row_idx, row in enumerate(species.movement_matrix, start=1):
            row_sum = sum(row)
            if row_sum <= 0:
                warnings.append(f"{species.name}: movement matrix row {row_idx} has no positive destinations; emigrants will remain in the source patch.")

        maturity_index = species.maturity_age - 1
        if any(value != 0 for value in species.fecundity_mean[:maturity_index]):
            warnings.append(f"{species.name}: fecundity before the first reproductive age will be forced to zero in the simulation.")

        for idx, survival_mean in enumerate(species.survival_mean, start=1):
            max_sd = math.sqrt(max(survival_mean * (1.0 - survival_mean), 0.0))
            if species.survival_sd >= max_sd and max_sd > 0:
                warnings.append(
                    f"{species.name}: survival SD is too large for age transition {idx}->{idx + 1}; it will be clamped internally."
                )
                break

    return errors, warnings
