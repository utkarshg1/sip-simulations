from __future__ import annotations

import hashlib
import json
import logging
import os

import asyncpg
from dotenv import load_dotenv

from simulation import SimulationInputs

logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
logger = logging.getLogger("sip-simulation.db")

_pool: asyncpg.Pool | None = None
_schema: str = "public"


def is_connected() -> bool:
    return _pool is not None


async def init_db() -> None:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        logger.info("DATABASE_URL not set — running without PostgreSQL cache")
        return
    global _pool, _schema
    try:
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1, ssl='require')
        async with _pool.acquire() as conn:
            current_user = await conn.fetchval("SELECT current_user")
            _schema = current_user or "public"
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{_schema}"')
            await conn.execute(f'SET search_path TO "{_schema}", public')
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{_schema}".result_cache (
                    params_hash TEXT PRIMARY KEY,
                    params_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    nominal_histogram_html TEXT,
                    real_histogram_html TEXT,
                    net_gains_histogram_html TEXT,
                    real_net_gains_histogram_html TEXT,
                    monthly_path_html TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    accessed_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        # Recreate pool with persistent search_path for all connections
        await _pool.close()
        _pool = await asyncpg.create_pool(
            dsn, min_size=1, max_size=1, ssl='require',
            server_settings={"search_path": f'"{_schema}", public'},
        )
        logger.info("PostgreSQL cache connected and table ready")
    except Exception as exc:
        logger.error("PostgreSQL connection failed: %s", exc)
        if _pool:
            await _pool.close()
            _pool = None


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def compute_params_hash(inputs: SimulationInputs) -> str:
    data = {
        "monthly_sip": inputs.monthly_sip,
        "years": inputs.years,
        "expected_inflation_rate": inputs.expected_inflation_rate,
        "expected_return_rate": inputs.expected_return_rate,
        "step_up_top_up_amount": inputs.step_up_top_up_amount,
        "step_up_cap_amount": inputs.step_up_cap_amount,
        "seed": inputs.seed,
    }
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_result(params_hash: str) -> dict | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM result_cache WHERE params_hash = $1", params_hash
        )
        if row is None:
            return None
        await conn.execute(
            "UPDATE result_cache SET accessed_at = NOW() WHERE params_hash = $1",
            params_hash,
        )
        return {
            "result_json": row["result_json"],
            "nominal_histogram_html": row["nominal_histogram_html"],
            "real_histogram_html": row["real_histogram_html"],
            "net_gains_histogram_html": row["net_gains_histogram_html"],
            "real_net_gains_histogram_html": row["real_net_gains_histogram_html"],
            "monthly_path_html": row["monthly_path_html"],
        }


async def set_cached_result(
    params_hash: str,
    params_json: str,
    result_json: str,
    nominal_histogram_html: str,
    real_histogram_html: str,
    net_gains_histogram_html: str,
    real_net_gains_histogram_html: str,
    monthly_path_html: str,
) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO result_cache
                (params_hash, params_json, result_json,
                 nominal_histogram_html, real_histogram_html,
                 net_gains_histogram_html, real_net_gains_histogram_html,
                 monthly_path_html)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (params_hash) DO UPDATE SET
                accessed_at = NOW()
            """,
            params_hash,
            params_json,
            result_json,
            nominal_histogram_html,
            real_histogram_html,
            net_gains_histogram_html,
            real_net_gains_histogram_html,
            monthly_path_html,
        )
