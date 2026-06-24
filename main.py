from __future__ import annotations

from typing import Annotated

import plotly.graph_objects as go
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from plotly.io import to_html

from simulation import SIMULATION_COUNT, SimulationInputs, run_simulation, validate_inputs


app = FastAPI(title="Monte Carlo SIP Simulator")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


DEFAULT_FORM = {
    "monthly_sip": 25_000,
    "years": 20,
    "expected_inflation_rate": 6,
    "expected_return_rate": 12,
    "seed": 42,
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "form": DEFAULT_FORM,
            "errors": [],
            "simulation_count": SIMULATION_COUNT,
        },
    )


@app.post("/simulate", response_class=HTMLResponse)
async def simulate(
    request: Request,
    monthly_sip: Annotated[float, Form()],
    years: Annotated[int, Form()],
    expected_inflation_rate: Annotated[float, Form()],
    expected_return_rate: Annotated[float, Form()],
    seed: Annotated[str, Form()] = "",
) -> HTMLResponse:
    parsed_seed = parse_seed(seed)
    form = {
        "monthly_sip": monthly_sip,
        "years": years,
        "expected_inflation_rate": expected_inflation_rate,
        "expected_return_rate": expected_return_rate,
        "seed": seed,
    }

    if parsed_seed == "invalid":
        return render_form_with_errors(
            request,
            form,
            ["Seed must be a whole number or left blank."],
        )

    inputs = SimulationInputs(
        monthly_sip=monthly_sip,
        years=years,
        expected_inflation_rate=expected_inflation_rate,
        expected_return_rate=expected_return_rate,
        seed=parsed_seed,
    )
    errors = validate_inputs(inputs)
    if errors:
        return render_form_with_errors(request, form, errors)

    result = run_simulation(inputs)
    histogram_html = build_histogram(result.final_values_after_tax, result.summary)

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "form": form,
            "result": result,
            "summary_cards": build_summary_cards(result.summary),
            "histogram_html": histogram_html,
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def parse_seed(seed: str) -> int | None | str:
    normalized = seed.strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except ValueError:
        return "invalid"


def render_form_with_errors(
    request: Request,
    form: dict[str, float | int | str],
    errors: list[str],
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "form": form,
            "errors": errors,
            "simulation_count": SIMULATION_COUNT,
        },
        status_code=400,
    )


def build_histogram(values, summary: dict[str, float]) -> str:
    figure = go.Figure()
    figure.add_trace(
        go.Histogram(
            x=values,
            nbinsx=70,
            marker_color="#14b8a6",
            opacity=0.88,
            hovertemplate="After-tax value: Rs %{x:,.0f}<br>Runs: %{y}<extra></extra>",
        )
    )
    percentile_markers = [
        ("2.5%", summary["p2_5"], "#fb7185"),
        ("25%", summary["p25"], "#f59e0b"),
        ("50%", summary["p50"], "#14b8a6"),
        ("75%", summary["p75"], "#38bdf8"),
        ("97.5%", summary["p97_5"], "#818cf8"),
    ]
    for label, value, color in percentile_markers:
        figure.add_vline(
            x=value,
            line_width=2,
            line_dash="dash",
            line_color=color,
            annotation_text=label,
            annotation_position="top",
            annotation_font_size=12,
            annotation_font_color=color,
        )

    figure.update_layout(
        template="plotly_white",
        margin={"l": 56, "r": 28, "t": 58, "b": 54},
        height=520,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.96)",
        bargap=0.02,
        xaxis_title="After-tax maturity value",
        yaxis_title="Simulation count",
        font={"family": "Inter, ui-sans-serif, system-ui"},
    )
    return to_html(
        figure,
        full_html=False,
        include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def build_summary_cards(summary: dict[str, float]) -> list[dict[str, str | float]]:
    return [
        {"label": "2.5 percentile", "value": summary["p2_5"], "tone": "rose"},
        {"label": "25 percentile", "value": summary["p25"], "tone": "amber"},
        {"label": "50 percentile", "value": summary["p50"], "tone": "teal"},
        {"label": "75 percentile", "value": summary["p75"], "tone": "sky"},
        {"label": "97.5 percentile", "value": summary["p97_5"], "tone": "indigo"},
        {"label": "IQR", "value": summary["iqr"], "tone": "violet"},
        {"label": "Average", "value": summary["average"], "tone": "emerald"},
        {"label": "Standard deviation", "value": summary["std_dev"], "tone": "slate"},
    ]
