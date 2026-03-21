"""
TREND RIDER — EMA20/EMA50 golden cross bölgesi + EMA200 makro filtresi
Bull market'ta long, bear market'ta short; ama yalnızca trend bölgesinde.
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class TrendRiderAgent(BaseAgent):
    def _look_for_trades(self):
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not sigs:
                continue
            sig = sigs[-1]

            strength     = sig.get("strength", 0)
            ema_golden   = sig.get("ema_golden", False)        # EMA20 > EMA50
            ema200_bull  = sig.get("ema200_bull", True)
            macd_bull    = sig.get("macd_bull", False)
            ema_cross_b  = sig.get("ema_cross_bull", False)    # taze golden cross
            ema_cross_d  = sig.get("ema_cross_bear", False)    # taze death cross
            rsi          = sig.get("rsi", 50)
            ich_bull     = sig.get("ich_bull", None)

            if strength < self.config.get("min_signal_strength", 0.65):
                continue

            # ── LONG: golden bölge + EMA200 üstü + MACD bull
            if ema_golden and ema200_bull and macd_bull and rsi < 72:
                reason = (
                    f"TrendRider LONG: golden_zone, EMA200 bull, MACD bull"
                    + (", taze cross!" if ema_cross_b else "")
                    + (f", Ichimoku bull" if ich_bull else "")
                )
                self._open_trade(coin, "long", reason)

            # ── SHORT: death bölge + EMA200 altı + MACD bear
            elif not ema_golden and not ema200_bull and not macd_bull and rsi > 28:
                reason = (
                    f"TrendRider SHORT: death_zone, EMA200 bear, MACD bear"
                    + (", taze cross!" if ema_cross_d else "")
                )
                self._open_trade(coin, "short", reason)
