from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Optional

import optuna

from .backtester import BacktestEngine
from .performance import objective_from_metrics

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class CandidateResult:
    config: Dict
    objective: float
    metrics: Dict


def _build_config_from_trial(trial: optuna.Trial, base_config: Dict) -> Dict:
    out = deepcopy(base_config)
    sleeves = out["ensemble"]["sleeves"]

    raw = [trial.suggest_float(f"w_{k}", 0.05, 1.0)
           for k in ("trend", "mean_reversion", "breakout", "pullback")]
    total = sum(raw)
    for k, v in zip(("trend", "mean_reversion", "breakout", "pullback"), raw):
        sleeves[k]["weight"] = round(v / total, 4)

    sleeves["trend"]["ema_fast"] = trial.suggest_int("trend_ema_fast", 8, 34)
    sleeves["trend"]["ema_slow"] = trial.suggest_int("trend_ema_slow", 55, 160)
    sleeves["trend"]["momentum_window"] = trial.suggest_int("trend_mom_win", 8, 40)
    sleeves["trend"]["strength_threshold"] = trial.suggest_float("trend_strength", 0.001, 0.02, log=True)

    sleeves["mean_reversion"]["lookback"] = trial.suggest_int("mr_lookback", 20, 80)
    sleeves["mean_reversion"]["z_entry"] = trial.suggest_float("mr_z_entry", 1.1, 2.8)
    sleeves["mean_reversion"]["z_exit"] = trial.suggest_float("mr_z_exit", 0.2, 1.0)
    sleeves["mean_reversion"]["rsi_oversold"] = trial.suggest_int("mr_rsi_os", 20, 40)
    sleeves["mean_reversion"]["rsi_overbought"] = trial.suggest_int("mr_rsi_ob", 60, 80)

    sleeves["breakout"]["channel_window"] = trial.suggest_int("bo_chan_win", 12, 60)
    sleeves["breakout"]["volume_window"] = trial.suggest_int("bo_vol_win", 8, 36)
    sleeves["breakout"]["volume_z_threshold"] = trial.suggest_float("bo_vol_z", 0.0, 1.8)
    sleeves["breakout"]["atr_expansion_threshold"] = trial.suggest_float("bo_atr_exp", -0.05, 0.15)

    sleeves["pullback"]["ema_fast"] = trial.suggest_int("pb_ema_fast", 8, 34)
    sleeves["pullback"]["ema_slow"] = trial.suggest_int("pb_ema_slow", 30, 100)
    sleeves["pullback"]["pullback_window"] = trial.suggest_int("pb_win", 3, 14)
    sleeves["pullback"]["reentry_rsi"] = trial.suggest_int("pb_rsi", 45, 60)

    out["ensemble"]["entry_threshold"] = trial.suggest_float("entry_thr", 0.22, 0.70)
    out["ensemble"]["exit_threshold"] = trial.suggest_float("exit_thr", 0.03, 0.18)

    out["portfolio"]["risk_per_trade"] = trial.suggest_float("risk_per_trade", 0.003, 0.015, log=True)
    out["portfolio"]["max_positions"] = trial.suggest_int("max_pos", 2, 6)
    out["portfolio"]["max_gross_exposure"] = trial.suggest_float("max_gross_exp", 1.0, 3.0)
    out["portfolio"]["max_symbol_exposure"] = trial.suggest_float("max_sym_exp", 0.25, 0.85)
    out["portfolio"]["max_cluster_exposure"] = trial.suggest_float("max_clus_exp", 0.55, 1.65)
    out["portfolio"]["max_holding_bars"] = trial.suggest_int("max_hold_bars", 18, 144)
    out["portfolio"]["trailing_atr_mult"] = trial.suggest_float("trail_atr", 0.8, 2.5)
    out["portfolio"]["stop_atr_mult"] = trial.suggest_float("stop_atr", 0.9, 3.0)
    out["portfolio"]["take_profit_rr"] = trial.suggest_float("tp_rr", 1.1, 4.0)
    out["portfolio"]["cooldown_bars"] = trial.suggest_int("cooldown", 0, 10)
    out["portfolio"]["correlation_threshold"] = trial.suggest_float("corr_thr", 0.55, 0.90)
    return out


class AdaptiveOptimizer:
    """
    Bayesian hyper-parameter search (Optuna TPE) instead of pure random search.
    With the same candidate budget, TPE typically finds 5-10x better parameters
    because each trial is informed by all prior results.
    """

    def __init__(self, base_config: Dict, seed: int = 42,
                 candidates: int = 50, validation_split: float = 0.25):
        self.base_config = deepcopy(base_config)
        self.seed = seed
        self.candidates = candidates
        self.validation_split = validation_split

    def _slice_market(self, market: Dict, start: int, end: int) -> Dict:
        return {s: df.iloc[start:end].reset_index(drop=True) for s, df in market.items()}

    def _evaluate(self, cfg: Dict, market: Dict) -> CandidateResult:
        length = min(len(df) for df in market.values())
        split = max(int(length * (1 - self.validation_split)), 120)
        train_mkt = self._slice_market(market, 0, split)
        val_mkt = self._slice_market(market, split, length)   # strict split, no overlap

        engine = BacktestEngine(cfg)
        train_res = engine.run(train_mkt)
        val_res = engine.run(val_mkt)
        score = (objective_from_metrics(train_res.metrics) * 0.45
                 + objective_from_metrics(val_res.metrics) * 0.55)
        blended = deepcopy(val_res.metrics)
        blended["train_total_return_pct"] = train_res.metrics.get("total_return_pct", 0.0)
        return CandidateResult(config=cfg, objective=score, metrics=blended)

    def _extract_params_from_config(self, cfg: Dict) -> Dict:
        sleeves = cfg["ensemble"]["sleeves"]
        weights = {k: sleeves[k].get("weight", 0.25)
                   for k in ("trend", "mean_reversion", "breakout", "pullback")}
        total = sum(weights.values()) or 1.0
        params: Dict = {f"w_{k}": v / total for k, v in weights.items()}
        params.update({
            "trend_ema_fast": sleeves["trend"]["ema_fast"],
            "trend_ema_slow": sleeves["trend"]["ema_slow"],
            "trend_mom_win": sleeves["trend"]["momentum_window"],
            "trend_strength": sleeves["trend"]["strength_threshold"],
            "mr_lookback": sleeves["mean_reversion"]["lookback"],
            "mr_z_entry": sleeves["mean_reversion"]["z_entry"],
            "mr_z_exit": sleeves["mean_reversion"]["z_exit"],
            "mr_rsi_os": sleeves["mean_reversion"]["rsi_oversold"],
            "mr_rsi_ob": sleeves["mean_reversion"]["rsi_overbought"],
            "bo_chan_win": sleeves["breakout"]["channel_window"],
            "bo_vol_win": sleeves["breakout"]["volume_window"],
            "bo_vol_z": sleeves["breakout"]["volume_z_threshold"],
            "bo_atr_exp": sleeves["breakout"]["atr_expansion_threshold"],
            "pb_ema_fast": sleeves["pullback"]["ema_fast"],
            "pb_ema_slow": sleeves["pullback"]["ema_slow"],
            "pb_win": sleeves["pullback"]["pullback_window"],
            "pb_rsi": sleeves["pullback"]["reentry_rsi"],
            "entry_thr": cfg["ensemble"]["entry_threshold"],
            "exit_thr": cfg["ensemble"]["exit_threshold"],
            "risk_per_trade": cfg["portfolio"]["risk_per_trade"],
            "max_pos": cfg["portfolio"]["max_positions"],
            "max_gross_exp": cfg["portfolio"]["max_gross_exposure"],
            "max_sym_exp": cfg["portfolio"]["max_symbol_exposure"],
            "max_clus_exp": cfg["portfolio"]["max_cluster_exposure"],
            "max_hold_bars": cfg["portfolio"]["max_holding_bars"],
            "trail_atr": cfg["portfolio"]["trailing_atr_mult"],
            "stop_atr": cfg["portfolio"]["stop_atr_mult"],
            "tp_rr": cfg["portfolio"]["take_profit_rr"],
            "cooldown": cfg["portfolio"]["cooldown_bars"],
            "corr_thr": cfg["portfolio"]["correlation_threshold"],
        })
        return params

    def optimize(self, market: Dict, champion: Optional[Dict] = None) -> CandidateResult:
        sampler = optuna.samplers.TPESampler(seed=self.seed, n_startup_trials=5)
        study = optuna.create_study(direction="maximize", sampler=sampler)

        # Warm-start: enqueue champion as first trial so TPE anchors on it
        if champion is not None:
            try:
                study.enqueue_trial(self._extract_params_from_config(champion))
            except Exception:
                pass

        best_result: Optional[CandidateResult] = None

        def objective(trial: optuna.Trial) -> float:
            nonlocal best_result
            cfg = _build_config_from_trial(trial, self.base_config)
            result = self._evaluate(cfg, market)
            if best_result is None or result.objective > best_result.objective:
                best_result = result
            return result.objective

        study.optimize(objective, n_trials=self.candidates, show_progress_bar=False)
        assert best_result is not None
        logger.info("Optuna done: best=%.4f in %d trials", best_result.objective, self.candidates)
        return best_result
