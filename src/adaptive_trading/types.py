from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class PendingOrder:
    symbol: str
    side: int  # 1 long, -1 short, 0 exit
    created_at: pd.Timestamp
    score: float
    stop_atr_mult: float
    take_profit_rr: float
    reason: str


@dataclass
class Position:
    symbol: str
    side: int
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    stop_price: float
    take_profit_price: float
    trail_price: float
    atr_at_entry: float
    risk_fraction: float
    entry_fee: float = 0.0
    bars_held: int = 0
    entry_reason: str = ""
    peak_price: float = 0.0
    trough_price: float = 0.0

    def __post_init__(self) -> None:
        if self.side == 1:
            self.peak_price = self.entry_price
            self.trough_price = self.entry_price
        else:
            self.peak_price = self.entry_price
            self.trough_price = self.entry_price

    def market_value(self, price: float) -> float:
        return abs(self.quantity * price)

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.entry_price) * self.quantity * self.side


@dataclass
class Trade:
    symbol: str
    side: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    fees: float
    pnl: float
    return_pct: float
    bars_held: int
    entry_reason: str
    exit_reason: str
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: List[Trade]
    metrics: Dict[str, float]
    config_snapshot: Dict[str, Any]
    window_details: List[Dict[str, Any]] = field(default_factory=list)

    def save(self, path: str | pd.Path) -> None:  # type: ignore[attr-defined]
        from pathlib import Path
        import json

        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        self.equity_curve.to_csv(out / "equity_curve.csv", index=False)
        pd.DataFrame([t.to_dict() for t in self.trades]).to_csv(out / "trades.csv", index=False)
        (out / "metrics.json").write_text(json.dumps(self.metrics, indent=2, default=str))
        (out / "config_snapshot.json").write_text(json.dumps(self.config_snapshot, indent=2, default=str))
        if self.window_details:
            (out / "window_details.json").write_text(json.dumps(self.window_details, indent=2, default=str))


@dataclass
class WalkForwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_score: float
    best_config: Dict[str, Any]
    test_metrics: Dict[str, float]


@dataclass
class WalkForwardResult:
    windows: List[WalkForwardWindow]
    aggregate_metrics: Dict[str, float]
    equity_curve: pd.DataFrame
    trades: List[Trade]

    def save(self, path: str | pd.Path) -> None:  # type: ignore[attr-defined]
        from pathlib import Path
        import json

        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        self.equity_curve.to_csv(out / "equity_curve.csv", index=False)
        pd.DataFrame([t.to_dict() for t in self.trades]).to_csv(out / "trades.csv", index=False)
        (out / "aggregate_metrics.json").write_text(json.dumps(self.aggregate_metrics, indent=2, default=str))
        (out / "windows.json").write_text(
            json.dumps([
                {
                    "train_start": w.train_start,
                    "train_end": w.train_end,
                    "test_start": w.test_start,
                    "test_end": w.test_end,
                    "best_score": w.best_score,
                    "best_config": w.best_config,
                    "test_metrics": w.test_metrics,
                }
                for w in self.windows
            ], indent=2, default=str)
        )


@dataclass
class ReplayResult:
    promotions: List[Dict[str, Any]]
    equity_curve: pd.DataFrame
    trades: List[Trade]
    metrics: Dict[str, float]

    def summary_text(self) -> str:
        return (
            f"Final equity: {self.metrics.get('final_equity', 0):.2f}\n"
            f"Total return: {self.metrics.get('total_return_pct', 0):.2f}%\n"
            f"Max drawdown: {self.metrics.get('max_drawdown_pct', 0):.2f}%\n"
            f"Sharpe: {self.metrics.get('sharpe', 0):.2f}\n"
            f"Trades: {len(self.trades)}\n"
            f"Promotions: {len(self.promotions)}"
        )

    def save(self, path: str | pd.Path) -> None:  # type: ignore[attr-defined]
        from pathlib import Path
        import json

        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        self.equity_curve.to_csv(out / "equity_curve.csv", index=False)
        pd.DataFrame([t.to_dict() for t in self.trades]).to_csv(out / "trades.csv", index=False)
        (out / "metrics.json").write_text(json.dumps(self.metrics, indent=2, default=str))
        (out / "promotions.json").write_text(json.dumps(self.promotions, indent=2, default=str))
