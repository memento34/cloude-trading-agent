from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

import pandas as pd

from .backtester import BacktestEngine
from .optimizer import AdaptiveOptimizer
from .performance import compute_metrics
from .types import Trade, WalkForwardResult, WalkForwardWindow


class WalkForwardRunner:
    def __init__(self, config: Dict):
        self.config = deepcopy(config)
        self.wf_cfg = self.config["walkforward"]

    def _slice_market(self, market: Dict[str, pd.DataFrame], start: int, end: int) -> Dict[str, pd.DataFrame]:
        return {symbol: df.iloc[start:end].reset_index(drop=True) for symbol, df in market.items()}

    def run(self, market: Dict[str, pd.DataFrame]) -> WalkForwardResult:
        n = min(len(df) for df in market.values())
        train_bars = self.wf_cfg["train_bars"]
        test_bars = self.wf_cfg["test_bars"]
        step = self.wf_cfg["step_bars"]

        all_trades: List[Trade] = []
        eq_parts = []
        windows: List[WalkForwardWindow] = []
        start = 0

        while start + train_bars + test_bars <= n:
            train_start, train_end = start, start + train_bars
            test_start, test_end = train_end, train_end + test_bars
            train_market = self._slice_market(market, train_start, train_end)
            test_market = self._slice_market(market, test_start, test_end)

            optimizer = AdaptiveOptimizer(
                base_config=self.config,
                seed=self.config.get("seed", 42) + start,
                candidates=self.wf_cfg["optimizer_candidates"],
                validation_split=self.wf_cfg["validation_split"],
            )
            best = optimizer.optimize(train_market)
            test_result = BacktestEngine(best.config).run(test_market)

            all_trades.extend(test_result.trades)
            part = test_result.equity_curve.copy()
            part["window_start_bar"] = start
            eq_parts.append(part)

            first_symbol = list(market.keys())[0]
            train_df = market[first_symbol].iloc[train_start:train_end]
            test_df = market[first_symbol].iloc[test_start:test_end]
            windows.append(
                WalkForwardWindow(
                    train_start=str(train_df.iloc[0]["timestamp"]),
                    train_end=str(train_df.iloc[-1]["timestamp"]),
                    test_start=str(test_df.iloc[0]["timestamp"]),
                    test_end=str(test_df.iloc[-1]["timestamp"]),
                    best_score=float(best.objective),
                    best_config=best.config,
                    test_metrics=test_result.metrics,
                )
            )
            start += step

        equity_curve = pd.concat(eq_parts, ignore_index=True) if eq_parts else pd.DataFrame(columns=["timestamp", "equity"])
        metrics = compute_metrics(equity_curve, all_trades, self.config["portfolio"]["starting_equity"])
        return WalkForwardResult(
            windows=windows,
            aggregate_metrics=metrics,
            equity_curve=equity_curve,
            trades=all_trades,
        )
