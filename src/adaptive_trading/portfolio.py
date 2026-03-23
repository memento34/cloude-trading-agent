from __future__ import annotations

from typing import Dict

import pandas as pd

from .types import Position


def compute_position_size(
    equity: float,
    entry_price: float,
    atr_value: float,
    risk_per_trade: float,
    stop_atr_mult: float,
    max_symbol_exposure: float,
) -> float:
    stop_distance = max(atr_value * stop_atr_mult, entry_price * 0.002)
    risk_dollars = max(equity * risk_per_trade, 0.0)
    qty_from_risk = risk_dollars / max(stop_distance, 1e-9)
    qty_from_cap = (equity * max_symbol_exposure) / max(entry_price, 1e-9)
    return max(min(qty_from_risk, qty_from_cap), 0.0)


def gross_exposure(positions: Dict[str, Position], latest_prices: Dict[str, float], equity: float) -> float:
    if equity <= 0:
        return 0.0
    gross = 0.0
    for symbol, pos in positions.items():
        price = latest_prices.get(symbol, pos.entry_price)
        gross += abs(pos.quantity * price) / equity
    return gross


def cluster_exposure(
    candidate_symbol: str,
    candidate_side: int,
    positions: Dict[str, Position],
    corr: pd.DataFrame,
    latest_prices: Dict[str, float],
    equity: float,
    threshold: float,
) -> float:
    if equity <= 0:
        return 0.0
    exposure = 0.0
    for symbol, pos in positions.items():
        same_direction = pos.side == candidate_side
        correlation = 0.0
        if candidate_symbol in corr.index and symbol in corr.columns:
            correlation = float(corr.loc[candidate_symbol, symbol])
        if same_direction and correlation >= threshold:
            exposure += abs(pos.quantity * latest_prices.get(symbol, pos.entry_price)) / equity
    return exposure
