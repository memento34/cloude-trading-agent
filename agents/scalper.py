
"""
SCALPER — Sadece BTC/ETH/SOL, küçük ve hızlı kazançlar
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class ScalperAgent(BaseAgent):
    def _look_for_trades(self):
        allowed = self.config.get("allowed_coins", ["BTC/USDT","ETH/USDT","SOL/USDT"])
        for coin in allowed:
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            signals = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if not signals:
                continue
            latest = signals[-1]
            # Scalper daha düşük eşikle giriyor ama daha hızlı çıkıyor (config'de SL/TP dar)
            if latest.get("strength", 0) < self.config.get("min_signal_strength", 0.55):
                continue
            direction = "long" if latest.get("signal") == "BUY" else "short"
            self._open_trade(coin, direction, f"Scalp: {latest.get('reason','')[:50]}")
