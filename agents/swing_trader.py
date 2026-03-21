"""
SWING TRADER — Büyük hamleleri yakalar
N ardışık aynı yönlü sinyal + EMA200 makro filtresi + Hype onayı.
Az ama büyük pozisyon, geniş TP hedefi.
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)


class SwingTraderAgent(BaseAgent):
    def _look_for_trades(self):
        min_n = self.config.get("min_consecutive_signals", 2)

        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            sigs = self.hub.get_signals_for_coin(coin, source="technical", limit=6)
            if len(sigs) < min_n:
                continue

            # Son N sinyalin hepsi aynı yönde mi?
            recent     = sigs[-min_n:]
            directions = [s.get("signal", "") for s in recent]
            if len(set(directions)) != 1:
                continue  # Karışık yönler

            strengths   = [s.get("strength", 0) for s in recent]
            avg_strength = sum(strengths) / len(strengths)
            if avg_strength < self.config.get("min_signal_strength", 0.70):
                continue

            latest      = sigs[-1]
            direction   = directions[-1]
            ema200_bull = latest.get("ema200_bull", True)
            ema_golden  = latest.get("ema_golden", False)
            vol_ratio   = latest.get("vol_ratio", 1.0)
            rsi         = latest.get("rsi", 50)
            ich_bull    = latest.get("ich_bull", None)

            # Hype onayı (bonus, zorunlu değil)
            hype_sigs  = self.hub.get_signals_for_coin(coin, source="hype", limit=3)
            hype_boost = any(h.get("signal") == "HYPE_ALERT" for h in hype_sigs)

            score = 0
            if direction == "BUY":
                score += ema200_bull        # Makro bull
                score += ema_golden         # EMA bölgesi
                score += vol_ratio > 1.2    # Hacim desteği
                score += ich_bull is True   # Ichimoku onayı
                score += hype_boost         # Hype bonus
                if score < 2:
                    continue  # En az 2 ekstra konfirmasyon lazım
                self._open_trade(
                    coin, "long",
                    f"SwingTrader LONG ×{min_n}: str={avg_strength:.2f} "
                    f"score={score}/5 EMA200={'✓' if ema200_bull else '✗'} "
                    f"hype={'✓' if hype_boost else '✗'}"
                )
            elif direction == "SELL":
                score += not ema200_bull    # Makro bear
                score += not ema_golden     # Death zone
                score += vol_ratio > 1.2
                score += ich_bull is False
                if score < 2:
                    continue
                self._open_trade(
                    coin, "short",
                    f"SwingTrader SHORT ×{min_n}: str={avg_strength:.2f} "
                    f"score={score}/4 EMA200={'bear' if not ema200_bull else 'bull'}"
                )
