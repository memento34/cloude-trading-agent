from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from ..portfolio import compute_position_size
from ..strategies import build_ensemble_frame


@dataclass
class SignalSnapshot:
    symbol: str
    timestamp: str
    desired_signal: int
    ensemble_score: float
    confidence: float
    regime: int
    close: float
    atr: float
    notional_fraction: float
    stop_atr_mult: float
    take_profit_rr: float


class LiveSignalEngine:
    def __init__(self, config: Dict):
        self.config = config

    def build_frames(self, market: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        return {symbol: build_ensemble_frame(df, self.config["ensemble"], self.config["regime"]) for symbol, df in market.items()}

    def generate(self, market: Dict[str, pd.DataFrame], equity: float) -> List[SignalSnapshot]:
        frames = self.build_frames(market)
        portfolio_cfg = self.config["portfolio"]
        ranked: List[SignalSnapshot] = []
        for symbol, frame in frames.items():
            row = frame.iloc[-1]
            close = float(row["close"])
            atr_value = max(float(row["atr"]), 1e-9)
            qty = compute_position_size(
                equity=equity,
                entry_price=close,
                atr_value=atr_value,
                risk_per_trade=portfolio_cfg["risk_per_trade"],
                stop_atr_mult=portfolio_cfg["stop_atr_mult"],
                max_symbol_exposure=portfolio_cfg["max_symbol_exposure"],
            )
            notional_fraction = (qty * close) / max(equity, 1e-9)
            ranked.append(
                SignalSnapshot(
                    symbol=symbol,
                    timestamp=str(row["timestamp"]),
                    desired_signal=int(row["desired_signal"]),
                    ensemble_score=float(row["ensemble_score"]),
                    confidence=float(abs(row["ensemble_score"])),
                    regime=int(row["regime"]),
                    close=close,
                    atr=atr_value,
                    notional_fraction=min(notional_fraction, portfolio_cfg["max_symbol_exposure"]),
                    stop_atr_mult=float(portfolio_cfg["stop_atr_mult"]),
                    take_profit_rr=float(portfolio_cfg["take_profit_rr"]),
                )
            )
        ranked.sort(key=lambda x: abs(x.ensemble_score), reverse=True)
        return ranked
