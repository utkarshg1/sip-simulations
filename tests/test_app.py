from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_index_renders_form():
    response = client.get("/")

    assert response.status_code == 200
    assert "Simulation inputs" in response.text
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
    assert "After-tax outcome distribution" in response.text
    assert "2.5 percentile" in response.text
    assert "Plotly.newPlot" in response.text
    assert '"type":"line"' in response.text
    assert '"text":"2.5%"' in response.text
    assert '"text":"25%"' in response.text
    assert '"text":"50%"' in response.text
    assert '"text":"75%"' in response.text
    assert '"text":"97.5%"' in response.text


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
    assert "After-tax outcome distribution" in response.text
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
