"""Estimated USD cost from per-model prices in eval/prices.json.

Never billed amounts — always labeled estimated. Fill in real prices yourself.
"""

from __future__ import annotations

import json
import os
from typing import Any

PLACEHOLDER_PRICES: dict[str, Any] = {
    "_comment": (
        "Fill in real USD-per-million-token prices for the models you run. "
        "dc-eval labels every figure from this file as estimated, not billed."
    ),
    "models": {
        "default": {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.30,
            "cache_write": 3.75,
        },
        "composer-1": {
            "input": 1.25,
            "output": 10.0,
            "cache_read": 0.125,
            "cache_write": 1.25,
        },
        "sonnet": {
            "input": 3.0,
            "output": 15.0,
            "cache_read": 0.30,
            "cache_write": 3.75,
        },
    },
}


def default_prices_path(eval_dir: str) -> str:
    return os.path.join(eval_dir, "prices.json")


def ensure_prices_file(eval_dir: str) -> str:
    path = default_prices_path(eval_dir)
    if os.path.isfile(path):
        return path
    os.makedirs(eval_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(PLACEHOLDER_PRICES, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def load_prices(eval_dir: str) -> dict[str, Any]:
    path = default_prices_path(eval_dir)
    if not os.path.isfile(path):
        return PLACEHOLDER_PRICES
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else PLACEHOLDER_PRICES
    except (OSError, json.JSONDecodeError):
        return PLACEHOLDER_PRICES


def _rates_for_model(prices: dict[str, Any], model: str) -> dict[str, float]:
    models = prices.get("models") if isinstance(prices.get("models"), dict) else {}
    key = (model or "default").strip()
    blob = None
    if key in models:
        blob = models[key]
    else:
        low = key.lower()
        for name, val in models.items():
            if name == "default":
                continue
            if name.lower() in low or low in name.lower():
                blob = val
                break
    if not isinstance(blob, dict):
        blob = models.get("default") if isinstance(models.get("default"), dict) else {}
    def _f(name: str, default: float) -> float:
        try:
            return float(blob.get(name, default))
        except (TypeError, ValueError):
            return default
    return {
        "input": _f("input", 3.0),
        "output": _f("output", 15.0),
        "cache_read": _f("cache_read", 0.30),
        "cache_write": _f("cache_write", 3.75),
    }


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None,
    cache_write_tokens: int | None,
    eval_dir: str,
) -> float | None:
    if None in (input_tokens, output_tokens, cache_read_tokens, cache_write_tokens):
        return None
    rates = _rates_for_model(load_prices(eval_dir), model)
    million = 1_000_000.0
    return (
        (input_tokens or 0) * rates["input"]
        + (output_tokens or 0) * rates["output"]
        + (cache_read_tokens or 0) * rates["cache_read"]
        + (cache_write_tokens or 0) * rates["cache_write"]
    ) / million
