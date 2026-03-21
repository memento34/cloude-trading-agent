"""
VOLUME SHARK — Hacim patlaması + OBV yönü + momentum uyumu
Hacim olmadan işlem yok. Büyük hacim = büyük oyuncuların hareketi.
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class VolumeSharkAgent(BaseAgent):
    def _look_for_trades(self):
        min_vol = self.config.get("min_vol_ratio", 2.0)

        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not sigs:
                continue
            sig = sigs[-1]

            vol_ratio = sig.get("vol_ratio", 1.0)
            if vol_ratio < min_vol:
                continue   # Hacim yoksa işlem yok

            strength  = sig.get("strength", 0)
            if strength < self.config.get("min_signal_strength", 0.60):
                continue

            direction = sig.get("signal", "")
            obv_trend = sig.get("obv_trend", 0)
            mom5      = sig.get("momentum_5", 0)
            macd_bull = sig.get("macd_bull", False)
            rsi       = sig.get("rsi", 50)

            # Hype oracle'dan da bakabiliriz
            hype_sigs = self.hub.get_signals_for_coin(coin, source="hype", limit=2)
            hype_alert = any(h.get("signal") == "HYPE_ALERT" for h in hype_sigs)

            reason_base = f"VolumeShark: vol×{vol_ratio:.1f}, OBV:{obv_trend:+d}, mom:{mom5:.1f}%"
            if hype_alert:
                reason_base += " + HYPE!"

            # ── LONG: vol spike + OBV yukarı + momentum pozitif ──
            if direction == "BUY" and obv_trend >= 0 and (mom5 > 0 or macd_bull) and rsi < 75:
                self._open_trade(coin, "long", reason_base)

            # ── SHORT: vol spike + OBV aşağı + momentum negatif ─
            elif direction == "SELL" and obv_trend <= 0 and (mom5 < 0 or not macd_bull) and rsi > 25:
                self._open_trade(coin, "short", reason_base)

            # ── HYPE bonus: çok güçlü hacim patlaması (×3+) ──────
            elif vol_ratio >= 3.0 and hype_alert and direction == "BUY":
                self._open_trade(coin, "long", reason_base + " EXTREME VOL!")
