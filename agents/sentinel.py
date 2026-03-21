
"""
SENTINEL — Muhafazakar, sadece güçlü trend sinyallerinde girer
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class SentinelAgent(BaseAgent):
    def _look_for_trades(self):
        min_strength = self.config.get("min_signal_strength", 0.75)
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            signals = self.hub.get_signals_for_coin(coin, source="technical", limit=5)
            if not signals:
                continue
            latest = signals[-1]
            if latest.get("strength", 0) < min_strength:
                continue
            direction = latest.get("signal")
            if direction == "BUY":
                self._open_trade(coin, "long", f"Güçlü teknik sinyal: {latest.get('reason','')}")
            elif direction == "SELL":
                self._open_trade(coin, "short", f"Güçlü satış sinyali: {latest.get('reason','')}")
