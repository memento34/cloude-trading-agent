
"""
BREAKOUT — Bollinger kırılmaları ve güçlü momentum yakalamak
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class BreakoutAgent(BaseAgent):
    def _look_for_trades(self):
        daily_trades = sum(1 for t in self.trader.trade_history
                          if t.get("opened_at","").startswith(
                              __import__("datetime").datetime.now().strftime("%Y-%m-%d")))
        if daily_trades >= 3:
            return  # Günde max 3 işlem
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            signals = self.hub.get_signals_for_coin(coin, source="technical", limit=5)
            for sig in signals:
                strength = sig.get("strength", 0)
                if strength < self.config.get("min_signal_strength", 0.70):
                    continue
                reason = sig.get("reason", "")
                if "bollinger" in reason.lower() or "breakout" in reason.lower() or "macd" in reason.lower():
                    direction = "long" if sig.get("signal") == "BUY" else "short"
                    self._open_trade(coin, direction, f"Kırılma: {reason}")
                    break
