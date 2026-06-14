from __future__ import annotations

import math

import numpy as np


def _scaled_noise(rng: np.random.Generator, size: int | tuple[int, ...], heavy_tail: bool, heavy_tail_df: float) -> np.ndarray:
    if heavy_tail and heavy_tail_df > 2:
        scale = math.sqrt(heavy_tail_df / (heavy_tail_df - 2.0))
        return rng.standard_t(df=heavy_tail_df, size=size) / scale
    return rng.normal(loc=0.0, scale=1.0, size=size)


def draw_lognormal_mean_sd(
    mean: float | np.ndarray,
    sd: float,
    rng: np.random.Generator,
    heavy_tail: bool = False,
    heavy_tail_df: float = 5.0,
) -> np.ndarray:
    mean_arr = np.asarray(mean, dtype=float)
    if sd <= 0:
        return np.maximum(mean_arr, 0.0)

    safe_mean = np.maximum(mean_arr, 1e-12)
    sigma2 = np.log1p((sd * sd) / (safe_mean * safe_mean))
    sigma = np.sqrt(sigma2)
    mu = np.log(safe_mean) - 0.5 * sigma2
    noise = _scaled_noise(rng, mean_arr.shape, heavy_tail, heavy_tail_df)
    samples = np.exp(mu + sigma * noise)
    return np.where(mean_arr <= 0, 0.0, samples)


def draw_beta_mean_sd(mean: float | np.ndarray, sd: float, rng: np.random.Generator) -> np.ndarray:
    mean_arr = np.clip(np.asarray(mean, dtype=float), 1e-6, 1.0 - 1e-6)
    if sd <= 0:
        return mean_arr

    max_var = mean_arr * (1.0 - mean_arr)
    target_var = np.minimum(sd * sd, 0.95 * max_var)
    concentration = np.maximum((mean_arr * (1.0 - mean_arr) / target_var) - 1.0, 1e-3)
    alpha = np.maximum(mean_arr * concentration, 1e-3)
    beta = np.maximum((1.0 - mean_arr) * concentration, 1e-3)
    return rng.beta(alpha, beta)
