from __future__ import annotations

from typing import Annotated, Optional
from urllib.parse import urlencode

import plotly.graph_objects as go
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from plotly.io import to_html

from simulation import SIMULATION_COUNT, SimulationInputs, run_simulation, validate_inputs


app = FastAPI(title="Monte Carlo SIP Simulator")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


DEFAULT_FORM = {
    "monthly_sip": 15_000,
    "years": 5,
    "expected_inflation_rate": 8,
    "expected_return_rate": 10,
    "seed": 42,
    "step_up_rate": 10,
    "step_up_enabled": True,
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
async def simulate_post(
    request: Request,
    monthly_sip: Annotated[float, Form()],
    years: Annotated[int, Form()],
    expected_inflation_rate: Annotated[float, Form()],
    expected_return_rate: Annotated[float, Form()],
    seed: Annotated[str, Form()] = "",
    step_up_enabled: Annotated[str, Form()] = "",
    step_up_rate: Annotated[float, Form()] = 0.0,
) -> HTMLResponse:
    parsed_seed = parse_seed(seed)
    is_step_up = step_up_enabled == "on"
    effective_step_up = step_up_rate if is_step_up else 0.0

    form = {
        "monthly_sip": monthly_sip,
        "years": years,
        "expected_inflation_rate": expected_inflation_rate,
        "expected_return_rate": expected_return_rate,
        "seed": seed,
        "step_up_rate": step_up_rate,
        "step_up_enabled": is_step_up,
    }

    if parsed_seed == "invalid":
        return render_form_with_errors(
            request, form, ["Seed must be a whole number or left blank."]
        )

    inputs = SimulationInputs(
        monthly_sip=monthly_sip,
        years=years,
        expected_inflation_rate=expected_inflation_rate,
        expected_return_rate=expected_return_rate,
        seed=parsed_seed,
        step_up_rate=effective_step_up,
    )
    errors = validate_inputs(inputs)
    if errors:
        return render_form_with_errors(request, form, errors)

    params: dict[str, str] = {
        "monthly_sip": str(monthly_sip),
        "years": str(years),
        "expected_inflation_rate": str(expected_inflation_rate),
        "expected_return_rate": str(expected_return_rate),
        "step_up_rate": str(effective_step_up),
    }
    if seed.strip():
        params["seed"] = seed.strip()
    return RedirectResponse(url=f"/simulate?{urlencode(params)}", status_code=303)


@app.get("/simulate", response_class=HTMLResponse)
async def simulate_get(
    request: Request,
    monthly_sip: Annotated[float, Query()],
    years: Annotated[int, Query()],
    expected_inflation_rate: Annotated[float, Query()],
    expected_return_rate: Annotated[float, Query()],
    seed: Annotated[Optional[str], Query()] = None,
    step_up_rate: Annotated[float, Query()] = 0.0,
) -> HTMLResponse:
    seed_str = seed or ""
    parsed_seed = parse_seed(seed_str)
    form = {
        "monthly_sip": monthly_sip,
        "years": years,
        "expected_inflation_rate": expected_inflation_rate,
        "expected_return_rate": expected_return_rate,
        "seed": seed_str,
        "step_up_rate": step_up_rate,
        "step_up_enabled": step_up_rate > 0,
    }

    if parsed_seed == "invalid":
        return render_form_with_errors(
            request, form, ["Seed must be a whole number or left blank."]
        )

    inputs = SimulationInputs(
        monthly_sip=monthly_sip,
        years=years,
        expected_inflation_rate=expected_inflation_rate,
        expected_return_rate=expected_return_rate,
        seed=parsed_seed,
        step_up_rate=step_up_rate,
    )
    errors = validate_inputs(inputs)
    if errors:
        return render_form_with_errors(request, form, errors)

    return _render_results(request, inputs, form)


def _render_results(request: Request, inputs: SimulationInputs, form: dict) -> HTMLResponse:
    result = run_simulation(inputs)
    nominal_histogram_html = build_histogram(
        result.final_values_after_tax,
        result.summary,
        title="Future after-tax maturity value",
        xaxis_title="Future after-tax maturity value",
    )
    real_histogram_html = build_histogram(
        result.real_values_after_tax,
        result.real_summary,
        title="Today's-worth after-tax value",
        xaxis_title="Today's-worth after-tax value",
        bar_color="#818cf8",
    )
    monthly_path_html = build_monthly_path_chart(result.monthly_path)

    return templates.TemplateResponse(
        request,
        "results.html",
        {
            "form": form,
            "result": result,
            "summary_cards": build_summary_cards(result.summary),
            "real_summary_cards": build_summary_cards(result.real_summary),
            "nominal_histogram_html": nominal_histogram_html,
            "real_histogram_html": real_histogram_html,
            "monthly_path_html": monthly_path_html,
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
    form: dict[str, float | int | str | bool],
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


def build_histogram(
    values,
    summary: dict[str, float],
    title: str,
    xaxis_title: str,
    bar_color: str = "#14b8a6",
) -> str:
    figure = go.Figure()
    figure.add_trace(
        go.Histogram(
            x=values,
            nbinsx=70,
            marker_color=bar_color,
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
        margin={"l": 40, "r": 16, "t": 48, "b": 40},
        height=400,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.96)",
        bargap=0.02,
        title={"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 14}},
        xaxis_title=xaxis_title,
        yaxis_title="Simulation count",
        font={"family": "Inter, ui-sans-serif, system-ui", "size": 11},
    )
    return to_html(
        figure,
        full_html=False,
        include_plotlyjs="cdn",
        config={"displayModeBar": False, "responsive": True},
    )


def build_monthly_path_chart(monthly_path: dict) -> str:
    x_values = monthly_path["years"]
    figure = go.Figure()

    # Outer band fill (2.5 – 97.5)
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p97_5"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p2_5"],
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(129, 140, 248, 0.14)",
            line={"width": 0},
            name="2.5–97.5 percentile band",
            hoverinfo="skip",
        )
    )

    # Inner band fill (25 – 75)
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p75"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p25"],
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(20, 184, 166, 0.20)",
            line={"width": 0},
            name="25–75 percentile band",
            hoverinfo="skip",
        )
    )

    # Median line
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p50"],
            mode="lines",
            line={"color": "#0f766e", "width": 3},
            name="50th percentile after-tax corpus",
            hoverinfo="skip",
        )
    )

    # Principal line
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["principal"],
            mode="lines",
            line={"color": "#f59e0b", "width": 3, "dash": "dash"},
            name="Principal invested",
            hoverinfo="skip",
        )
    )

    # Single ghost trace — carries all 6 values, drives the entire tooltip
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=monthly_path["p50"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            customdata=list(zip(
                monthly_path["principal"],
                monthly_path["p2_5"],
                monthly_path["p25"],
                monthly_path["p50"],
                monthly_path["p75"],
                monthly_path["p97_5"],
            )),
            hovertemplate=(
                "<b>Year %{x:.1f}</b><br>"
                "─────────────────<br>"
                "Principal &nbsp;&nbsp;&nbsp;&nbsp;: Rs %{customdata[0]:,.0f}<br>"
                "2.5 pctile &nbsp;&nbsp;: Rs %{customdata[1]:,.0f}<br>"
                "25 pctile &nbsp;&nbsp;&nbsp;: Rs %{customdata[2]:,.0f}<br>"
                "50 pctile &nbsp;&nbsp;&nbsp;: Rs %{customdata[3]:,.0f}<br>"
                "75 pctile &nbsp;&nbsp;&nbsp;: Rs %{customdata[4]:,.0f}<br>"
                "97.5 pctile : Rs %{customdata[5]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

    figure.update_layout(
        template="plotly_white",
        margin={"l": 40, "r": 16, "t": 48, "b": 40},
        height=420,
        title={"text": "Monthly after-tax corpus path", "x": 0.01, "xanchor": "left", "font": {"size": 14}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.96)",
        xaxis_title="Investment year",
        yaxis_title="After-tax corpus",
        hovermode="closest",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        font={"family": "Inter, ui-sans-serif, system-ui", "size": 11},
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
