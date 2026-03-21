"""
MEAN REVERTER — İstatistiksel ortalamaya dönüş
BB + RSI + CCI + StochRSI + Williams aşırı satım/alım konfirmasyonu.
Range rejiminde en verimli.
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class MeanReverterAgent(BaseAgent):
    def _look_for_trades(self):
        min_score = self.config.get("oversold_min_score", 2)

        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not sigs:
                continue
            sig = sigs[-1]

            strength = sig.get("strength", 0)
            if strength < self.config.get("min_signal_strength", 0.58):
                continue

            rsi      = sig.get("rsi", 50)
            stoch_k  = sig.get("stoch_rsi_k", 0.5)
            cci      = sig.get("cci", 0)
            wR       = sig.get("williams_r", -50)
            bb_below = sig.get("bb_below", False)
            bb_above = sig.get("bb_above", False)
            mom5     = sig.get("momentum_5", 0)
            # Trend filtresi: EMA200 ile ters işlem yapma
            ema200_bull = sig.get("ema200_bull", True)

            # ── Aşırı satım (LONG) ───────────────────────────────
            oversold_score = sum([
                rsi     < 35,
                stoch_k < 0.20,
                cci     < -80,
                wR      < -80,
                bb_below,
            ])

            # ── Aşırı alım (SHORT) ───────────────────────────────
            overbought_score = sum([
                rsi     > 65,
                stoch_k > 0.80,
                cci     > 80,
                wR      > -20,
                bb_above,
            ])

            if oversold_score >= min_score and ema200_bull:
                # Sadece EMA200 üstünde long — bear market diplerini atla
                self._open_trade(
                    coin, "long",
                    f"MeanReverter: {oversold_score}/5 oversold "
                    f"(RSI={rsi:.0f} CCI={cci:.0f} mom={mom5:.1f}%)"
                )
            elif overbought_score >= min_score and not ema200_bull:
                # Sadece EMA200 altında short
                self._open_trade(
                    coin, "short",
                    f"MeanReverter: {overbought_score}/5 overbought "
                    f"(RSI={rsi:.0f} CCI={cci:.0f} mom={mom5:.1f}%)"
                )
            elif oversold_score >= min_score + 1:
                # Çok aşırı satım: EMA200 filtresi olmaksızın gir
                self._open_trade(
                    coin, "long",
                    f"MeanReverter EXTREME: {oversold_score}/5 oversold"
                )
