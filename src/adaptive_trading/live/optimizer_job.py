from __future__ import annotations

from copy import deepcopy
from typing import Dict

from ..optimizer import AdaptiveOptimizer
from ..performance import objective_from_metrics
from ..walkforward import WalkForwardRunner
from .settings import ServiceSettings
from .state_store import StateStore, utc_now_iso


class OptimizerService:
    def __init__(self, base_config: Dict, settings: ServiceSettings, store: StateStore):
        self.base_config = deepcopy(base_config)
        self.settings = settings
        self.store = store

    def get_champion_config(self) -> Dict:
        champion = self.store.read_json("champion_config.json")
        if champion and isinstance(champion, dict) and champion.get("config"):
            return champion["config"]
        return deepcopy(self.base_config)

    def optimize_and_maybe_promote(self, market: Dict, runtime_config: Dict | None = None) -> Dict:
        cfg = deepcopy(runtime_config or self.get_champion_config())
        optimizer = AdaptiveOptimizer(
            base_config=cfg,
            seed=cfg.get("seed", 42),
            candidates=self.settings.optimizer_candidates,
            validation_split=cfg["walkforward"].get("validation_split", 0.25),
        )
        best = optimizer.optimize(market, champion=cfg)
        wf_runner = WalkForwardRunner(best.config)
        wf_result = wf_runner.run({k: v.tail(self.settings.optimize_lookback_bars).reset_index(drop=True) for k, v in market.items()})
        existing = self.store.read_json("champion_config.json", default={}) or {}
        existing_objective = float(existing.get("objective", -1e18))
        promote = best.objective >= existing_objective + self.settings.auto_promote_min_objective_improvement
        existing_wf_objective = objective_from_metrics(existing.get("walkforward_metrics", {})) if existing else -1e18
        new_wf_objective = objective_from_metrics(wf_result.aggregate_metrics)
        promote = promote or new_wf_objective > existing_wf_objective + 0.05

        payload = {
            "updated_at": utc_now_iso(),
            "objective": float(best.objective),
            "metrics": best.metrics,
            "walkforward_metrics": wf_result.aggregate_metrics,
            "config": best.config,
            "promoted": bool(promote),
        }
        self.store.write_json("optimizer", "last_optimization.json", payload=payload)
        if promote:
            self.store.write_json("champion_config.json", payload=payload)
        return payload
