from __future__ import annotations

import threading
from copy import deepcopy
from typing import Dict, List, Tuple

from ..config import load_config
from .market import MarketDataService
from .optimizer_job import OptimizerService
from .settings import ServiceSettings
from .signal_engine import LiveSignalEngine
from .state_store import StateStore, utc_now_iso
from .trader import LiveExecutor, PaperExecutor


class TradingServiceWorker:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.settings = ServiceSettings.from_env(root_dir)
        self.store = StateStore(self.settings.state_dir)
        self.base_config = load_config(self.settings.root_dir / "config" / "default.yaml")
        self.base_config["portfolio"]["starting_equity"] = self.settings.paper_starting_equity
        self.base_config["walkforward"]["optimizer_candidates"] = self.settings.optimizer_candidates
        self.market = MarketDataService(self.settings, self.store)
        self.optimizer = OptimizerService(self.base_config, self.settings, self.store)
        self.paper_executor = PaperExecutor(self.settings, self.store)
        self.live_executor = LiveExecutor(self.settings, self.store)
        self._trade_lock = threading.Lock()
        self._opt_lock = threading.Lock()

    def active_config(self) -> Dict:
        champion = self.store.read_json("champion_config.json")
        if champion and champion.get("config"):
            return deepcopy(champion["config"])
        return deepcopy(self.base_config)

    def _get_executor(self):
        return self.live_executor if self.settings.mode == "live" else self.paper_executor

    def _resolve_runtime_config(self, force_universe_refresh: bool = False) -> Tuple[Dict, Dict]:
        cfg = self.active_config()
        symbols, universe = self.market.resolve_symbols(force_refresh=force_universe_refresh)
        cfg["symbols"] = list(symbols)
        if symbols:
            cfg["benchmark_symbol"] = symbols[0]
        cfg["portfolio"]["starting_equity"] = self.settings.paper_starting_equity
        cfg["walkforward"]["optimizer_candidates"] = self.settings.optimizer_candidates
        return cfg, universe

    def _adapt_for_available_history(self, cfg: Dict, market: Dict) -> Dict:
        cfg = deepcopy(cfg)
        if not market:
            return cfg
        min_bars = min(len(df) for df in market.values())
        wf = cfg["walkforward"]
        train = min(int(wf.get("train_bars", 720)), max(min_bars - 80, 120))
        test = min(int(wf.get("test_bars", 240)), max(min(train // 3, min_bars // 4), 40))
        if train + test > min_bars:
            train = max(int(min_bars * 0.65), 120)
            test = max(int(min_bars * 0.2), 40)
        if train + test > min_bars:
            train = max(min_bars - 60, 80)
            test = max(min(40, min_bars // 4), 20)
        step = max(min(int(wf.get("step_bars", test)), test), 20)
        wf["train_bars"] = int(train)
        wf["test_bars"] = int(test)
        wf["step_bars"] = int(step)
        cfg["_available_history_bars"] = int(min_bars)
        return cfg

    def _top_signals(self, signals: List, max_positions: int, entry_threshold: float) -> List:
        actionable = [s for s in signals if s.desired_signal != 0 and abs(s.ensemble_score) >= entry_threshold]
        return actionable[:max_positions]

    def _rankings(self, signals: List, universe: Dict) -> List[Dict]:
        volume_map = {row.get("instId"): row for row in universe.get("members", [])}
        rows = []
        for rank, sig in enumerate(signals, start=1):
            vol_row = volume_map.get(sig.symbol, {})
            rows.append({
                "rank": rank,
                "symbol": sig.symbol,
                "signal": sig.desired_signal,
                "ensemble_score": float(sig.ensemble_score),
                "close": float(sig.close),
                "atr": float(sig.atr),
                "regime": int(sig.regime),
                "notional_fraction": float(sig.notional_fraction),
                "volume_rank": vol_row.get("rank"),
                "volCcy24h": float(vol_row.get("volCcy24h") or 0.0),
                "change24h_pct": float(vol_row.get("change24h_pct") or 0.0),
                "spread_bps": float(vol_row.get("spread_bps") or 0.0),
                "timestamp": sig.timestamp,
            })
        return rows

    def optimization_cycle(self) -> Dict:
        if not self._opt_lock.acquire(blocking=False):
            return {"ok": False, "message": "optimization already running"}
        try:
            cfg, universe = self._resolve_runtime_config(force_universe_refresh=True)
            min_bars = max(self.settings.optimizer_history_floor_bars, cfg["regime"]["slow"] + 30)
            market = self.market.get_market(cfg["symbols"], min_bars=min_bars)
            market = {k: v for k, v in market.items() if len(v) >= self.settings.optimizer_history_floor_bars}
            if len(market) < self.settings.optimization_min_symbols:
                return {
                    "ok": False,
                    "message": f"not enough symbols with history for optimization ({len(market)})",
                    "required": self.settings.optimization_min_symbols,
                    "available": list(market.keys()),
                }
            cfg["symbols"] = list(market.keys())
            cfg["benchmark_symbol"] = cfg["symbols"][0]
            cfg = self._adapt_for_available_history(cfg, market)
            result = self.optimizer.optimize_and_maybe_promote(market, runtime_config=cfg)
            result.update({
                "ok": True,
                "ran_at": utc_now_iso(),
                "symbols_used": list(market.keys()),
                "available_history_bars": cfg.get("_available_history_bars"),
                "universe": {
                    "selected_count": universe.get("selected_count"),
                    "loaded_count": len(market),
                    "updated_at": universe.get("updated_at"),
                    "selection_mode": universe.get("selection_mode"),
                },
            })
            self.store.write_json("runtime", "last_optimization_cycle.json", payload=result)
            self.store.append_jsonl("runtime", "optimization_cycle_log.jsonl", payload=result)
            return result
        finally:
            self._opt_lock.release()

    def trading_cycle(self) -> Dict:
        if not self._trade_lock.acquire(blocking=False):
            return {"ok": False, "message": "trading cycle already running"}
        try:
            cfg, universe = self._resolve_runtime_config(force_universe_refresh=False)
            market = self.market.get_market(cfg["symbols"], min_bars=max(self.settings.candles_limit, cfg["regime"]["slow"] + 30))
            cfg["symbols"] = list(market.keys())
            if cfg["symbols"]:
                cfg["benchmark_symbol"] = cfg["symbols"][0]
            signal_engine = LiveSignalEngine(cfg)
            enriched_market = signal_engine.build_frames(market)
            latest_prices = {symbol: float(df.iloc[-1]["close"]) for symbol, df in enriched_market.items()}
            executor = self._get_executor()
            if self.settings.mode == "paper":
                exits = self.paper_executor.update_intrabar_exits(
                    market=enriched_market,
                    trailing_atr_mult=cfg["portfolio"]["trailing_atr_mult"],
                    max_holding_bars=cfg["portfolio"]["max_holding_bars"],
                )
            else:
                exits = []
            equity = executor.get_equity(latest_prices) or cfg["portfolio"]["starting_equity"]
            signals = signal_engine.generate(market, equity=equity)
            entry_threshold = cfg["ensemble"]["entry_threshold"]
            top_signals = self._top_signals(signals, cfg["portfolio"]["max_positions"], entry_threshold)
            universe_rankings = self._rankings(signals, universe)
            existing_positions = executor.get_positions()
            actions = []
            top_map = {s.symbol: s for s in top_signals}

            for symbol, pos in existing_positions.items():
                desired = top_map.get(symbol)
                market_df = enriched_market.get(symbol)
                ts = str(market_df.iloc[-1]["timestamp"]) if market_df is not None and not market_df.empty else utc_now_iso()
                px = latest_prices.get(symbol, pos.get("entry_price", 0.0))
                if desired is None or desired.desired_signal != int(pos["side"]):
                    res = executor.close_position(symbol=symbol, price=px, timestamp=ts, reason="signal_exit_or_rotation")
                    if res:
                        actions.append(res)

            refreshed_positions = executor.get_positions()
            available_slots = max(cfg["portfolio"]["max_positions"] - len(refreshed_positions), 0)
            for sig in top_signals:
                if available_slots <= 0:
                    break
                if sig.symbol in refreshed_positions:
                    continue
                notional_fraction = min(sig.notional_fraction, self.settings.max_order_notional_pct, cfg["portfolio"]["max_symbol_exposure"])
                qty = (equity * notional_fraction) / max(sig.close, 1e-9)
                if qty <= 0:
                    continue
                res = executor.open_position(
                    symbol=sig.symbol,
                    side=sig.desired_signal,
                    qty=qty,
                    price=sig.close,
                    timestamp=sig.timestamp,
                    atr_value=sig.atr,
                    stop_atr_mult=sig.stop_atr_mult,
                    take_profit_rr=sig.take_profit_rr,
                )
                actions.append(res)
                available_slots -= 1

            summary = {
                "ok": True,
                "mode": self.settings.mode,
                "ran_at": utc_now_iso(),
                "equity": equity,
                "signals": [sig.__dict__ for sig in top_signals],
                "universe_rankings": universe_rankings[: max(50, len(top_signals))],
                "actions": actions,
                "exits": exits,
                "open_positions": executor.get_positions(),
                "latest_prices": latest_prices,
                "universe": {
                    "selection_mode": universe.get("selection_mode"),
                    "target_size": universe.get("target_size"),
                    "selected_count": universe.get("selected_count"),
                    "loaded_count": len(market),
                    "updated_at": universe.get("updated_at"),
                    "symbols": list(market.keys()),
                },
            }
            self.store.write_json("runtime", "last_trading_cycle.json", payload=summary)
            self.store.append_jsonl("runtime", "trading_cycle_log.jsonl", payload=summary)
            return summary
        finally:
            self._trade_lock.release()

    def status(self) -> Dict:
        return {
            "settings": self.settings.to_dict(),
            "mode": self.settings.mode,
            "has_private_okx_credentials": self.settings.has_private_okx_credentials,
            "last_trading_cycle": self.store.read_json("runtime", "last_trading_cycle.json", default={}),
            "last_optimization_cycle": self.store.read_json("runtime", "last_optimization_cycle.json", default={}),
            "champion": self.store.read_json("champion_config.json", default={}),
            "paper_portfolio": self.store.read_json("paper_portfolio.json", default={}),
            "universe": self.store.read_json("runtime", "universe_snapshot.json", default={}),
        }
