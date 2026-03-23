from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from .settings import ServiceSettings


class OKXClient:
    def __init__(self, settings: ServiceSettings, timeout: float = 30.0):
        self.settings = settings
        self.base_url = settings.okx_base_url.rstrip("/")
        self.timeout = timeout

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _sign(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        signature = hmac.new(
            self.settings.okx_api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode()

    def _headers(self, method: str, request_path: str, body: str = "", private: bool = False) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.okx_flag == "1":
            headers["x-simulated-trading"] = "1"
        if private:
            if not self.settings.has_private_okx_credentials:
                raise RuntimeError("Missing OKX private credentials")
            ts = self._timestamp()
            headers.update(
                {
                    "OK-ACCESS-KEY": self.settings.okx_api_key,
                    "OK-ACCESS-SIGN": self._sign(ts, method, request_path, body),
                    "OK-ACCESS-TIMESTAMP": ts,
                    "OK-ACCESS-PASSPHRASE": self.settings.okx_passphrase,
                }
            )
        return headers

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None, private: bool = False) -> Dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        request_path = f"{path}{query}"
        body_text = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = self._headers(method, request_path, body_text, private=private)
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, url, params=params, content=body_text or None, headers=headers)
            response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and str(payload.get("code", "0")) not in {"0", "", "None"}:
            raise RuntimeError(f"OKX error {payload.get('code')}: {payload.get('msg')}")
        return payload

    def public_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params, private=False)

    def private_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params, private=True)

    def private_post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, body=body, private=True)

    def fetch_candles(self, inst_id: str, bar: str, limit: int = 300) -> List[list]:
        payload = self.public_get("/api/v5/market/candles", {"instId": inst_id, "bar": bar, "limit": str(limit)})
        return payload.get("data", [])

    def fetch_instrument(self, inst_id: str, inst_type: str) -> Dict[str, Any]:
        payload = self.public_get("/api/v5/public/instruments", {"instType": inst_type, "instId": inst_id})
        data = payload.get("data", [])
        if not data:
            raise RuntimeError(f"Instrument not found: {inst_id}")
        return data[0]

    def fetch_instruments(self, inst_type: str, settle_ccy: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"instType": inst_type}
        if settle_ccy:
            params["settleCcy"] = settle_ccy
        payload = self.public_get("/api/v5/public/instruments", params)
        return payload.get("data", [])

    def fetch_tickers(self, inst_type: str) -> List[Dict[str, Any]]:
        payload = self.public_get("/api/v5/market/tickers", {"instType": inst_type})
        return payload.get("data", [])

    def fetch_balance(self, ccy: str = "USDT") -> Dict[str, Any]:
        return self.private_get("/api/v5/account/balance", {"ccy": ccy})

    def fetch_positions(self, inst_id: Optional[str] = None, inst_type: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if inst_id:
            params["instId"] = inst_id
        if inst_type:
            params["instType"] = inst_type
        return self.private_get("/api/v5/account/positions", params or None)

    def set_leverage(self, inst_id: str, leverage: str, td_mode: str = "cross") -> Dict[str, Any]:
        return self.private_post("/api/v5/account/set-leverage", {"instId": inst_id, "lever": str(leverage), "mgnMode": td_mode})

    def place_market_order(
        self,
        inst_id: str,
        side: str,
        sz: str,
        td_mode: str,
        reduce_only: bool = False,
        pos_side: Optional[str] = None,
        tag: Optional[str] = None,
        stop_loss_px: Optional[str] = None,
        take_profit_px: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place a market order, optionally attaching exchange-side SL/TP algo
        orders so positions remain protected even if the service goes down.

        OKX v5 supports ``attachAlgoOrds`` on the order creation endpoint –
        this is preferred over separate algo-order calls because the entry and
        the conditional orders are submitted atomically.
        """
        body: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": "market",
            "sz": sz,
            "reduceOnly": str(reduce_only).lower(),
        }
        if pos_side:
            body["posSide"] = pos_side
        if tag:
            body["tag"] = tag[:16]

        # Attach exchange-side stop-loss and take-profit when opening a position
        if not reduce_only and (stop_loss_px or take_profit_px):
            algo: Dict[str, Any] = {}
            if stop_loss_px:
                algo["slTriggerPx"] = stop_loss_px
                algo["slOrdPx"] = "-1"          # market execution on trigger
                algo["slTriggerPxType"] = "last"
            if take_profit_px:
                algo["tpTriggerPx"] = take_profit_px
                algo["tpOrdPx"] = "-1"          # market execution on trigger
                algo["tpTriggerPxType"] = "last"
            body["attachAlgoOrds"] = [algo]

        return self.private_post("/api/v5/trade/order", body)
