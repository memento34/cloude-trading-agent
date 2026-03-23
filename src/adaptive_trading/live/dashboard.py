from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .state_store import StateStore


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "nan"):
            return default
        return float(value)
    except Exception:
        return default


def _parse_dt(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def _fmt_side(side: Any) -> str:
    return "LONG" if int(side or 0) == 1 else "SHORT"


def _build_trade_frame(trades: List[Dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades).copy()
    if "entry_price" not in df:
        df["entry_price"] = 0.0
    if "exit_price" not in df:
        df["exit_price"] = 0.0
    if "qty" not in df:
        df["qty"] = 0.0
    if "pnl" not in df:
        df["pnl"] = 0.0
    df["entry_price"] = df["entry_price"].apply(_safe_float)
    df["exit_price"] = df["exit_price"].apply(_safe_float)
    df["qty"] = df["qty"].apply(_safe_float)
    df["pnl"] = df["pnl"].apply(_safe_float)
    side_col = df["side"] if "side" in df.columns else pd.Series([0] * len(df), index=df.index)
    entry_time_col = df["entry_time"] if "entry_time" in df.columns else pd.Series([None] * len(df), index=df.index)
    exit_time_col = df["exit_time"] if "exit_time" in df.columns else pd.Series([None] * len(df), index=df.index)
    df["side"] = side_col.apply(lambda x: int(x or 0))
    denom = (df["entry_price"].abs() * df["qty"].abs()).replace(0, pd.NA)
    df["return_pct"] = (df["pnl"] / denom) * 100.0
    df["return_pct"] = df["return_pct"].fillna(0.0)
    df["entry_dt"] = entry_time_col.apply(_parse_dt)
    df["exit_dt"] = exit_time_col.apply(_parse_dt)
    df["holding_hours"] = ((df["exit_dt"] - df["entry_dt"]).dt.total_seconds() / 3600.0).fillna(0.0)
    df["symbol"] = df.get("symbol", "").fillna("")
    df["reason"] = df.get("reason", "").fillna("")
    return df


def _compute_drawdown(equity: pd.Series) -> tuple[float, float]:
    if equity.empty:
        return 0.0, 0.0
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    current = float(dd.iloc[-1]) * 100.0 if len(dd) else 0.0
    max_dd = abs(float(dd.min())) * 100.0 if len(dd) else 0.0
    return round(current, 4), round(max_dd, 4)


def _equity_curve_from_cycles(cycles: List[Dict[str, Any]], starting_equity: float, fallback_trades: pd.DataFrame) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for row in cycles:
        ts = row.get("ran_at") or row.get("time") or row.get("timestamp")
        if not ts:
            continue
        points.append({
            "time": ts,
            "equity": _safe_float(row.get("equity"), starting_equity),
            "open_positions": len((row.get("open_positions") or {})),
            "signal_count": len(row.get("signals") or []),
            "action_count": len(row.get("actions") or []),
        })
    if points:
        dedup: Dict[str, Dict[str, Any]] = {p["time"]: p for p in points}
        ordered = sorted(dedup.values(), key=lambda x: x["time"])
        return ordered[-1000:]

    equity = starting_equity
    synthetic = [{"time": datetime.now(timezone.utc).isoformat(), "equity": starting_equity, "open_positions": 0, "signal_count": 0, "action_count": 0}]
    if not fallback_trades.empty:
        for _, row in fallback_trades.sort_values("exit_dt").iterrows():
            equity += _safe_float(row["pnl"])
            ts = row["exit_dt"]
            synthetic.append({
                "time": ts.isoformat() if pd.notna(ts) else datetime.now(timezone.utc).isoformat(),
                "equity": round(equity, 4),
                "open_positions": 0,
                "signal_count": 0,
                "action_count": 1,
            })
    return synthetic[-1000:]


def _daily_pnl(trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if trades_df.empty:
        return []
    df = trades_df.dropna(subset=["exit_dt"]).copy()
    if df.empty:
        return []
    agg = (
        df.assign(day=df["exit_dt"].dt.strftime("%Y-%m-%d"))
        .groupby("day", as_index=False)["pnl"]
        .sum()
    )
    return [{"date": str(r["day"]), "pnl": round(_safe_float(r["pnl"]), 4)} for _, r in agg.iterrows()][-365:]


def _monthly_pnl(trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if trades_df.empty:
        return []
    df = trades_df.dropna(subset=["exit_dt"]).copy()
    if df.empty:
        return []
    agg = (
        df.assign(month=df["exit_dt"].dt.strftime("%Y-%m"))
        .groupby("month", as_index=False)["pnl"]
        .sum()
    )
    return [{"month": str(r["month"]), "pnl": round(_safe_float(r["pnl"]), 4)} for _, r in agg.iterrows()][-36:]


def _symbol_stats(trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if trades_df.empty:
        return []
    rows = []
    for symbol, grp in trades_df.groupby("symbol"):
        gross_profit = grp.loc[grp["pnl"] > 0, "pnl"].sum()
        gross_loss = -grp.loc[grp["pnl"] < 0, "pnl"].sum()
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        rows.append({
            "symbol": symbol,
            "trades": int(len(grp)),
            "realized_pnl": round(_safe_float(grp["pnl"].sum()), 4),
            "win_rate_pct": round(float((grp["pnl"] > 0).mean() * 100.0), 2),
            "avg_trade_pnl": round(_safe_float(grp["pnl"].mean()), 4),
            "profit_factor": round(float(pf), 4),
            "avg_return_pct": round(_safe_float(grp["return_pct"].mean()), 4),
        })
    rows.sort(key=lambda x: x["realized_pnl"], reverse=True)
    return rows


def _reason_breakdown(trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if trades_df.empty:
        return []
    agg = trades_df.groupby("reason")["pnl"].agg(["count", "sum"]).reset_index()
    rows = []
    for _, r in agg.iterrows():
        rows.append({
            "reason": r["reason"] or "unknown",
            "count": int(r["count"]),
            "pnl": round(_safe_float(r["sum"]), 4),
        })
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


def _time_of_day_heatmap(trades_df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    if trades_df.empty:
        return {"hourly": [], "weekday": []}
    df = trades_df.dropna(subset=["exit_dt"]).copy()
    if df.empty:
        return {"hourly": [], "weekday": []}
    hourly = df.assign(hour=df["exit_dt"].dt.hour).groupby("hour", as_index=False)["pnl"].sum()
    weekday = df.assign(weekday=df["exit_dt"].dt.day_name()).groupby("weekday", as_index=False)["pnl"].sum()
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hourly_rows = [{"hour": int(r["hour"]), "pnl": round(_safe_float(r["pnl"]), 4)} for _, r in hourly.iterrows()]
    weekday_map = {str(r["weekday"]): round(_safe_float(r["pnl"]), 4) for _, r in weekday.iterrows()}
    weekday_rows = [{"weekday": name, "pnl": weekday_map.get(name, 0.0)} for name in weekday_order]
    return {"hourly": hourly_rows, "weekday": weekday_rows}


def _serialize_positions(positions: Dict[str, Dict[str, Any]], latest_prices: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for symbol, pos in (positions or {}).items():
        mark = _safe_float(latest_prices.get(symbol), _safe_float(pos.get("entry_price")))
        entry = _safe_float(pos.get("entry_price"))
        qty = _safe_float(pos.get("qty"))
        side = int(pos.get("side", 0))
        unreal = (mark - entry) * qty * side
        exposure = qty * mark
        rows.append({
            "symbol": symbol,
            "side": _fmt_side(side),
            "qty": round(qty, 6),
            "entry_price": round(entry, 6),
            "mark_price": round(mark, 6),
            "unrealized_pnl": round(unreal, 4),
            "exposure": round(exposure, 4),
            "entry_time": pos.get("entry_time"),
            "stop_price": round(_safe_float(pos.get("stop_price")), 6),
            "take_profit_price": round(_safe_float(pos.get("take_profit_price")), 6),
            "trail_price": round(_safe_float(pos.get("trail_price")), 6),
            "bars_held": int(pos.get("bars_held", 0) or 0),
        })
    rows.sort(key=lambda x: abs(x["unrealized_pnl"]), reverse=True)
    return rows


def _recent_actions(cycles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for cycle in cycles[-200:]:
        ran_at = cycle.get("ran_at")
        for action in cycle.get("actions") or []:
            rows.append({
                "time": ran_at,
                "symbol": action.get("symbol"),
                "action": action.get("action"),
                "side": _fmt_side(action.get("side", 0)) if action.get("side") is not None else "-",
                "price": round(_safe_float(action.get("price")), 6) if action.get("price") is not None else None,
                "qty": round(_safe_float(action.get("qty")), 6) if action.get("qty") is not None else None,
                "reason": action.get("reason", ""),
                "pnl": round(_safe_float(action.get("pnl")), 4) if action.get("pnl") is not None else None,
            })
        for exit_row in cycle.get("exits") or []:
            rows.append({
                "time": ran_at,
                "symbol": exit_row.get("symbol"),
                "action": "auto_exit",
                "side": "-",
                "price": round(_safe_float(exit_row.get("exit_price")), 6),
                "qty": None,
                "reason": exit_row.get("reason", ""),
                "pnl": round(_safe_float(exit_row.get("pnl")), 4),
            })
    rows.sort(key=lambda x: x.get("time") or "")
    return rows[-100:][::-1]


def _recent_signals(last_cycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for sig in last_cycle.get("signals") or []:
        rows.append({
            "symbol": sig.get("symbol"),
            "signal": _fmt_side(sig.get("desired_signal", 0)),
            "score": round(_safe_float(sig.get("ensemble_score")), 4),
            "confidence": round(_safe_float(sig.get("confidence")), 4),
            "price": round(_safe_float(sig.get("close")), 6),
            "notional_fraction": round(_safe_float(sig.get("notional_fraction")), 4),
            "regime": sig.get("regime", ""),
            "timestamp": sig.get("timestamp"),
        })
    rows.sort(key=lambda x: abs(x["score"]), reverse=True)
    return rows


def _optimization_history(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for row in logs[-100:]:
        metrics = row.get("metrics") or {}
        rows.append({
            "ran_at": row.get("ran_at") or row.get("time") or row.get("generated_at"),
            "objective": round(_safe_float(row.get("objective") or row.get("best_objective")), 4),
            "promoted": bool(row.get("promoted")),
            "improvement_pct": round(_safe_float(row.get("improvement_pct")), 4),
            "trade_count": int(metrics.get("trade_count", 0) or 0),
            "return_pct": round(_safe_float(metrics.get("total_return_pct")), 4),
            "max_drawdown_pct": round(_safe_float(metrics.get("max_drawdown_pct")), 4),
            "sharpe": round(_safe_float(metrics.get("sharpe")), 4),
        })
    rows.sort(key=lambda x: x.get("ran_at") or "")
    return rows[::-1]


def build_dashboard_payload(store: StateStore, settings: Dict[str, Any] | None = None) -> Dict[str, Any]:
    settings = settings or {}
    starting_equity = _safe_float(settings.get("paper_starting_equity"), 100000.0)
    paper_pf = store.read_json("paper_portfolio.json", default={}) or {}
    last_cycle = store.read_json("runtime", "last_trading_cycle.json", default={}) or {}
    last_opt = store.read_json("runtime", "last_optimization_cycle.json", default={}) or {}
    champion = store.read_json("champion_config.json", default={}) or {}
    universe_snapshot = store.read_json("runtime", "universe_snapshot.json", default={}) or {}
    cycles = store.read_jsonl("runtime", "trading_cycle_log.jsonl", limit=5000)
    opt_logs = store.read_jsonl("runtime", "optimization_cycle_log.jsonl", limit=1000)

    latest_prices = last_cycle.get("latest_prices") or {}
    positions = paper_pf.get("positions") or last_cycle.get("open_positions") or {}
    trades = paper_pf.get("trades") or []
    trades_df = _build_trade_frame(trades)
    open_positions = _serialize_positions(positions, latest_prices)
    unrealized_pnl = round(sum(x["unrealized_pnl"] for x in open_positions), 4)
    cash = _safe_float(paper_pf.get("cash"), starting_equity)
    current_equity = _safe_float(last_cycle.get("equity"), cash + unrealized_pnl)
    realized_pnl = round(_safe_float(trades_df["pnl"].sum()) if not trades_df.empty else 0.0, 4)
    total_pnl = round(current_equity - starting_equity, 4)
    total_return_pct = round((current_equity / starting_equity - 1.0) * 100.0, 4) if starting_equity else 0.0

    equity_curve = _equity_curve_from_cycles(cycles, starting_equity, trades_df)
    equity_series = pd.Series([_safe_float(p["equity"], starting_equity) for p in equity_curve])
    current_dd, max_dd = _compute_drawdown(equity_series)

    win_rate = float((trades_df["pnl"] > 0).mean() * 100.0) if not trades_df.empty else 0.0
    gross_profit = _safe_float(trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum()) if not trades_df.empty else 0.0
    gross_loss = -_safe_float(trades_df.loc[trades_df["pnl"] < 0, "pnl"].sum()) if not trades_df.empty else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    avg_trade_pnl = _safe_float(trades_df["pnl"].mean()) if not trades_df.empty else 0.0
    avg_trade_return_pct = _safe_float(trades_df["return_pct"].mean()) if not trades_df.empty else 0.0
    best_trade = _safe_float(trades_df["pnl"].max()) if not trades_df.empty else 0.0
    worst_trade = _safe_float(trades_df["pnl"].min()) if not trades_df.empty else 0.0
    avg_holding_hours = _safe_float(trades_df["holding_hours"].mean()) if not trades_df.empty else 0.0
    long_count = int((trades_df["side"] == 1).sum()) if not trades_df.empty else 0
    short_count = int((trades_df["side"] == -1).sum()) if not trades_df.empty else 0
    action_log = _recent_actions(cycles)
    opt_history = _optimization_history(opt_logs)

    day_pnl = _daily_pnl(trades_df)
    month_pnl = _monthly_pnl(trades_df)
    symbol_breakdown = _symbol_stats(trades_df)
    reason_breakdown = _reason_breakdown(trades_df)
    temporal_breakdown = _time_of_day_heatmap(trades_df)
    universe_members = universe_snapshot.get("members") or []
    universe_rankings = last_cycle.get("universe_rankings") or []

    summary = {
        "starting_equity": round(starting_equity, 4),
        "current_equity": round(current_equity, 4),
        "cash": round(cash, 4),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "current_drawdown_pct": current_dd,
        "max_drawdown_pct": max_dd,
        "closed_trades": int(len(trades_df)),
        "open_positions": int(len(open_positions)),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(float(profit_factor), 4),
        "avg_trade_pnl": round(avg_trade_pnl, 4),
        "avg_trade_return_pct": round(avg_trade_return_pct, 4),
        "best_trade": round(best_trade, 4),
        "worst_trade": round(worst_trade, 4),
        "avg_holding_hours": round(avg_holding_hours, 2),
        "long_trades": long_count,
        "short_trades": short_count,
        "trading_cycles": len(cycles),
        "optimization_runs": len(opt_logs),
        "last_cycle_at": last_cycle.get("ran_at"),
        "last_optimization_at": last_opt.get("ran_at") or last_opt.get("generated_at"),
        "universe_selected": int(universe_snapshot.get("selected_count") or len(universe_members)),
        "universe_loaded": int(universe_snapshot.get("loaded_count") or len(last_cycle.get("universe", {}).get("symbols", []))),
    }

    recent_trades = []
    if not trades_df.empty:
        for _, row in trades_df.sort_values("exit_dt", ascending=False).head(100).iterrows():
            recent_trades.append({
                "symbol": row["symbol"],
                "side": _fmt_side(row["side"]),
                "entry_time": row["entry_time"],
                "exit_time": row["exit_time"],
                "entry_price": round(_safe_float(row["entry_price"]), 6),
                "exit_price": round(_safe_float(row["exit_price"]), 6),
                "qty": round(_safe_float(row["qty"]), 6),
                "pnl": round(_safe_float(row["pnl"]), 4),
                "return_pct": round(_safe_float(row["return_pct"]), 4),
                "holding_hours": round(_safe_float(row["holding_hours"]), 2),
                "reason": row["reason"],
            })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "equity_curve": equity_curve,
        "daily_pnl": day_pnl,
        "monthly_pnl": month_pnl,
        "symbol_breakdown": symbol_breakdown,
        "reason_breakdown": reason_breakdown,
        "temporal_breakdown": temporal_breakdown,
        "recent_trades": recent_trades,
        "open_positions": open_positions,
        "recent_actions": action_log,
        "recent_signals": _recent_signals(last_cycle),
        "optimization_history": opt_history,
        "last_cycle": last_cycle,
        "last_optimization": last_opt,
        "champion": champion,
        "universe": {
            "selection_mode": universe_snapshot.get("selection_mode"),
            "target_size": universe_snapshot.get("target_size"),
            "selected_count": universe_snapshot.get("selected_count"),
            "loaded_count": universe_snapshot.get("loaded_count"),
            "updated_at": universe_snapshot.get("updated_at"),
            "members": universe_members,
            "rankings": universe_rankings,
        },
    }
    return payload
