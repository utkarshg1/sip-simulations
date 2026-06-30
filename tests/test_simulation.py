import numpy as np

from simulation import (
    LTCG_EXEMPTION,
    STCG_RATE,
    SimulationInputs,
    apply_exit_tax,
    build_monthly_after_tax_paths,
    build_monthly_sip_schedule,
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

    assert result.total_invested == 240_000.0
    assert result.monthly_sip == 10_000
    assert result.step_up_top_up_amount == 0
    assert result.step_up_cap_amount == 0
    assert np.array_equal(result.monthly_path["principal"], np.arange(1, 25) * 10_000)


def test_real_summary_uses_real_after_tax_values():
    result = run_simulation(
        SimulationInputs(
            monthly_sip=10_000,
            years=2,
            expected_inflation_rate=6,
            expected_return_rate=12,
            seed=2,
            simulations=500,
        )
    )

    assert result.real_summary == build_summary(result.real_values_after_tax)


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
    schedule = build_monthly_sip_schedule(monthly_sip, months, 0, 0)

    after_tax = apply_exit_tax(schedule, value_per_deposit, months)

    gross_value = monthly_sip * 2 * months
    short_term_gains = monthly_sip * 12
    long_term_gains = monthly_sip * 2
    expected_tax = short_term_gains * STCG_RATE + max(long_term_gains - LTCG_EXEMPTION, 0) * 0.125

    assert after_tax[0] == gross_value - expected_tax


def test_monthly_after_tax_path_applies_redemption_month_tax():
    monthly_sip = 100_000
    months = 14
    schedule = build_monthly_sip_schedule(monthly_sip, months, 0, 0)
    monthly_returns = np.zeros((1, months))
    monthly_returns[0, -1] = 1.0

    path = build_monthly_after_tax_paths(schedule, monthly_returns)

    gross_value = monthly_sip * 2 * 13 + monthly_sip
    short_term_gains = monthly_sip * 11
    long_term_gains = monthly_sip * 2
    expected_tax = short_term_gains * STCG_RATE + max(long_term_gains - LTCG_EXEMPTION, 0) * 0.125

    assert path[0, -1] == gross_value - expected_tax


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


def test_build_fixed_schedule():
    schedule = build_monthly_sip_schedule(10_000, 36, 0, 0)
    assert np.all(schedule == 10_000)
    assert schedule.shape == (36,)


def test_build_step_up_schedule_year_index():
    schedule = build_monthly_sip_schedule(10_000, 36, 5_000, 0)
    assert schedule[0] == 10_000
    assert schedule[11] == 10_000
    assert schedule[12] == 15_000
    assert schedule[23] == 15_000
    assert schedule[24] == 20_000
    assert schedule[35] == 20_000


def test_build_step_up_schedule_with_cap():
    schedule = build_monthly_sip_schedule(10_000, 36, 5_000, 18_000)
    assert schedule[0] == 10_000
    assert schedule[12] == 15_000
    assert schedule[24] == 18_000
    assert schedule[35] == 18_000


def test_step_up_sip_total_invested():
    result = run_simulation(
        SimulationInputs(
            monthly_sip=10_000,
            years=3,
            expected_inflation_rate=6,
            expected_return_rate=12,
            step_up_top_up_amount=5_000,
            step_up_cap_amount=0,
            seed=1,
            simulations=500,
        )
    )
    assert result.total_invested == 540_000.0
    assert result.step_up_top_up_amount == 5_000
    assert result.step_up_cap_amount == 0


def test_step_up_sip_with_cap_total_invested():
    result = run_simulation(
        SimulationInputs(
            monthly_sip=10_000,
            years=3,
            expected_inflation_rate=6,
            expected_return_rate=12,
            step_up_top_up_amount=5_000,
            step_up_cap_amount=18_000,
            seed=1,
            simulations=500,
        )
    )
    assert result.total_invested == 516_000.0


def test_step_up_principal_path():
    result = run_simulation(
        SimulationInputs(
            monthly_sip=10_000,
            years=2,
            expected_inflation_rate=6,
            expected_return_rate=12,
            step_up_top_up_amount=5_000,
            step_up_cap_amount=0,
            seed=1,
            simulations=500,
        )
    )
    expected = np.cumsum(
        [10_000] * 12 + [15_000] * 12
    ).astype(np.float64)
    assert np.array_equal(result.monthly_path["principal"], expected)
