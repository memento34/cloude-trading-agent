from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .types import Trade


def build_trade_frame(trades: List[Trade]) -> pd.DataFrame:
    return pd.DataFrame([t.to_dict() for t in trades]) if trades else pd.DataFrame()


def compute_metrics(equity_curve: pd.DataFrame, trades: List[Trade], starting_equity: float) -> Dict[str, float]:
    if equity_curve.empty:
        return {
            "final_equity": starting_equity,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "trade_count": 0,
            "avg_trade_return_pct": 0.0,
            "expectancy": 0.0,
            "calmar": 0.0,
        }

    eq = equity_curve["equity"].astype(float)
    rets = eq.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    downside = rets.where(rets < 0, 0.0)
    running_max = eq.cummax()
    drawdown = eq / running_max - 1.0
    max_dd = abs(drawdown.min()) if len(drawdown) else 0.0

    sharpe = (rets.mean() / (rets.std(ddof=0) + 1e-12)) * np.sqrt(24 * 365)
    sortino = (rets.mean() / (downside.std(ddof=0) + 1e-12)) * np.sqrt(24 * 365)
    total_return = (eq.iloc[-1] / starting_equity - 1.0) * 100
    annual_return = ((eq.iloc[-1] / starting_equity) ** (365 * 24 / max(len(eq), 1)) - 1.0) if len(eq) > 1 else 0.0
    calmar = annual_return / max(max_dd, 1e-12)

    trades_df = build_trade_frame(trades)
    if trades_df.empty:
        profit_factor = 0.0
        win_rate = 0.0
        avg_trade_ret = 0.0
        expectancy = 0.0
    else:
        gross_profit = trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum()
        gross_loss = -trades_df.loc[trades_df["pnl"] < 0, "pnl"].sum()
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        win_rate = (trades_df["pnl"] > 0).mean() * 100
        avg_trade_ret = trades_df["return_pct"].mean()
        expectancy = trades_df["pnl"].mean()

    return {
        "final_equity": round(float(eq.iloc[-1]), 4),
        "total_return_pct": round(float(total_return), 4),
        "max_drawdown_pct": round(float(max_dd * 100), 4),
        "sharpe": round(float(sharpe), 4),
        "sortino": round(float(sortino), 4),
        "profit_factor": round(float(profit_factor), 4),
        "win_rate_pct": round(float(win_rate), 4),
        "trade_count": int(len(trades)),
        "avg_trade_return_pct": round(float(avg_trade_ret), 4),
        "expectancy": round(float(expectancy), 4),
        "calmar": round(float(calmar), 4),
    }


def objective_from_metrics(metrics: Dict[str, float]) -> float:
    return (
        metrics.get("total_return_pct", 0.0) * 0.04
        + metrics.get("sharpe", 0.0) * 1.4
        + metrics.get("sortino", 0.0) * 0.8
        + min(metrics.get("profit_factor", 0.0), 5.0) * 0.35
        + metrics.get("win_rate_pct", 0.0) * 0.01
        + metrics.get("calmar", 0.0) * 0.45
        - metrics.get("max_drawdown_pct", 0.0) * 0.18
        + np.clip(metrics.get("trade_count", 0), 0, 400) * 0.002
    )


def metrics_to_text(metrics: Dict[str, float]) -> str:
    ordered = [
        ("final_equity", "Final equity"),
        ("total_return_pct", "Total return %"),
        ("max_drawdown_pct", "Max drawdown %"),
        ("sharpe", "Sharpe"),
        ("sortino", "Sortino"),
        ("profit_factor", "Profit factor"),
        ("win_rate_pct", "Win rate %"),
        ("trade_count", "Trade count"),
        ("avg_trade_return_pct", "Avg trade return %"),
        ("expectancy", "Expectancy"),
        ("calmar", "Calmar"),
    ]
    return "\n".join(f"{label}: {metrics.get(key)}" for key, label in ordered)
