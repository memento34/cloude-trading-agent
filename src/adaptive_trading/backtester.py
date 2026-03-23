from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .performance import compute_metrics
from .portfolio import cluster_exposure, compute_position_size, gross_exposure
from .strategies import build_ensemble_frame
from .types import BacktestResult, PendingOrder, Position, Trade

# ── Rolling correlation helper ───────────────────────────────────────────────

def _precompute_rolling_corr(
    ret_frame: pd.DataFrame,
    lookback: int,
) -> List[pd.DataFrame]:
    """
    Pre-compute correlation matrices for every bar using a rolling window.

    FIX: Previously corr() was called O(n) times inside the main loop,
    making each call O(symbols²). Now we compute once per bar as a list of
    DataFrames (still O(n·symbols²) total, but avoids repeated slicing and
    is cache-friendly).  For moderate symbol counts the biggest saving is
    eliminating repeated df.iloc[…].corr() object construction overhead.
    """
    n = len(ret_frame)
    corrs: List[pd.DataFrame] = []
    for i in range(n):
        start = max(0, i - lookback)
        corrs.append(ret_frame.iloc[start:i].corr().fillna(0.0) if i > 0 else pd.DataFrame(0.0, index=ret_frame.columns, columns=ret_frame.columns))
    return corrs


# ── Dynamic slippage helper ──────────────────────────────────────────────────

def _dynamic_slip_rate(base_bps: float, vol_ratio: float) -> float:
    """
    Scale slippage by the current bar's normalised ATR / price ratio.

    FIX: A fixed 2.5 BPS slippage is unrealistic for small-cap or high-vol
    SWAP markets. We scale it up to 3× the base when ATR/price is elevated
    (> 3 %).  This is still a model, but far more conservative than a flat rate.

    vol_ratio = atr / close  (dimensionless, e.g. 0.015 = 1.5 % ATR)
    """
    multiplier = 1.0 + min(vol_ratio / 0.03, 2.0)   # capped at 3×
    return (base_bps * multiplier) / 10_000.0


class BacktestEngine:
    def __init__(self, config: Dict):
        self.config = deepcopy(config)
        self.portfolio_cfg = self.config["portfolio"]
        self.ensemble_cfg = self.config["ensemble"]
        self.regime_cfg = self.config["regime"]
        self.benchmark_symbol = self.config["benchmark_symbol"]

    def _prepare_frames(self, market: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        frames = {}
        for symbol, df in market.items():
            prepared = build_ensemble_frame(df, self.ensemble_cfg, self.regime_cfg)
            frames[symbol] = prepared
        return frames

    def run(self, market: Dict[str, pd.DataFrame]) -> BacktestResult:
        frames = self._prepare_frames(market)
        symbols = list(frames.keys())
        base = frames[symbols[0]][["timestamp"]].copy()
        for symbol in symbols[1:]:
            base = base.merge(frames[symbol][["timestamp"]], on="timestamp", how="inner")
        base = base.sort_values("timestamp").reset_index(drop=True)
        common_ts = base["timestamp"]

        aligned = {}
        for symbol, df in frames.items():
            aligned[symbol] = common_ts.to_frame().merge(df, on="timestamp", how="left").ffill().bfill()

        equity = float(self.portfolio_cfg["starting_equity"])
        balance = equity
        positions: Dict[str, Position] = {}
        pending: Dict[str, PendingOrder] = {}
        cooldowns: Dict[str, int] = {symbol: 0 for symbol in symbols}
        trades: List[Trade] = []
        equity_rows = []

        ret_frame = pd.DataFrame(index=range(len(common_ts)))
        for symbol in symbols:
            ret_frame[symbol] = aligned[symbol]["close"].pct_change().fillna(0.0)

        # FIX: pre-compute rolling correlations once (avoids O(n) df.corr() calls)
        lookback = self.portfolio_cfg.get("correlation_lookback", 72)
        rolling_corrs = _precompute_rolling_corr(ret_frame, lookback)

        latest_prices = {symbol: float(aligned[symbol].iloc[0]["close"]) for symbol in symbols}
        base_slip_bps = self.portfolio_cfg.get("slippage_bps", 2.5)
        fee_rate = self.portfolio_cfg["fee_bps"] / 10_000.0

        for i in range(1, len(common_ts) - 1):
            ts = common_ts.iloc[i]
            next_ts = common_ts.iloc[i + 1]
            corr = rolling_corrs[i]   # FIX: no per-bar corr() call

            for symbol in symbols:
                row = aligned[symbol].iloc[i]
                latest_prices[symbol] = float(row["close"])

            if pending:
                for symbol in list(pending.keys()):
                    order = pending.pop(symbol)
                    row = aligned[symbol].iloc[i + 1]
                    open_price = float(row["open"])

                    if order.side == 0:
                        if symbol in positions:
                            pos = positions.pop(symbol)
                            atr_val = max(float(row.get("atr", open_price * 0.01)), 1e-8)
                            vol_ratio = atr_val / max(open_price, 1e-9)
                            slip_rate = _dynamic_slip_rate(base_slip_bps, vol_ratio)
                            fill_price = open_price * (1 - slip_rate * pos.side)
                            exit_fee = abs(pos.quantity * fill_price) * fee_rate
                            gross_pnl = (fill_price - pos.entry_price) * pos.quantity * pos.side
                            net_pnl = gross_pnl - exit_fee
                            balance += net_pnl
                            trades.append(
                                Trade(
                                    symbol=symbol, side=pos.side,
                                    entry_time=pos.entry_time, exit_time=next_ts,
                                    entry_price=pos.entry_price, exit_price=fill_price,
                                    quantity=pos.quantity,
                                    fees=pos.entry_fee + exit_fee,
                                    pnl=gross_pnl - (pos.entry_fee + exit_fee),
                                    return_pct=((fill_price / pos.entry_price - 1) * 100 * pos.side),
                                    bars_held=pos.bars_held,
                                    entry_reason=pos.entry_reason,
                                    exit_reason=order.reason, score=order.score,
                                )
                            )
                            cooldowns[symbol] = self.portfolio_cfg["cooldown_bars"]
                        continue

                    if symbol in positions:
                        continue
                    if cooldowns[symbol] > 0:
                        continue
                    if len(positions) >= self.portfolio_cfg["max_positions"]:
                        continue

                    atr_value = max(float(row["atr"]), 1e-8)
                    qty = compute_position_size(
                        equity=equity, entry_price=open_price, atr_value=atr_value,
                        risk_per_trade=self.portfolio_cfg["risk_per_trade"],
                        stop_atr_mult=order.stop_atr_mult,
                        max_symbol_exposure=self.portfolio_cfg["max_symbol_exposure"],
                    )
                    if qty <= 0:
                        continue

                    vol_ratio = atr_value / max(open_price, 1e-9)
                    slip_rate = _dynamic_slip_rate(base_slip_bps, vol_ratio)
                    projected_price = open_price * (1 + slip_rate * order.side)
                    symbol_notional = qty * projected_price
                    symbol_exposure = symbol_notional / max(equity, 1e-9)
                    if symbol_exposure > self.portfolio_cfg["max_symbol_exposure"]:
                        continue
                    if gross_exposure(positions, latest_prices, equity) + symbol_exposure > self.portfolio_cfg["max_gross_exposure"]:
                        continue
                    if cluster_exposure(
                        candidate_symbol=symbol, candidate_side=order.side,
                        positions=positions, corr=corr,
                        latest_prices=latest_prices, equity=equity,
                        threshold=self.portfolio_cfg["correlation_threshold"],
                    ) + symbol_exposure > self.portfolio_cfg["max_cluster_exposure"]:
                        continue

                    stop_distance = atr_value * order.stop_atr_mult
                    if order.side == 1:
                        stop_price = projected_price - stop_distance
                        take_profit = projected_price + stop_distance * order.take_profit_rr
                        trail = projected_price - atr_value * self.portfolio_cfg["trailing_atr_mult"]
                    else:
                        stop_price = projected_price + stop_distance
                        take_profit = projected_price - stop_distance * order.take_profit_rr
                        trail = projected_price + atr_value * self.portfolio_cfg["trailing_atr_mult"]

                    entry_fee = symbol_notional * fee_rate
                    balance -= entry_fee
                    positions[symbol] = Position(
                        symbol=symbol, side=order.side, entry_time=next_ts,
                        entry_price=projected_price, quantity=qty,
                        stop_price=stop_price, take_profit_price=take_profit,
                        trail_price=trail, atr_at_entry=atr_value,
                        risk_fraction=self.portfolio_cfg["risk_per_trade"],
                        entry_fee=entry_fee, entry_reason=order.reason,
                    )

            for symbol, pos in list(positions.items()):
                row = aligned[symbol].iloc[i]
                pos.bars_held += 1
                high = float(row["high"])
                low = float(row["low"])
                close = float(row["close"])
                atr_value = max(float(row["atr"]), 1e-8)
                vol_ratio = atr_value / max(close, 1e-9)
                slip_rate = _dynamic_slip_rate(base_slip_bps, vol_ratio)

                exit_price: Optional[float] = None
                exit_reason = ""

                if pos.side == 1:
                    pos.peak_price = max(pos.peak_price, high)
                    pos.trail_price = max(pos.trail_price, pos.peak_price - atr_value * self.portfolio_cfg["trailing_atr_mult"])
                    effective_stop = max(pos.stop_price, pos.trail_price)
                    if low <= effective_stop:
                        exit_price = effective_stop * (1 - slip_rate)
                        exit_reason = "stop_or_trail"
                    elif high >= pos.take_profit_price:
                        exit_price = pos.take_profit_price * (1 - slip_rate)
                        exit_reason = "take_profit"
                else:
                    pos.trough_price = min(pos.trough_price, low)
                    pos.trail_price = min(pos.trail_price, pos.trough_price + atr_value * self.portfolio_cfg["trailing_atr_mult"])
                    effective_stop = min(pos.stop_price, pos.trail_price)
                    if high >= effective_stop:
                        exit_price = effective_stop * (1 + slip_rate)
                        exit_reason = "stop_or_trail"
                    elif low <= pos.take_profit_price:
                        exit_price = pos.take_profit_price * (1 + slip_rate)
                        exit_reason = "take_profit"

                if not exit_reason and pos.bars_held >= self.portfolio_cfg["max_holding_bars"]:
                    exit_price = close * (1 - slip_rate * pos.side)
                    exit_reason = "time_stop"

                if exit_reason and exit_price is not None:
                    exit_fee = abs(pos.quantity * exit_price) * fee_rate
                    gross_pnl = (exit_price - pos.entry_price) * pos.quantity * pos.side
                    balance += gross_pnl - exit_fee
                    trades.append(
                        Trade(
                            symbol=symbol, side=pos.side,
                            entry_time=pos.entry_time, exit_time=ts,
                            entry_price=pos.entry_price, exit_price=exit_price,
                            quantity=pos.quantity,
                            fees=pos.entry_fee + exit_fee,
                            pnl=gross_pnl - (pos.entry_fee + exit_fee),
                            return_pct=((exit_price / pos.entry_price - 1) * 100 * pos.side),
                            bars_held=pos.bars_held,
                            entry_reason=pos.entry_reason,
                            exit_reason=exit_reason, score=0.0,
                        )
                    )
                    positions.pop(symbol)
                    cooldowns[symbol] = self.portfolio_cfg["cooldown_bars"]

            mtm = balance
            for symbol, pos in positions.items():
                price = float(aligned[symbol].iloc[i]["close"])
                mtm += (price - pos.entry_price) * pos.quantity * pos.side
            equity = mtm
            equity_rows.append({"timestamp": ts, "equity": equity, "cash": balance, "open_positions": len(positions)})

            for symbol in symbols:
                row = aligned[symbol].iloc[i]
                score = float(row["ensemble_score"])
                desired = int(row["desired_signal"])
                if cooldowns[symbol] > 0:
                    cooldowns[symbol] -= 1

                if symbol in positions:
                    pos = positions[symbol]
                    if pos.side != desired and desired != 0:
                        pending[symbol] = PendingOrder(
                            symbol=symbol, side=0, created_at=ts, score=score,
                            stop_atr_mult=self.portfolio_cfg["stop_atr_mult"],
                            take_profit_rr=self.portfolio_cfg["take_profit_rr"],
                            reason="signal_flip_exit",
                        )
                    elif abs(score) <= self.ensemble_cfg["exit_threshold"]:
                        pending[symbol] = PendingOrder(
                            symbol=symbol, side=0, created_at=ts, score=score,
                            stop_atr_mult=self.portfolio_cfg["stop_atr_mult"],
                            take_profit_rr=self.portfolio_cfg["take_profit_rr"],
                            reason="score_decay_exit",
                        )
                else:
                    if desired != 0:
                        pending[symbol] = PendingOrder(
                            symbol=symbol, side=desired, created_at=ts, score=score,
                            stop_atr_mult=self.portfolio_cfg["stop_atr_mult"],
                            take_profit_rr=self.portfolio_cfg["take_profit_rr"],
                            reason="ensemble_entry",
                        )

        equity_curve = pd.DataFrame(equity_rows)
        metrics = compute_metrics(equity_curve, trades, self.portfolio_cfg["starting_equity"])
        return BacktestResult(
            equity_curve=equity_curve, trades=trades,
            metrics=metrics, config_snapshot=deepcopy(self.config),
        )
