"""
ICHIMOKU SENSEI — Tam Ichimoku konfirmasyonu
Sadece ta kütüphanesi Ichimoku verisi ürettiğinde işlem yapar.
Bulut içindeyken kesinlikle işlem yok.
Tenkan > Kijun + Fiyat bulut üstü + MACD onayı.
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class IchimokuSenseiAgent(BaseAgent):
    def _look_for_trades(self):
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not sigs:
                continue
            sig = sigs[-1]

            ich_bull = sig.get("ich_bull")  # True / False / None
            if ich_bull is None:
                continue  # Bulut içi = belirsiz = işlem yok

            strength  = sig.get("strength", 0)
            if strength < self.config.get("min_signal_strength", 0.70):
                continue

            rsi       = sig.get("rsi", 50)
            macd_bull = sig.get("macd_bull", False)
            ema_golden = sig.get("ema_golden", False)
            vol_ratio  = sig.get("vol_ratio", 1.0)
            mom5       = sig.get("momentum_5", 0)

            # ── LONG: Ichimoku bull + MACD onayı ─────────────────
            if ich_bull and rsi < 72 and macd_bull:
                confirmation = sum([ema_golden, vol_ratio > 1.3, mom5 > 0])
                self._open_trade(
                    coin, "long",
                    f"Ichimoku LONG: bulut üstü, Tenkan>Kijun, MACD bull "
                    f"| conf={confirmation}/3 RSI={rsi:.0f}"
                )

            # ── SHORT: Ichimoku bear + MACD onayı ────────────────
            elif not ich_bull and rsi > 28 and not macd_bull:
                confirmation = sum([not ema_golden, vol_ratio > 1.3, mom5 < 0])
                self._open_trade(
                    coin, "short",
                    f"Ichimoku SHORT: bulut altı, Tenkan<Kijun, MACD bear "
                    f"| conf={confirmation}/3 RSI={rsi:.0f}"
                )
