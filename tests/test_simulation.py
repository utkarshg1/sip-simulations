import numpy as np

from simulation import (
    LTCG_EXEMPTION,
    STCG_RATE,
    SimulationInputs,
    apply_exit_tax,
    build_summary,
    run_simulation,
)


def test_fixed_sip_principal_calculation():
    result = run_simulation(
        SimulationInputs(
            monthly_sip=10_000,
            years=2,
            expected_inflation_rate=6,
            expected_return_rate=12,
            seed=1,
            simulations=500,
        )
    )

    assert result.total_invested == 240_000
    assert result.monthly_sip == 10_000


def test_summary_statistics_for_known_array():
    values = np.array([100, 200, 300, 400, 500], dtype=float)
    summary = build_summary(values)

    assert summary["p25"] == 200
    assert summary["p50"] == 300
    assert summary["p75"] == 400
    assert summary["iqr"] == 200
    assert summary["average"] == 300
    assert round(summary["std_dev"], 6) == round(np.std(values), 6)


def test_tax_applies_stcg_ltcg_and_exemption():
    monthly_sip = 100_000
    months = 14
    value_per_deposit = np.full((1, months), 2.0)

    after_tax = apply_exit_tax(monthly_sip, value_per_deposit, months)

    gross_value = monthly_sip * 2 * months
    short_term_gains = monthly_sip * 12
    long_term_gains = monthly_sip * 2
    expected_tax = short_term_gains * STCG_RATE + max(long_term_gains - LTCG_EXEMPTION, 0) * 0.125

    assert after_tax[0] == gross_value - expected_tax


def test_same_seed_reproduces_results():
    inputs = SimulationInputs(
        monthly_sip=15_000,
        years=5,
        expected_inflation_rate=6,
        expected_return_rate=12,
        seed=99,
        simulations=1_000,
    )

    first = run_simulation(inputs)
    second = run_simulation(inputs)

    assert first.summary == second.summary
    assert np.array_equal(first.final_values_after_tax, second.final_values_after_tax)


def test_different_seeds_change_distribution():
    base = {
        "monthly_sip": 15_000,
        "years": 5,
        "expected_inflation_rate": 6,
        "expected_return_rate": 12,
        "simulations": 1_000,
    }

    first = run_simulation(SimulationInputs(**base, seed=10))
    second = run_simulation(SimulationInputs(**base, seed=11))

    assert first.summary != second.summary
