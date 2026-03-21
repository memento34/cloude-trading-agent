
"""
MOMENTUM — Hype sinyallerine tepki verir, teknik onay arar
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class MomentumAgent(BaseAgent):
    def _look_for_trades(self):
        # Hype sinyallerini al
        hype_signals = self.hub.get_latest_signals(source="hype", limit=20)
        for sig in hype_signals:
            coin = sig.get("coin")
            if not coin or "/" not in coin:
                continue
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            if sig.get("signal") != "HYPE_ALERT":
                continue
            if sig.get("strength", 0) < self.config.get("min_signal_strength", 0.60):
                continue
            # Teknik onayla (isteğe bağlı ama varsa güçlendirir)
            tech = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            tech_buy = any(t.get("signal") == "BUY" for t in tech)
            if tech_buy or sig.get("strength", 0) > 0.85:
                self._open_trade(coin, "long", f"Hype sinyali + teknik onay: {sig.get('reason','')}")
