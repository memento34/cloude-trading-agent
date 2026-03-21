
"""
SYNTHESIZER — En az 2 oracle aynı yönde sinyal vermeli
En sofistike agent, birden fazla kaynağı birleştirir
"""
from agents.base_agent import BaseAgent
import logging
logger = logging.getLogger(__name__)

class SynthesizerAgent(BaseAgent):
    def _look_for_trades(self):
        min_agreement = self.config.get("min_oracle_agreement", 2)
        for coin in self.config.get("allowed_coins", self.coins):
            if not self._can_trade_now(coin) or coin in self.trader.positions:
                continue
            buy_votes  = 0
            sell_votes = 0
            reasons    = []
            # Teknik oracle oyu
            tech = self.hub.get_signals_for_coin(coin, source="technical", limit=3)
            if tech:
                last = tech[-1]
                if last.get("signal") == "BUY" and last.get("strength",0) > 0.6:
                    buy_votes += 1
                    reasons.append(f"Teknik: {last.get('reason','')[:30]}")
                elif last.get("signal") == "SELL" and last.get("strength",0) > 0.6:
                    sell_votes += 1
            # Hype oracle oyu
            if self.config.get("use_hype_signals"):
                hype = self.hub.get_signals_for_coin(coin, source="hype", limit=3)
                if any(h.get("signal") == "HYPE_ALERT" and h.get("strength",0) > 0.65 for h in hype):
                    buy_votes += 1
                    reasons.append("Hype sinyali")
            # Rejim oylaması
            regime = self.hub.get_regime()
            recommended = regime.get("recommended_strategies", [])
            if "SYNTHESIZER" in recommended or not recommended:
                buy_votes += 0.5  # Hafif bonus

            if buy_votes >= min_agreement:
                self._open_trade(coin, "long", f"Synthesizer ({buy_votes} oy): {' | '.join(reasons)}")
            elif sell_votes >= min_agreement:
                self._open_trade(coin, "short", f"Synthesizer ({sell_votes} satış oyu)")
