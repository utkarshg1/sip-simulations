from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_index_renders_form():
    response = client.get("/")

    assert response.status_code == 200
    assert "Monte Carlo" in response.text
    assert "tailwindcss" in response.text
    assert 'name="monthly_sip"' in response.text
    assert 'min="100"' in response.text
    assert 'step="100"' in response.text


def test_simulate_renders_cards_and_plotly_histogram():
    response = client.post(
        "/simulate",
        data={
            "monthly_sip": "10000",
            "years": "2",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
        },
    )

    assert response.status_code == 200
    assert "After-tax SIP simulation" in response.text
    assert "Nominal maturity distribution" in response.text
    assert "Inflation-adjusted maturity distribution" in response.text
    assert "Principal and after-tax corpus over time" in response.text
    assert "2.5 percentile" in response.text
    assert "Plotly.newPlot" in response.text
    assert '"type":"line"' in response.text
    assert '"text":"2.5%"' in response.text
    assert '"text":"25%"' in response.text
    assert '"text":"50%"' in response.text
    assert '"text":"75%"' in response.text
    assert '"text":"97.5%"' in response.text
    assert "Principal invested" in response.text
    assert "50th percentile after-tax corpus" in response.text


def test_simulate_accepts_15000_monthly_sip():
    response = client.post(
        "/simulate",
        data={
            "monthly_sip": "15000",
            "years": "10",
            "expected_inflation_rate": "8",
            "expected_return_rate": "12",
            "seed": "42",
        },
    )

    assert response.status_code == 200
    assert "After-tax SIP simulation" in response.text
    assert "Rs 15,000" in response.text


def test_invalid_input_returns_validation_error():
    response = client.post(
        "/simulate",
        data={
            "monthly_sip": "-1",
            "years": "2",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
        },
    )

    assert response.status_code == 400
    assert "Monthly SIP must be greater than 0." in response.text


def test_step_up_simulate_shows_topup_and_cap():
    response = client.post(
        "/simulate",
        data={
            "monthly_sip": "10000",
            "years": "3",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
            "step_up_top_up_amount": "5000",
            "step_up_cap_amount": "18000",
        },
    )

    assert response.status_code == 200
    assert "After-tax SIP simulation" in response.text
    assert "Annual top-up" in response.text
    assert "Monthly cap" in response.text
    assert "5,000" in response.text
    assert "18,000" in response.text


def test_step_up_results_show_stepup_info_even_when_zero():
    response = client.post(
        "/simulate",
        data={
            "monthly_sip": "10000",
            "years": "2",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
        },
    )

    assert response.status_code == 200
    assert "Annual top-up" in response.text
    assert "Monthly cap" in response.text


def test_check_cache_returns_false_without_db():
    response = client.get(
        "/check-cache",
        params={
            "monthly_sip": "10000",
            "years": "2",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {"cached": False}


def test_check_cache_invalid_input_returns_false():
    response = client.get(
        "/check-cache",
        params={
            "monthly_sip": "-1",
            "years": "2",
            "expected_inflation_rate": "6",
            "expected_return_rate": "12",
            "seed": "123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {"cached": False}


def test_check_cache_missing_param_returns_422():
    response = client.get("/check-cache", params={"monthly_sip": "10000"})

    assert response.status_code == 422
