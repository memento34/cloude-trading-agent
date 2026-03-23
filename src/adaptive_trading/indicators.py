from __future__ import annotations

import numpy as np
import pandas as pd


EPS = 1e-12


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    avg_up = up.ewm(alpha=1 / window, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_up / (avg_down + EPS)
    return 100 - (100 / (1 + rs))


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / window, adjust=False).mean()


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std(ddof=0)
    return (series - mean) / (std + EPS)


def donchian_high(series: pd.Series, window: int) -> pd.Series:
    return series.shift(1).rolling(window).max()


def donchian_low(series: pd.Series, window: int) -> pd.Series:
    return series.shift(1).rolling(window).min()


def volume_zscore(volume: pd.Series, window: int) -> pd.Series:
    return zscore(volume, window)


def realized_vol(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window).std(ddof=0) * np.sqrt(window)


def rolling_momentum(series: pd.Series, window: int) -> pd.Series:
    return series.pct_change(window)


def rolling_correlation_matrix(frame: pd.DataFrame, lookback: int) -> pd.DataFrame:
    return frame.tail(lookback).corr().fillna(0.0)
