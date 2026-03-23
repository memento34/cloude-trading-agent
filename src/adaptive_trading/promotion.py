from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

import pandas as pd

from .backtester import BacktestEngine
from .optimizer import AdaptiveOptimizer
from .performance import compute_metrics, objective_from_metrics
from .types import ReplayResult, Trade


class ContinuousPaperOptimizer:
    def __init__(self, config: Dict):
        self.base_config = deepcopy(config)
        self.ctrl_cfg = self.base_config["continuous_optimization"]

    def _slice_market(self, market: Dict[str, pd.DataFrame], start: int, end: int) -> Dict[str, pd.DataFrame]:
        return {symbol: df.iloc[start:end].reset_index(drop=True) for symbol, df in market.items()}

    def run_replay(self, market: Dict[str, pd.DataFrame]) -> ReplayResult:
        n = min(len(df) for df in market.values())
        lookback = self.ctrl_cfg["rolling_lookback_bars"]
        step = self.ctrl_cfg["reopt_every_bars"]
        starting_equity = self.base_config["portfolio"]["starting_equity"]

        champion = deepcopy(self.base_config)
        promotions: List[Dict] = []
        eq_parts = []
        all_trades: List[Trade] = []
        cursor = lookback
        last_equity = starting_equity

        while cursor < n:
            window_start = max(0, cursor - lookback)
            window_end = min(n, cursor + step)

            # History: strictly [window_start, cursor) — used only for optimisation
            history_market = self._slice_market(market, window_start, cursor)

            # FIX: Forward window starts at cursor (no overlap with history).
            # Previously it started at cursor-40, meaning the champion was
            # evaluated on 40 bars it had already trained on — a mini data
            # leakage. Now train and eval windows are strictly separated.
            forward_market = self._slice_market(market, cursor, window_end)

            # Skip windows that are too short to be meaningful
            fwd_len = min(len(df) for df in forward_market.values()) if forward_market else 0
            if fwd_len < 30:
                cursor += step
                continue

            champion_result = BacktestEngine(champion).run(forward_market)
            champion_score = objective_from_metrics(champion_result.metrics)
            challenger_cfg = champion

            needs_reopt = False
            if self.ctrl_cfg["enabled"]:
                dd = champion_result.metrics.get("max_drawdown_pct", 0.0) / 100.0
                if dd >= self.ctrl_cfg["drawdown_trigger"] or (cursor - lookback) % step == 0:
                    needs_reopt = True

            if needs_reopt:
                hist_len = min(len(df) for df in history_market.values()) if history_market else 0
                if hist_len >= 120:
                    optimizer = AdaptiveOptimizer(
                        base_config=self.base_config,
                        seed=self.base_config.get("seed", 42) + cursor,
                        candidates=self.ctrl_cfg["candidates"],
                        validation_split=self.base_config["walkforward"]["validation_split"],
                    )
                    challenger = optimizer.optimize(history_market, champion=champion)
                    challenger_cfg = challenger.config
                    # Evaluate challenger on the same forward window (post-cursor only)
                    challenger_forward = BacktestEngine(challenger_cfg).run(forward_market)
                    challenger_score = objective_from_metrics(challenger_forward.metrics)
                    if challenger_score > champion_score * (1 + self.ctrl_cfg["min_improvement"]):
                        champion = challenger_cfg
                        promotions.append({
                            "bar_index": int(cursor),
                            "promotion_reason": "objective_improved",
                            "old_score": champion_score,
                            "new_score": challenger_score,
                        })
                        champion_result = challenger_forward

            eq = champion_result.equity_curve.copy()
            eq["segment_end_bar"] = cursor
            eq_parts.append(eq)
            all_trades.extend(champion_result.trades)
            last_equity = champion_result.metrics.get("final_equity", last_equity)
            cursor += step

        equity_curve = (pd.concat(eq_parts, ignore_index=True)
                        if eq_parts else pd.DataFrame(columns=["timestamp", "equity"]))
        metrics = compute_metrics(equity_curve, all_trades, starting_equity)
        metrics["final_equity"] = last_equity
        return ReplayResult(promotions=promotions, equity_curve=equity_curve,
                            trades=all_trades, metrics=metrics)
