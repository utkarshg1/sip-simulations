from __future__ import annotations

from dataclasses import dataclass, field

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
    step_up_rate: float = 0.0          # annual % increase in SIP (0 = flat)


@dataclass(frozen=True)
class SimulationResult:
    final_values_after_tax: NDArray[np.float64]
    final_values_before_tax: NDArray[np.float64]
    real_values_after_tax: NDArray[np.float64]
    monthly_path: dict[str, NDArray[np.float64]]
    monthly_sip: float
    total_invested: float
    years: int
    simulations: int
    seed: int | None
    summary: dict[str, float]
    real_summary: dict[str, float]
    step_up_rate: float = 0.0
    yearly_sip_schedule: list[dict] = field(default_factory=list)


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
    if inputs.step_up_rate < 0 or inputs.step_up_rate > 100:
        errors.append("Step-up rate must be between 0% and 100%.")
    return errors


def build_monthly_sip_amounts(
    monthly_sip: float,
    years: int,
    step_up_rate: float,
) -> NDArray[np.float64]:
    """Return an array of shape (months,) with the SIP amount for each month."""
    yearly_amounts = [
        monthly_sip * (1 + step_up_rate / 100) ** year
        for year in range(years)
    ]
    return np.repeat(yearly_amounts, 12).astype(np.float64)


def build_yearly_sip_schedule(
    monthly_sip: float,
    years: int,
    step_up_rate: float,
) -> list[dict]:
    return [
        {
            "year": year + 1,
            "monthly_sip": round(monthly_sip * (1 + step_up_rate / 100) ** year, 2),
            "annual_total": round(monthly_sip * (1 + step_up_rate / 100) ** year * 12, 2),
        }
        for year in range(years)
    ]


def run_simulation(inputs: SimulationInputs) -> SimulationResult:
    errors = validate_inputs(inputs)
    if errors:
        raise ValueError(" ".join(errors))

    months = inputs.years * 12
    rng = np.random.default_rng(inputs.seed)

    monthly_sip_amounts = build_monthly_sip_amounts(
        inputs.monthly_sip, inputs.years, inputs.step_up_rate
    )

    final_before_tax = np.empty(inputs.simulations, dtype=np.float64)
    final_after_tax = np.empty(inputs.simulations, dtype=np.float64)
    real_after_tax = np.empty(inputs.simulations, dtype=np.float64)
    monthly_after_tax_paths = np.empty((inputs.simulations, months), dtype=np.float32)

    for start in range(0, inputs.simulations, SIMULATION_CHUNK_SIZE):
        end = min(start + SIMULATION_CHUNK_SIZE, inputs.simulations)
        chunk_size = end - start
        before_tax, after_tax, real_values, monthly_paths = simulate_chunk(
            inputs,
            rng,
            chunk_size,
            months,
            monthly_sip_amounts,
        )
        final_before_tax[start:end] = before_tax
        final_after_tax[start:end] = after_tax
        real_after_tax[start:end] = real_values
        monthly_after_tax_paths[start:end] = monthly_paths.astype(np.float32)

    total_invested = float(monthly_sip_amounts.sum())
    principal_path = np.cumsum(monthly_sip_amounts)

    yearly_schedule = (
        build_yearly_sip_schedule(inputs.monthly_sip, inputs.years, inputs.step_up_rate)
        if inputs.step_up_rate > 0
        else []
    )

    return SimulationResult(
        final_values_after_tax=final_after_tax,
        final_values_before_tax=final_before_tax,
        real_values_after_tax=real_after_tax,
        monthly_path=build_monthly_path_summary(monthly_after_tax_paths, principal_path),
        monthly_sip=inputs.monthly_sip,
        total_invested=total_invested,
        years=inputs.years,
        simulations=inputs.simulations,
        seed=inputs.seed,
        summary=build_summary(final_after_tax),
        real_summary=build_summary(real_after_tax),
        step_up_rate=inputs.step_up_rate,
        yearly_sip_schedule=yearly_schedule,
    )


def simulate_chunk(
    inputs: SimulationInputs,
    rng: np.random.Generator,
    chunk_size: int,
    months: int,
    monthly_sip_amounts: NDArray[np.float64],
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
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
    monthly_after_tax_paths = build_monthly_after_tax_paths(
        monthly_sip_amounts=monthly_sip_amounts,
        monthly_returns=monthly_returns,
    )
    growth_factors = np.cumprod(1 + monthly_returns, axis=1)
    terminal_factor = growth_factors[:, -1]

    value_per_deposit = terminal_factor[:, None] / growth_factors
    before_tax = (monthly_sip_amounts[None, :] * value_per_deposit).sum(axis=1)
    after_tax = apply_exit_tax(
        monthly_sip_amounts=monthly_sip_amounts,
        value_per_deposit=value_per_deposit,
        months=months,
    )

    cumulative_inflation = np.prod(1 + annual_inflation, axis=1)
    real_values = after_tax / cumulative_inflation
    return before_tax, after_tax, real_values, monthly_after_tax_paths


def build_monthly_after_tax_paths(
    monthly_sip_amounts: NDArray[np.float64],
    monthly_returns: NDArray[np.float64],
) -> NDArray[np.float64]:
    chunk_size, months = monthly_returns.shape
    lot_values = np.zeros((chunk_size, months), dtype=np.float64)
    after_tax_paths = np.empty((chunk_size, months), dtype=np.float64)

    for month_index in range(months):
        sip = monthly_sip_amounts[month_index]
        if month_index > 0:
            lot_values[:, :month_index] *= 1 + monthly_returns[:, month_index, None]
        lot_values[:, month_index] = sip

        active_values = lot_values[:, : month_index + 1]
        cost_bases = monthly_sip_amounts[: month_index + 1]
        gains = np.maximum(active_values - cost_bases[None, :], 0)
        ages_at_exit = month_index + 1 - np.arange(month_index + 1)
        long_term_mask = ages_at_exit > LTCG_MONTH_CUTOFF

        short_term_gains = gains[:, ~long_term_mask].sum(axis=1)
        long_term_gains = gains[:, long_term_mask].sum(axis=1)
        taxable_ltcg = np.maximum(long_term_gains - LTCG_EXEMPTION, 0)
        tax = short_term_gains * STCG_RATE + taxable_ltcg * LTCG_RATE
        after_tax_paths[:, month_index] = active_values.sum(axis=1) - tax

    return after_tax_paths


def build_monthly_path_summary(
    monthly_after_tax_paths: NDArray[np.float32],
    principal_path: NDArray[np.float64],
) -> dict[str, NDArray[np.float64]]:
    percentiles = np.percentile(monthly_after_tax_paths, [2.5, 25, 50, 75, 97.5], axis=0)
    months = np.arange(1, principal_path.size + 1, dtype=np.float64)
    return {
        "months": months,
        "years": months / 12,
        "principal": principal_path,
        "p2_5": percentiles[0].astype(np.float64),
        "p25": percentiles[1].astype(np.float64),
        "p50": percentiles[2].astype(np.float64),
        "p75": percentiles[3].astype(np.float64),
        "p97_5": percentiles[4].astype(np.float64),
    }


def apply_exit_tax(
    monthly_sip_amounts: NDArray[np.float64],
    value_per_deposit: NDArray[np.float64],
    months: int,
) -> NDArray[np.float64]:
    contribution_values = value_per_deposit * monthly_sip_amounts[None, :]
    cost_basis = monthly_sip_amounts[None, :]
    gains = np.maximum(contribution_values - cost_basis, 0)

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
