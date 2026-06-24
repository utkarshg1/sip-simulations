from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


SIMULATION_COUNT = 100_000
SIMULATION_CHUNK_SIZE = 10_000
RATE_STD_DEV = 0.03
MIN_RATE = -0.99
STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125_000.0
LTCG_MONTH_CUTOFF = 12


@dataclass(frozen=True)
class SimulationInputs:
    monthly_sip: float
    years: int
    expected_inflation_rate: float
    expected_return_rate: float
    seed: int | None = None
    simulations: int = SIMULATION_COUNT


@dataclass(frozen=True)
class SimulationResult:
    final_values_after_tax: NDArray[np.float64]
    final_values_before_tax: NDArray[np.float64]
    real_values_after_tax: NDArray[np.float64]
    monthly_sip: float
    total_invested: float
    years: int
    simulations: int
    seed: int | None
    summary: dict[str, float]


def validate_inputs(inputs: SimulationInputs) -> list[str]:
    errors: list[str] = []
    if inputs.monthly_sip <= 0:
        errors.append("Monthly SIP must be greater than 0.")
    if inputs.years <= 0:
        errors.append("Investment years must be greater than 0.")
    if inputs.years > 60:
        errors.append("Investment years must be 60 or less.")
    if inputs.simulations <= 0:
        errors.append("Simulation count must be greater than 0.")
    if inputs.simulations > 250_000:
        errors.append("Simulation count must be 250,000 or less.")
    if inputs.expected_inflation_rate <= -99:
        errors.append("Expected inflation must be greater than -99%.")
    if inputs.expected_return_rate <= -99:
        errors.append("Expected return must be greater than -99%.")
    return errors


def run_simulation(inputs: SimulationInputs) -> SimulationResult:
    errors = validate_inputs(inputs)
    if errors:
        raise ValueError(" ".join(errors))

    months = inputs.years * 12
    rng = np.random.default_rng(inputs.seed)

    final_before_tax = np.empty(inputs.simulations, dtype=np.float64)
    final_after_tax = np.empty(inputs.simulations, dtype=np.float64)
    real_after_tax = np.empty(inputs.simulations, dtype=np.float64)

    for start in range(0, inputs.simulations, SIMULATION_CHUNK_SIZE):
        end = min(start + SIMULATION_CHUNK_SIZE, inputs.simulations)
        chunk_size = end - start
        before_tax, after_tax, real_values = simulate_chunk(inputs, rng, chunk_size, months)
        final_before_tax[start:end] = before_tax
        final_after_tax[start:end] = after_tax
        real_after_tax[start:end] = real_values
    total_invested = inputs.monthly_sip * months

    return SimulationResult(
        final_values_after_tax=final_after_tax,
        final_values_before_tax=final_before_tax,
        real_values_after_tax=real_after_tax,
        monthly_sip=inputs.monthly_sip,
        total_invested=total_invested,
        years=inputs.years,
        simulations=inputs.simulations,
        seed=inputs.seed,
        summary=build_summary(final_after_tax),
    )


def simulate_chunk(
    inputs: SimulationInputs,
    rng: np.random.Generator,
    chunk_size: int,
    months: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    annual_returns = rng.normal(
        inputs.expected_return_rate / 100,
        RATE_STD_DEV,
        size=(chunk_size, inputs.years),
    )
    annual_inflation = rng.normal(
        inputs.expected_inflation_rate / 100,
        RATE_STD_DEV,
        size=(chunk_size, inputs.years),
    )
    annual_returns = np.clip(annual_returns, MIN_RATE, None)
    annual_inflation = np.clip(annual_inflation, MIN_RATE, None)

    monthly_returns = np.repeat((1 + annual_returns) ** (1 / 12) - 1, 12, axis=1)
    growth_factors = np.cumprod(1 + monthly_returns, axis=1)
    terminal_factor = growth_factors[:, -1]

    # SIP contributions are assumed to be invested at the beginning of each month.
    value_per_deposit = terminal_factor[:, None] / growth_factors
    before_tax = inputs.monthly_sip * value_per_deposit.sum(axis=1)
    after_tax = apply_exit_tax(
        monthly_sip=inputs.monthly_sip,
        value_per_deposit=value_per_deposit,
        months=months,
    )

    cumulative_inflation = np.prod(1 + annual_inflation, axis=1)
    real_values = after_tax / cumulative_inflation
    return before_tax, after_tax, real_values


def apply_exit_tax(
    monthly_sip: float,
    value_per_deposit: NDArray[np.float64],
    months: int,
) -> NDArray[np.float64]:
    contribution_values = monthly_sip * value_per_deposit
    gains = np.maximum(contribution_values - monthly_sip, 0)

    ages_at_exit = months - np.arange(months)
    long_term_mask = ages_at_exit > LTCG_MONTH_CUTOFF

    short_term_gains = gains[:, ~long_term_mask].sum(axis=1)
    long_term_gains = gains[:, long_term_mask].sum(axis=1)
    taxable_ltcg = np.maximum(long_term_gains - LTCG_EXEMPTION, 0)

    tax = short_term_gains * STCG_RATE + taxable_ltcg * LTCG_RATE
    return contribution_values.sum(axis=1) - tax


def build_summary(values: NDArray[np.float64]) -> dict[str, float]:
    percentiles = np.percentile(values, [2.5, 25, 50, 75, 97.5])
    average = float(np.mean(values))
    std_dev = float(np.std(values))
    return {
        "p2_5": float(percentiles[0]),
        "p25": float(percentiles[1]),
        "p50": float(percentiles[2]),
        "p75": float(percentiles[3]),
        "p97_5": float(percentiles[4]),
        "iqr": float(percentiles[3] - percentiles[1]),
        "average": average,
        "std_dev": std_dev,
    }
