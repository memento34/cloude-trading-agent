from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

import pandas as pd


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def load_symbol_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in {path}: {missing}")
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp")
    return df.reset_index(drop=True)


def load_symbol_csvs(folder: str | Path, symbols: Iterable[str]) -> Dict[str, pd.DataFrame]:
    folder = Path(folder)
    market = {}
    for symbol in symbols:
        market[symbol] = load_symbol_csv(folder / f"{symbol}_1h.csv")
    return market
