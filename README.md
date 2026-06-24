# Monte Carlo SIP Simulator

A FastAPI and Jinja web app that runs 100,000 NumPy-vectorized SIP simulations and shows after-tax outcomes with a Plotly histogram.

## Run

```powershell
uv sync
uv run uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Test

```powershell
uv run pytest
```
