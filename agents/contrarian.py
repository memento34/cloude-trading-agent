"""
CONTRARIAN — Piyasa extremlerini ters yönde fade eder
RSI / StochRSI / Williams / CCI aşırı değerleri + Fear & Greed extremleri.
"Herkes satıyorsa al, herkes alıyorsa sat."
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class ContrarianAgent(BaseAgent):
    def _look_for_trades(self):
        rsi_buy   = self.config.get("rsi_extreme_buy",   22)
        rsi_sell  = self.config.get("rsi_extreme_sell",  78)
        fg_buy    = self.config.get("fear_greed_buy",    18)
        fg_sell   = self.config.get("fear_greed_sell",   82)
        min_score = self.config.get("min_contra_score",   2)

        # Fear & Greed değerini hype sinyallerinden al
        fear_greed = 50
        hype_all = self.hub.get_latest_signals(source="hype", limit=10)
        for h in hype_all:
            if h.get("signal") == "FEAR_GREED":
                fear_greed = h.get("value", 50)
                break

        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not sigs:
                continue
            sig = sigs[-1]

            strength = sig.get("strength", 0)
            if strength < self.config.get("min_signal_strength", 0.52):
                continue

            rsi     = sig.get("rsi", 50)
            stoch_k = sig.get("stoch_rsi_k", 0.5)
            wR      = sig.get("williams_r", -50)
            cci     = sig.get("cci", 0)
            bb_below = sig.get("bb_below", False)
            bb_above = sig.get("bb_above", False)
            ema200_bull = sig.get("ema200_bull", True)

            # ── Contrarian LONG: piyasa panikte, sistematik al ──
            contra_buy = sum([
                rsi      < rsi_buy,
                stoch_k  < 0.08,
                wR       < -90,
                cci      < -120,
                bb_below,
                fear_greed < fg_buy,
            ])

            # ── Contrarian SHORT: piyasa euforide, sistematik sat ─
            contra_sell = sum([
                rsi      > rsi_sell,
                stoch_k  > 0.92,
                wR       > -10,
                cci      > 120,
                bb_above,
                fear_greed > fg_sell,
            ])

            if contra_buy >= min_score:
                self._open_trade(
                    coin, "long",
                    f"Contrarian LONG {contra_buy}/6: RSI={rsi:.0f} "
                    f"StochK={stoch_k:.2f} F&G={fear_greed}"
                )
            elif contra_sell >= min_score:
                self._open_trade(
                    coin, "short",
                    f"Contrarian SHORT {contra_sell}/6: RSI={rsi:.0f} "
                    f"StochK={stoch_k:.2f} F&G={fear_greed}"
                )
