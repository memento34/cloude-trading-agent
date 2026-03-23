from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ..data import load_symbol_csv
from .okx_client import OKXClient
from .settings import ServiceSettings
from .state_store import StateStore, utc_now_iso

# FIX: minimum inter-request delay for OKX public API (rate limit: ~20 req/2 s).
# With 50 symbols in a single cycle this prevents bursting all 50 requests
# simultaneously when the cache is cold.
_OKX_CANDLE_DELAY_SECS: float = 0.12


class MarketDataService:
    def __init__(self, settings: ServiceSettings, store: StateStore):
        self.settings = settings
        self.store = store
        self.okx = OKXClient(settings)
        self.cache_dir = self.store.path("market_cache").parent / "market_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bundle_dir = settings.root_dir / "data"
        self._last_candle_request: float = 0.0   # for rate-limit throttle

    def _cache_path(self, inst_id: str) -> Path:
        return self.cache_dir / f"{inst_id.replace('/', '_').replace('-', '_')}.csv"

    def _parse_okx_candles(self, rows: List[list]) -> pd.DataFrame:
        cols = ["ts", "open", "high", "low", "close", "volume", "vol_ccy", "vol_quote", "confirm"]
        df = pd.DataFrame(rows, columns=cols[: len(rows[0])]) if rows else pd.DataFrame(columns=cols)
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.rename(columns={"ts": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = (df[["timestamp", "open", "high", "low", "close", "volume"]]
              .sort_values("timestamp")
              .drop_duplicates("timestamp"))
        return df.reset_index(drop=True)

    def _csv_fallback(self, inst_id: str) -> pd.DataFrame:
        symbol_map = self.settings.csv_symbol_map or {}
        base_symbol = symbol_map.get(
            inst_id,
            inst_id.replace("-", "").replace("SWAP", "").replace("__", "_"),
        )
        possible = [
            self.bundle_dir / f"{base_symbol}_{self.settings.default_bar.lower()}.csv",
            self.bundle_dir / f"{base_symbol}_1h.csv",
            self.bundle_dir / f"{base_symbol}.csv",
        ]
        for path in possible:
            if path.exists():
                return load_symbol_csv(path)
        raise FileNotFoundError(f"No bundled CSV fallback for {inst_id}")

    def _parse_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _universe_fresh(self, snapshot: Dict) -> bool:
        ts = self._parse_dt(snapshot.get("updated_at"))
        if ts is None:
            return False
        return datetime.now(timezone.utc) - ts < timedelta(minutes=self.settings.universe_refresh_minutes)

    def _build_dynamic_universe(self) -> Dict:
        instruments = self.okx.fetch_instruments(
            self.settings.trade_inst_type, settle_ccy=self.settings.universe_settle_ccy
        )
        tickers = {row.get("instId"): row for row in self.okx.fetch_tickers(self.settings.trade_inst_type)}
        include = set(self.settings.universe_include_symbols or [])

        # FIX: read max-spread filter from settings (default 0 = disabled)
        max_spread_bps: float = getattr(self.settings, "universe_max_spread_bps", 0.0)
        min_volume: float = self.settings.universe_min_volume_usdt  # FIX: applied below

        rows: List[Dict] = []
        for inst in instruments:
            inst_id = inst.get("instId")
            if not inst_id or inst_id not in tickers:
                continue
            state = str(inst.get("state") or "").lower()
            if state and state not in {"live", "open", "preopen"}:
                continue
            if self.settings.trade_inst_type.upper() == "SWAP":
                if str(inst.get("settleCcy") or "").upper() != self.settings.universe_settle_ccy.upper():
                    continue
                if self.settings.universe_quote_ccy and (
                    f"-{self.settings.universe_quote_ccy.upper()}-SWAP" not in inst_id.upper()
                ):
                    continue

            ticker = tickers[inst_id]
            vol_quote = float(ticker.get("volCcy24h") or 0.0)
            last = float(ticker.get("last") or 0.0)
            bid = float(ticker.get("bidPx") or 0.0)
            ask = float(ticker.get("askPx") or 0.0)
            spread_bps = ((ask - bid) / last * 10_000.0) if last > 0 and bid > 0 and ask > 0 else 0.0

            # FIX: actually enforce volume filter (was always 0 before)
            if vol_quote < min_volume and inst_id not in include:
                continue

            # FIX: enforce spread filter when configured (skips wide spreads)
            if max_spread_bps > 0 and spread_bps > max_spread_bps and inst_id not in include:
                continue

            rows.append({
                "instId": inst_id,
                "baseCcy": inst.get("baseCcy"),
                "quoteCcy": inst.get("quoteCcy"),
                "settleCcy": inst.get("settleCcy"),
                "ctVal": inst.get("ctVal"),
                "ctValCcy": inst.get("ctValCcy"),
                "last": last,
                "bidPx": bid,
                "askPx": ask,
                "spread_bps": round(spread_bps, 4),
                "volCcy24h": vol_quote,
                "vol24h": float(ticker.get("vol24h") or 0.0),
                "change24h_pct": round(
                    (((last / float(ticker.get("sodUtc0") or last)) - 1.0) * 100.0)
                    if last > 0 and float(ticker.get("sodUtc0") or 0.0) > 0
                    else 0.0,
                    4,
                ),
            })

        rows.sort(key=lambda x: x.get("volCcy24h", 0.0), reverse=True)
        chosen = rows[: self.settings.universe_size]
        snapshot = {
            "selection_mode": "okx_top_volume_swaps",
            "target_size": self.settings.universe_size,
            "selected_count": len(chosen),
            "universe_settle_ccy": self.settings.universe_settle_ccy,
            "universe_quote_ccy": self.settings.universe_quote_ccy,
            "universe_min_volume_usdt": min_volume,
            "universe_max_spread_bps": max_spread_bps,
            "updated_at": utc_now_iso(),
            "symbols": [row["instId"] for row in chosen],
            "members": [dict(rank=i + 1, **row) for i, row in enumerate(chosen)],
        }
        self.store.write_json("runtime", "universe_snapshot.json", payload=snapshot)
        self.store.append_jsonl("runtime", "universe_history.jsonl", payload=snapshot)
        return snapshot

    def get_universe_snapshot(self, force_refresh: bool = False) -> Dict:
        if not self.settings.dynamic_universe:
            snapshot = {
                "selection_mode": "fixed_okx_pair_list",
                "target_size": len(self.settings.symbols or []),
                "selected_count": len(self.settings.symbols or []),
                "updated_at": utc_now_iso(),
                "symbols": list(self.settings.symbols or []),
                "members": [
                    {"rank": i + 1, "instId": sym, "volCcy24h": None, "last": None}
                    for i, sym in enumerate(self.settings.symbols or [])
                ],
            }
            self.store.write_json("runtime", "universe_snapshot.json", payload=snapshot)
            return snapshot
        snapshot = self.store.read_json("runtime", "universe_snapshot.json", default={}) or {}
        if force_refresh or not snapshot or not self._universe_fresh(snapshot):
            return self._build_dynamic_universe()
        return snapshot

    def resolve_symbols(self, force_refresh: bool = False) -> Tuple[List[str], Dict]:
        snapshot = self.get_universe_snapshot(force_refresh=force_refresh)
        symbols = list(snapshot.get("symbols") or self.settings.symbols or [])
        return symbols, snapshot

    def get_candles(self, inst_id: str, bar: str | None = None, min_bars: int | None = None) -> pd.DataFrame:
        bar = bar or self.settings.default_bar
        min_bars = min_bars or self.settings.candles_limit
        cache_path = self._cache_path(inst_id)
        cached = pd.read_csv(cache_path, parse_dates=["timestamp"]) if cache_path.exists() else pd.DataFrame()
        fetched = pd.DataFrame()
        source = self.settings.market_data_source
        errors = []

        if source in {"okx", "auto"}:
            try:
                # FIX: throttle requests to avoid OKX public rate limit
                elapsed = time.monotonic() - self._last_candle_request
                if elapsed < _OKX_CANDLE_DELAY_SECS:
                    time.sleep(_OKX_CANDLE_DELAY_SECS - elapsed)
                limit = min(max(min_bars, self.settings.candles_limit), 300)
                rows = self.okx.fetch_candles(inst_id, bar=bar, limit=limit)
                self._last_candle_request = time.monotonic()
                fetched = self._parse_okx_candles(rows)
            except Exception as exc:
                errors.append(str(exc))

        if fetched.empty and source in {"csv", "auto"}:
            try:
                fetched = self._csv_fallback(inst_id)
            except Exception as exc:
                errors.append(str(exc))

        if fetched.empty and not cached.empty:
            merged = cached.copy()
        elif cached.empty:
            merged = fetched.copy()
        else:
            merged = (pd.concat([cached, fetched], ignore_index=True)
                      .drop_duplicates("timestamp")
                      .sort_values("timestamp"))

        if merged.empty:
            raise RuntimeError(f"No market data available for {inst_id}. Errors: {errors}")

        merged = merged.tail(self.settings.history_cache_bars).reset_index(drop=True)
        merged.to_csv(cache_path, index=False)
        self.store.write_json("market_cache", f"{inst_id.replace('-', '_')}_meta.json", payload={
            "inst_id": inst_id,
            "bars": len(merged),
            "updated_at": utc_now_iso(),
            "bar": bar,
            "source": "okx" if not fetched.empty and source != "csv" else "csv_or_cache",
            "errors": errors,
        })
        return merged

    def get_market(
        self,
        symbols: List[str] | None = None,
        min_bars: int | None = None,
        force_universe_refresh: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        snapshot = None
        if symbols is None:
            symbols, snapshot = self.resolve_symbols(force_refresh=force_universe_refresh)
        market: Dict[str, pd.DataFrame] = {}
        errors: Dict[str, str] = {}
        for symbol in symbols:
            try:
                market[symbol] = self.get_candles(symbol, min_bars=min_bars)
            except Exception as exc:
                errors[symbol] = str(exc)
        if snapshot is None:
            snapshot = self.get_universe_snapshot(force_refresh=False)
        snapshot["loaded_symbols"] = list(market.keys())
        snapshot["load_errors"] = errors
        snapshot["loaded_count"] = len(market)
        self.store.write_json("runtime", "universe_snapshot.json", payload=snapshot)
        min_required = max(3, min(self.settings.min_loaded_symbols, len(symbols)))
        if len(market) < min_required:
            raise RuntimeError(
                f"Loaded only {len(market)} / {len(symbols)} symbols. "
                f"Sample errors: {list(errors.items())[:5]}"
            )
        return market
