from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from .indicators import atr, donchian_high, donchian_low, ema, realized_vol, rolling_momentum, rsi, volume_zscore, zscore


REGIME_BULL = 1
REGIME_BEAR = -1
REGIME_CHOP = 0


def infer_regime(df: pd.DataFrame, regime_cfg: Dict) -> pd.Series:
    fast = ema(df["close"], regime_cfg["fast"])
    slow = ema(df["close"], regime_cfg["slow"])
    slope = slow.pct_change(10)
    vol = realized_vol(df["close"].pct_change().fillna(0.0), regime_cfg["vol_window"])

    regime = pd.Series(REGIME_CHOP, index=df.index, dtype=float)
    bull = (fast > slow) & (slope > 0)
    bear = (fast < slow) & (slope < 0)
    regime[bull] = REGIME_BULL
    regime[bear] = REGIME_BEAR
    regime[vol > regime_cfg["vol_cutoff"]] = REGIME_CHOP
    return regime.fillna(REGIME_CHOP)


def _normalize_signal(x: pd.Series) -> pd.Series:
    return x.clip(-1.0, 1.0).fillna(0.0)


def trend_sleeve(df: pd.DataFrame, cfg: Dict, regime: pd.Series) -> pd.DataFrame:
    fast = ema(df["close"], cfg["ema_fast"])
    slow = ema(df["close"], cfg["ema_slow"])
    mom = rolling_momentum(df["close"], cfg["momentum_window"])
    strength = (fast - slow) / slow
    score = 0.55 * np.tanh(strength * 100) + 0.45 * np.tanh(mom.fillna(0.0) * 12)
    score = pd.Series(score, index=df.index)
    score[(regime == REGIME_BEAR) & (score > 0)] *= 0.35
    score[(regime == REGIME_BULL) & (score < 0)] *= 0.35
    signal = pd.Series(0, index=df.index)
    signal[score >= cfg["strength_threshold"]] = 1
    signal[score <= -cfg["strength_threshold"]] = -1
    return pd.DataFrame({"score": _normalize_signal(score), "signal": signal})


def mean_reversion_sleeve(df: pd.DataFrame, cfg: Dict, regime: pd.Series) -> pd.DataFrame:
    z = zscore(df["close"], cfg["lookback"])
    r = rsi(df["close"], cfg["rsi_window"])
    long_cond = (z <= -cfg["z_entry"]) & (r <= cfg["rsi_oversold"]) & (regime != REGIME_BEAR)
    short_cond = (z >= cfg["z_entry"]) & (r >= cfg["rsi_overbought"]) & (regime != REGIME_BULL)
    score = -z / max(cfg["z_entry"], 1e-6)
    score[regime == REGIME_BULL] = score[regime == REGIME_BULL].clip(lower=-0.6)
    score[regime == REGIME_BEAR] = score[regime == REGIME_BEAR].clip(upper=0.6)
    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return pd.DataFrame({"score": _normalize_signal(score), "signal": signal})


def breakout_sleeve(df: pd.DataFrame, cfg: Dict, regime: pd.Series) -> pd.DataFrame:
    upper = donchian_high(df["high"], cfg["channel_window"])
    lower = donchian_low(df["low"], cfg["channel_window"])
    v_z = volume_zscore(df["volume"], cfg["volume_window"])
    local_atr = atr(df)
    atr_accel = local_atr.pct_change().fillna(0.0)

    long_cond = (df["close"] > upper) & (v_z > cfg["volume_z_threshold"]) & (atr_accel > cfg["atr_expansion_threshold"])
    short_cond = (df["close"] < lower) & (v_z > cfg["volume_z_threshold"]) & (atr_accel > cfg["atr_expansion_threshold"])
    score = ((df["close"] - upper).fillna(0.0) - (lower - df["close"]).fillna(0.0)) / (local_atr + 1e-9)
    score[(regime == REGIME_BULL) & (score > 0)] *= 1.15
    score[(regime == REGIME_BEAR) & (score < 0)] *= 1.15
    score[(regime == REGIME_CHOP)] *= 0.7
    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return pd.DataFrame({"score": _normalize_signal(score / 3.0), "signal": signal})


def pullback_sleeve(df: pd.DataFrame, cfg: Dict, regime: pd.Series) -> pd.DataFrame:
    fast = ema(df["close"], cfg["ema_fast"])
    slow = ema(df["close"], cfg["ema_slow"])
    trend = np.sign((fast - slow).fillna(0.0))
    pullback = (df["close"] / fast - 1.0).rolling(cfg["pullback_window"]).min()
    local_rsi = rsi(df["close"], 14)

    long_cond = (trend > 0) & (df["close"] < fast) & (local_rsi > cfg["reentry_rsi"]) & (regime != REGIME_BEAR)
    short_cond = (trend < 0) & (df["close"] > fast) & (local_rsi < (100 - cfg["reentry_rsi"])) & (regime != REGIME_BULL)
    score = (fast - df["close"]) / (slow + 1e-9)
    score[trend < 0] = -((df["close"] - fast) / (slow + 1e-9))[trend < 0]
    score = score.fillna(0.0)
    score[regime == REGIME_CHOP] *= 0.6
    signal = pd.Series(0, index=df.index)
    signal[long_cond] = 1
    signal[short_cond] = -1
    return pd.DataFrame({"score": _normalize_signal(score * 30), "signal": signal})


def build_ensemble_frame(df: pd.DataFrame, cfg: Dict, regime_cfg: Dict) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    regime = infer_regime(df, regime_cfg)
    local_atr = atr(df, 14).bfill().ffill()

    sleeves_cfg = cfg["sleeves"]
    outputs = {}
    if sleeves_cfg["trend"]["enabled"]:
        outputs["trend"] = trend_sleeve(df, sleeves_cfg["trend"], regime)
    if sleeves_cfg["mean_reversion"]["enabled"]:
        outputs["mean_reversion"] = mean_reversion_sleeve(df, sleeves_cfg["mean_reversion"], regime)
    if sleeves_cfg["breakout"]["enabled"]:
        outputs["breakout"] = breakout_sleeve(df, sleeves_cfg["breakout"], regime)
    if sleeves_cfg["pullback"]["enabled"]:
        outputs["pullback"] = pullback_sleeve(df, sleeves_cfg["pullback"], regime)

    out = df.copy()
    weighted_score = pd.Series(0.0, index=df.index)
    weight_sum = 0.0
    for name, sleeve_df in outputs.items():
        w = sleeves_cfg[name]["weight"]
        out[f"{name}_score"] = sleeve_df["score"]
        out[f"{name}_signal"] = sleeve_df["signal"]
        weighted_score += sleeve_df["score"] * w
        weight_sum += w

    weighted_score = weighted_score / max(weight_sum, 1e-9)
    out["ensemble_score"] = weighted_score.clip(-1.0, 1.0)
    out["regime"] = regime
    out["atr"] = local_atr

    out["desired_signal"] = 0
    out.loc[out["ensemble_score"] >= cfg["entry_threshold"], "desired_signal"] = 1
    out.loc[out["ensemble_score"] <= -cfg["entry_threshold"], "desired_signal"] = -1
    if not cfg.get("allow_long", True):
        out.loc[out["desired_signal"] == 1, "desired_signal"] = 0
    if not cfg.get("allow_short", True):
        out.loc[out["desired_signal"] == -1, "desired_signal"] = 0
    return out
