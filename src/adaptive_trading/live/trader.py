from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import pandas as pd

from .okx_client import OKXClient
from .settings import ServiceSettings
from .state_store import StateStore, utc_now_iso


@dataclass
class RuntimePosition:
    symbol: str
    side: int
    qty: float
    entry_price: float
    entry_time: str
    stop_price: float
    take_profit_price: float
    trail_price: float
    peak_price: float
    trough_price: float
    bars_held: int = 0
    exchange_order_id: str = ""


# ── Paper executor ──────────────────────────────────────────────────────────

class PaperExecutor:
    """
    Simulated executor for paper-trading mode.

    FIX: fee model is now applied on both entry and exit, matching the
    backtester (4 BPS default), so paper and backtest results are
    comparable.
    """

    def __init__(self, settings: ServiceSettings, store: StateStore):
        self.settings = settings
        self.store = store
        self._boot_state()

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def _fee_rate(self) -> float:
        # Mirror backtester fee_bps (configurable via base_config; fall back to 4 BPS)
        return 4.0 / 10_000.0

    def _boot_state(self) -> None:
        self.store.ensure_default("paper_portfolio.json", payload={
            "cash": self.settings.paper_starting_equity,
            "positions": {},
            "trades": [],
            "updated_at": utc_now_iso(),
        })

    def load_portfolio(self) -> Dict:
        return self.store.read_json("paper_portfolio.json", default={})

    def save_portfolio(self, payload: Dict) -> None:
        payload["updated_at"] = utc_now_iso()
        self.store.write_json("paper_portfolio.json", payload=payload)

    def get_positions(self) -> Dict[str, Dict]:
        return self.load_portfolio().get("positions", {})

    def get_equity(self, latest_prices: Dict[str, float]) -> float:
        pf = self.load_portfolio()
        equity = float(pf.get("cash", self.settings.paper_starting_equity))
        for symbol, pos in pf.get("positions", {}).items():
            equity += (latest_prices.get(symbol, pos["entry_price"]) - pos["entry_price"]) * pos["qty"] * pos["side"]
        return equity

    def update_intrabar_exits(
        self,
        market: Dict[str, pd.DataFrame],
        trailing_atr_mult: float,
        max_holding_bars: int,
    ) -> List[Dict]:
        pf = self.load_portfolio()
        positions = pf.get("positions", {})
        trades = pf.get("trades", [])
        exits: List[Dict] = []
        changed = False

        for symbol, pos in list(positions.items()):
            if symbol not in market or market[symbol].empty:
                continue
            row = market[symbol].iloc[-1]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            atr_value = max(float(row.get("atr", (high - low) or close * 0.01)), 1e-9)
            pos["bars_held"] = int(pos.get("bars_held", 0)) + 1
            exit_price = None
            exit_reason = None

            if pos["side"] == 1:
                pos["peak_price"] = max(float(pos.get("peak_price", pos["entry_price"])), high)
                pos["trail_price"] = max(float(pos.get("trail_price", pos["entry_price"])), pos["peak_price"] - atr_value * trailing_atr_mult)
                effective_stop = max(float(pos["stop_price"]), float(pos["trail_price"]))
                if low <= effective_stop:
                    exit_price = effective_stop
                    exit_reason = "stop_or_trail"
                elif high >= float(pos["take_profit_price"]):
                    exit_price = float(pos["take_profit_price"])
                    exit_reason = "take_profit"
            else:
                pos["trough_price"] = min(float(pos.get("trough_price", pos["entry_price"])), low)
                pos["trail_price"] = min(float(pos.get("trail_price", pos["entry_price"])), pos["trough_price"] + atr_value * trailing_atr_mult)
                effective_stop = min(float(pos["stop_price"]), float(pos["trail_price"]))
                if high >= effective_stop:
                    exit_price = effective_stop
                    exit_reason = "stop_or_trail"
                elif low <= float(pos["take_profit_price"]):
                    exit_price = float(pos["take_profit_price"])
                    exit_reason = "take_profit"

            if exit_reason is None and pos["bars_held"] >= max_holding_bars:
                exit_price = close
                exit_reason = "time_stop"

            if exit_reason is not None and exit_price is not None:
                exit_fee = abs(pos["qty"] * exit_price) * self._fee_rate
                gross_pnl = (exit_price - pos["entry_price"]) * pos["qty"] * pos["side"]
                net_pnl = gross_pnl - exit_fee - float(pos.get("entry_fee", 0.0))
                pf["cash"] = float(pf.get("cash", 0.0)) + gross_pnl - exit_fee
                trades.append({
                    "symbol": symbol,
                    "side": pos["side"],
                    "entry_time": pos["entry_time"],
                    "exit_time": str(row["timestamp"]),
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "qty": pos["qty"],
                    "fees": pos.get("entry_fee", 0.0) + exit_fee,
                    "pnl": net_pnl,
                    "reason": exit_reason,
                })
                exits.append({"symbol": symbol, "reason": exit_reason, "exit_price": exit_price, "pnl": net_pnl})
                positions.pop(symbol, None)
                changed = True

        if changed:
            pf["positions"] = positions
            pf["trades"] = trades[-5000:]
            self.save_portfolio(pf)
        return exits

    def open_position(
        self, symbol: str, side: int, qty: float, price: float,
        timestamp: str, atr_value: float, stop_atr_mult: float, take_profit_rr: float,
    ) -> Dict:
        pf = self.load_portfolio()
        positions = pf.get("positions", {})
        stop_distance = atr_value * stop_atr_mult
        if side == 1:
            stop_price = price - stop_distance
            take_profit = price + stop_distance * take_profit_rr
            trail = price - atr_value * 1.8
        else:
            stop_price = price + stop_distance
            take_profit = price - stop_distance * take_profit_rr
            trail = price + atr_value * 1.8

        # FIX: deduct entry fee from cash (mirrors backtester behaviour)
        notional = qty * price
        entry_fee = notional * self._fee_rate
        pf["cash"] = float(pf.get("cash", self.settings.paper_starting_equity)) - entry_fee

        positions[symbol] = asdict(RuntimePosition(
            symbol=symbol, side=side, qty=qty, entry_price=price,
            entry_time=timestamp, stop_price=stop_price,
            take_profit_price=take_profit, trail_price=trail,
            peak_price=price, trough_price=price,
        ))
        positions[symbol]["entry_fee"] = entry_fee
        pf["positions"] = positions
        self.save_portfolio(pf)
        return {"symbol": symbol, "action": "open", "side": side, "qty": qty, "price": price, "entry_fee": entry_fee}

    def close_position(self, symbol: str, price: float, timestamp: str, reason: str) -> Optional[Dict]:
        pf = self.load_portfolio()
        positions = pf.get("positions", {})
        pos = positions.get(symbol)
        if not pos:
            return None
        exit_fee = abs(pos["qty"] * price) * self._fee_rate
        gross_pnl = (price - pos["entry_price"]) * pos["qty"] * pos["side"]
        net_pnl = gross_pnl - exit_fee - float(pos.get("entry_fee", 0.0))
        pf["cash"] = float(pf.get("cash", 0.0)) + gross_pnl - exit_fee
        pf.setdefault("trades", []).append({
            "symbol": symbol,
            "side": pos["side"],
            "entry_time": pos["entry_time"],
            "exit_time": timestamp,
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "qty": pos["qty"],
            "fees": pos.get("entry_fee", 0.0) + exit_fee,
            "pnl": net_pnl,
            "reason": reason,
        })
        positions.pop(symbol, None)
        pf["positions"] = positions
        pf["trades"] = pf["trades"][-5000:]
        self.save_portfolio(pf)
        return {"symbol": symbol, "action": "close", "price": price, "reason": reason, "pnl": net_pnl}


# ── Live executor ───────────────────────────────────────────────────────────

class LiveExecutor:
    """
    Real-money executor connecting to OKX.

    FIX: Exchange-side stop-loss and take-profit orders are now sent
    atomically alongside the entry order via OKX ``attachAlgoOrds``.
    This means open positions remain protected even if the service process
    crashes or loses internet connectivity.
    """

    def __init__(self, settings: ServiceSettings, store: StateStore):
        self.settings = settings
        self.store = store
        self.okx = OKXClient(settings)
        self.instrument_cache: Dict[str, Dict] = {}

    def _get_instrument(self, symbol: str) -> Dict:
        if symbol not in self.instrument_cache:
            self.instrument_cache[symbol] = self.okx.fetch_instrument(symbol, self.settings.trade_inst_type)
        return self.instrument_cache[symbol]

    def _contracts_from_notional(self, symbol: str, notional_usd: float, price: float) -> float:
        meta = self._get_instrument(symbol)
        ct_val = float(meta.get("ctVal") or 1.0)
        min_sz = float(meta.get("minSz") or 1.0)
        lot_sz = float(meta.get("lotSz") or min_sz or 1.0)
        contracts = max(notional_usd / max(price * ct_val, 1e-9), 0.0)
        return max(round(contracts / lot_sz) * lot_sz, min_sz)

    def _fmt_price(self, price: float) -> str:
        """Format a price to a reasonable number of decimals for OKX."""
        return f"{price:.8f}".rstrip("0").rstrip(".")

    def get_positions(self) -> Dict[str, Dict]:
        payload = self.okx.fetch_positions(inst_type=self.settings.trade_inst_type)
        positions = {}
        for row in payload.get("data", []):
            qty = abs(float(row.get("pos") or 0.0))
            if qty <= 0:
                continue
            side_raw = str(row.get("posSide") or "")
            side = 1 if side_raw in {"long", "net"} and float(row.get("pos", 0)) >= 0 else -1
            if side_raw == "short":
                side = -1
            positions[row["instId"]] = {
                "symbol": row["instId"],
                "side": side,
                "qty": qty,
                "entry_price": float(row.get("avgPx") or 0.0),
                "entry_time": utc_now_iso(),
                "exchange_order_id": row.get("posId", ""),
            }
        return positions

    def get_equity(self, latest_prices: Dict[str, float]) -> float:
        payload = self.okx.fetch_balance(self.settings.settle_ccy)
        try:
            details = payload.get("data", [])[0].get("details", [])
            for row in details:
                if row.get("ccy") == self.settings.settle_ccy:
                    return float(row.get("eq") or row.get("cashBal") or 0.0)
        except Exception:
            pass
        return 0.0

    def open_position(
        self, symbol: str, side: int, qty: float, price: float,
        timestamp: str, atr_value: float, stop_atr_mult: float, take_profit_rr: float,
    ) -> Dict:
        self.okx.set_leverage(symbol, self.settings.leverage, self.settings.td_mode)
        notional_usd = qty * price
        contracts = self._contracts_from_notional(symbol, notional_usd, price)
        side_txt = "buy" if side == 1 else "sell"

        # Compute exchange-side SL/TP prices
        stop_distance = atr_value * stop_atr_mult
        if side == 1:
            stop_px = price - stop_distance
            tp_px = price + stop_distance * take_profit_rr
        else:
            stop_px = price + stop_distance
            tp_px = price - stop_distance * take_profit_rr

        # FIX: attach SL/TP atomically to protect position if service dies
        payload = self.okx.place_market_order(
            inst_id=symbol,
            side=side_txt,
            sz=str(contracts),
            td_mode=self.settings.td_mode,
            reduce_only=False,
            tag="ATSV7OPEN",
            stop_loss_px=self._fmt_price(stop_px),
            take_profit_px=self._fmt_price(tp_px),
        )
        return {
            "symbol": symbol, "action": "open", "side": side,
            "contracts": contracts,
            "stop_price": stop_px, "take_profit_price": tp_px,
            "response": payload,
        }

    def close_position(self, symbol: str, price: float, timestamp: str, reason: str) -> Dict:
        positions = self.get_positions()
        pos = positions.get(symbol)
        if not pos:
            return {"symbol": symbol, "action": "close", "status": "no_position"}
        side_txt = "sell" if pos["side"] == 1 else "buy"
        payload = self.okx.place_market_order(
            inst_id=symbol,
            side=side_txt,
            sz=str(pos["qty"]),
            td_mode=self.settings.td_mode,
            reduce_only=True,
            tag="ATSV7CLOSE",
        )
        return {"symbol": symbol, "action": "close", "reason": reason, "response": payload}
