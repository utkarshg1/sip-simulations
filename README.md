# Monte Carlo SIP Simulator

A high-performance web app that runs **100,000 NumPy-vectorised Monte Carlo simulations** to show the full distribution of after-tax outcomes for a Systematic Investment Plan (SIP). Built with FastAPI, Jinja2, Plotly, and optional PostgreSQL caching.

🌐 **Live demo:** [sip-simulations.onrender.com](https://sip-simulations.onrender.com/)

---

## What's new in v2.0

- **PostgreSQL caching** — simulation results are cached by parameter hash. Repeated runs with the same inputs load instantly without re-simulating.
- **Cache-aware loading animation** — before each simulation, the app checks the cache and shows "Cache hit ✓ / Loading cached results…" or "Crunching numbers / Running 1,00,000 simulations…" accordingly.
- **Mobile responsiveness** — fully polished layout for small screens, including chart sizing, card stacking, and horizontal scroll for tables.

---

## What it does

Most SIP calculators give you a single number. This simulator gives you the full picture — because real markets are noisy.

It samples 100,000 possible futures by varying annual returns and inflation around your expected values, applies a simplified Indian equity mutual fund exit tax model (LTCG / STCG), and plots the distribution of outcomes. You see pessimistic, median, and optimistic scenarios side by side.

### Key outputs

- **Nominal maturity distribution** — future rupee value after exit tax, across all 100,000 simulations
- **Inflation-adjusted distribution** — the same values discounted back to today's purchasing power
- **Net capital gains distribution** — nominal and inflation-adjusted capital gains after tax
- **Monthly corpus path chart** — how your portfolio grows year by year, showing the 2.5–97.5 and 25–75 percentile bands alongside the median and principal invested
- **Summary statistics** — 2.5, 25, 50, 75, 97.5 percentile, IQR, average, and standard deviation for nominal, real, and net gains values

---

## SIP modes

| Mode | Description |
|---|---|
| **Fixed SIP** | Same ₹ amount invested every month for the full duration (top‑up = 0) |
| **Step-up SIP** | SIP amount increases by a fixed ₹ amount each year, with an optional monthly cap |

All inputs are always visible — there is no mode toggle. The top‑up amount controls the annual increase; when set to 0 the SIP behaves as a fixed SIP. An optional **monthly cap** clamps the per‑month installment.

When a top‑up is specified, a **yearly schedule table** appears on the results page showing the monthly SIP, annual principal, and cumulative principal for each year.

---

## Simulation model

| Parameter | Detail |
|---|---|
| Simulations | 100,000 per run (processed in chunks of 10,000) |
| Return model | Normal distribution centred on your expected return ± 3% annual std dev |
| Inflation model | Normal distribution centred on your expected inflation ± 3% annual std dev |
| Tax model | Simplified LTCG (12.5%) and STCG (20%) exit tax on equity mutual funds |
| SIP style | Fixed (constant amount) or Step-up (fixed ₹ annual top‑up + optional cap) |
| Seed | Optional — set for reproducible results, leave blank for a fresh run |

---

## Tech stack

| Layer | Technology |
|---|---|---|
| Web framework | FastAPI |
| Templating | Jinja2 |
| Simulation engine | NumPy (vectorised, chunked) |
| Charts | Plotly |
| Styling | Tailwind CSS + custom CSS |
| Server | Uvicorn |
| Package manager | uv |
| Caching (opt.) | PostgreSQL + asyncpg |
| Cache check | `/check-cache` endpoint — instant cache lookup on form submit |

---

## Running locally

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies
uv sync

# (Optional) Enable PostgreSQL caching — create .env from example
cp .env.example .env
# Edit .env with your real DATABASE_URL

# Start the dev server
uv run uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

Open `http://localhost:5000` in your browser.

---

## Running with Docker

```bash
# Create .env first (required for Docker — template provided)
cp .env.example .env

# Build and start
docker compose up --build

# Or build and run manually (inject .env at runtime)
docker build -t sip-simulator .
docker run -p 5000:5000 --env-file .env sip-simulator
```

Open `http://localhost:5000` in your browser.

---

## Running tests

```bash
uv run pytest
```

---

## Shareable results

Every simulation result has a unique URL containing all input parameters as query strings:

```
# Fixed SIP (top‑up and cap both 0)
/simulate?monthly_sip=15000&years=5&expected_inflation_rate=8&expected_return_rate=10&seed=42

# Step-up SIP — ₹5,000/year top-up, no cap
/simulate?monthly_sip=15000&years=5&expected_inflation_rate=8&expected_return_rate=10&seed=42&step_up_top_up_amount=5000

# Step-up SIP with ₹50,000/month cap
/simulate?monthly_sip=15000&years=10&expected_inflation_rate=6&expected_return_rate=12&seed=42&step_up_top_up_amount=5000&step_up_cap_amount=50000
```

Use the **Copy link** button on any results page to copy the URL and share it. Anyone who opens the link sees exactly the same simulation.

---

## Project structure

```
.
├── main.py           # FastAPI app, routes, Plotly chart builders
├── simulation.py     # NumPy Monte Carlo engine (Fixed + Step-up SIP)
├── db.py             # PostgreSQL caching (asyncpg, hash-based result cache)
├── templates/
│   ├── base.html     # Shared layout, loading overlay
│   ├── index.html    # Input form with top-up, cap, rates, and seed fields
│   └── results.html  # Results page with histograms, summary cards, yearly schedule, path chart
├── static/
│   └── styles.css    # Custom styles and animations (mobile-responsive)
├── tests/
│   ├── test_app.py
│   └── test_simulation.py
├── Dockerfile
├── docker-compose.yml
├── .env.example      # Template for DATABASE_URL
└── pyproject.toml
```

---

## PostgreSQL caching (optional)

When a `DATABASE_URL` environment variable is present, the app connects to PostgreSQL and caches simulation results. Each unique set of input parameters is hashed (SHA-256) and used as a cache key. On subsequent requests with the same parameters, the pre-rendered results are served directly from the cache — skipping the 100,000‑simulation run entirely.

Before each simulation, the form calls the `/check-cache` endpoint with the same parameters and shows one of two loading states:

| State | Overlay text |
|-------|-------------|
| **Cache hit** | "Cache hit ✓ — Loading cached results…" |
| **Cache miss** | "Crunching numbers — Running 1,00,000 Monte Carlo simulations" |

**No Docker‑ised Postgres** — point it at your own instance:

```bash
# Create .env from the example and fill in your connection string
cp .env.example .env

# The app reads DATABASE_URL at startup
DATABASE_URL=postgresql://user:password@host:5432/sip_simulation
```

The cache table (`result_cache`) is created automatically on first start. If the env var is absent, the app works exactly as before — no database required.

---

## Default inputs

| Input | Default |
|---|---|
| Monthly SIP | ₹15,000 |
| Investment years | 5 |
| Expected inflation | 8% |
| Expected return | 10% |
| Seed | 42 |
| Annual top‑up | ₹0 (fixed SIP) |
| Monthly cap | ₹0 (no limit, greyed out by default) |
