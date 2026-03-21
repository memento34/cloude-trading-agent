
"""
BASE AGENT v4 — Fiyatları PriceCache'den alır, HTTP isteği yapmaz
"""
import logging
logger = logging.getLogger(__name__)

class BaseAgent:
    def __init__(self, agent_id, config, paper_trader,
                 signal_hub, risk_manager, exchange, coins):
        self.agent_id = agent_id
        self.config   = config
        self.trader   = paper_trader
        self.hub      = signal_hub
        self.risk     = risk_manager
        self.exchange = exchange
        self.coins    = coins
        # Fiyatlar dışarıdan inject edilir (run metodunda)
        self._prices  = {}

    def run(self, prices: dict = None):
        """prices: merkezi cache'den gelen fiyatlar"""
        if self.trader.is_eliminated or self.trader.is_frozen:
            return
        if prices:
            self._prices = prices
        try:
            self._close_positions_check()
            self._look_for_trades()
        except Exception as e:
            logger.error(f"[{self.agent_id}] run hatası: {e}")

    def _close_positions_check(self):
        closed = self.trader.check_and_close_positions(self._prices)
        for trade in closed:
            self.risk.register_close(
                trade["coin"], self.agent_id,
                trade.get("pnl", 0), self.trader.initial_balance
            )

    def _get_price(self, coin: str) -> float | None:
        return self._prices.get(coin)

    def _can_trade_now(self, coin: str) -> bool:
        ok, _ = self.risk.can_open_trade(coin, self.agent_id)
        if not ok:
            return False
        if len(self.trader.positions) >= self.config.get("max_open_trades", 3):
            return False
        regime = self.hub.get_regime()
        allowed = self.config.get("works_in_regimes", ["ANY"])
        if "ANY" not in allowed and regime.get("regime") not in allowed:
            return False
        return True

    def _open_trade(self, coin: str, side: str, reason: str):
        price = self._get_price(coin)
        if not price or price <= 0:
            return
        ok, msg = self.risk.can_open_trade(coin, self.agent_id)
        if not ok:
            return
        result = self.trader.open_trade(
            coin=coin, side=side,
            size_pct=self.config.get("max_position_pct", 0.10),
            current_price=price,
            stop_loss_pct=self.config.get("stop_loss_pct", 0.02),
            take_profit_pct=self.config.get("take_profit_pct", 0.03),
        )
        if result:
            self.risk.register_open(coin, self.agent_id)
            logger.info(f"[{self.agent_id}] 📈 {side.upper()} {coin} @ {price:.4f} | {reason[:60]}")

    def _look_for_trades(self):
        raise NotImplementedError
