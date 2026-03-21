
"""
BOUNCER — RSI aşırı satım + dip bounce stratejisi
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class BouncerAgent(BaseAgent):
    def _look_for_trades(self):
        rsi_threshold = self.config.get("rsi_oversold", 30)
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            signals = self.hub.get_signals_for_coin(coin, source="technical", limit=5)
            for sig in signals:
                if sig.get("signal") != "BUY":
                    continue
                reason = sig.get("reason", "")
                rsi_val = sig.get("rsi")
                # RSI aşırı satım olmalı
                if rsi_val and rsi_val > rsi_threshold:
                    continue
                if "oversold" in reason.lower() or (rsi_val and rsi_val < rsi_threshold):
                    self._open_trade(coin, "long", f"Dip bounce: {reason}")
                    break
