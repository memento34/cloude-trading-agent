"""
PAPER TRADER — Gerçek işlem yok, sanal portföy takibi
Her agent'ın kendi PaperTrader instance'ı vardır

FIX: threading.Lock() → threading.RLock()
     get_stats() → get_total_equity() → get_open_positions_value() zinciri
     aynı thread'den Lock'u tekrar acquire etmeye çalışıyor → deadlock.
"""
import threading
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Position:
    def __init__(self, coin, side, entry_price, size_usd, stop_loss_pct, take_profit_pct):
        self.coin = coin
        self.side = side
        self.entry_price = entry_price
        self.size_usd = size_usd
        self.quantity = size_usd / entry_price
        self.stop_loss_price = (
            entry_price * (1 - stop_loss_pct) if side == "long"
            else entry_price * (1 + stop_loss_pct)
        )
        self.take_profit_price = (
            entry_price * (1 + take_profit_pct) if side == "long"
            else entry_price * (1 - take_profit_pct)
        )
        self.opened_at = datetime.now().isoformat()
        self.status = "open"
        self.pnl = 0.0

    def check_close(self, current_price: float) -> str | None:
        if self.side == "long":
            if current_price >= self.take_profit_price:
                return "take_profit"
            if current_price <= self.stop_loss_price:
                return "stop_loss"
        else:
            if current_price <= self.take_profit_price:
                return "take_profit"
            if current_price >= self.stop_loss_price:
                return "stop_loss"
        return None

    def calculate_pnl(self, current_price: float) -> float:
        if self.side == "long":
            return (current_price - self.entry_price) / self.entry_price * self.size_usd
        else:
            return (self.entry_price - current_price) / self.entry_price * self.size_usd

    def to_dict(self) -> dict:
        return {
            "coin": self.coin, "side": self.side,
            "entry_price": self.entry_price, "size_usd": self.size_usd,
            "quantity": self.quantity, "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "opened_at": self.opened_at, "status": self.status, "pnl": self.pnl
        }


class PaperTrader:
    def __init__(self, agent_id: str, initial_balance: float):
        self.agent_id = agent_id
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions: dict[str, Position] = {}
        self.trade_history: list[dict] = []
        self.daily_pnl: dict[str, float] = {}
        self.is_frozen = False
        self.is_eliminated = False
        # ── BUGFIX: Lock() → RLock() ──────────────────────────────────────────
        # get_stats() lock altında get_total_equity() → get_open_positions_value()
        # çağırıyor. get_open_positions_value() de aynı lock'u acquire etmeye
        # çalışıyor. threading.Lock() re-entrant değil → thread sonsuza kilitlenir.
        # threading.RLock() aynı thread'den tekrar acquire edilebilir → deadlock yok.
        self._lock = threading.RLock()

    def can_open_trade(self, coin: str, size_usd: float) -> tuple[bool, str]:
        if self.is_eliminated:
            return False, "Agent elindi"
        if self.is_frozen:
            return False, "Agent donduruldu"
        if coin in self.positions:
            return False, f"{coin} için zaten açık pozisyon var"
        if size_usd > self.balance:
            return False, f"Yetersiz bakiye: {self.balance:.2f} < {size_usd:.2f}"
        if self.balance <= 0:
            return False, "Bakiye sıfır"
        return True, "OK"

    def open_trade(self, coin: str, side: str, size_pct: float,
                   current_price: float, stop_loss_pct: float, take_profit_pct: float) -> dict | None:
        size_usd = self.balance * size_pct
        ok, reason = self.can_open_trade(coin, size_usd)
        if not ok:
            logger.debug(f"[{self.agent_id}] Trade açılamadı: {reason}")
            return None
        with self._lock:
            pos = Position(coin, side, current_price, size_usd, stop_loss_pct, take_profit_pct)
            self.positions[coin] = pos
            self.balance -= size_usd
            logger.info(f"[{self.agent_id}] AÇILDI {side.upper()} {coin} @ {current_price:.4f} | Boyut: ${size_usd:.2f}")
            return pos.to_dict()

    def check_and_close_positions(self, current_prices: dict) -> list[dict]:
        closed = []
        with self._lock:
            for coin, pos in list(self.positions.items()):
                price = current_prices.get(coin)
                if not price:
                    continue
                close_reason = pos.check_close(price)
                if close_reason:
                    pnl = pos.calculate_pnl(price)
                    pos.pnl = pnl
                    pos.status = close_reason
                    self.balance += pos.size_usd + pnl
                    trade_record = {
                        **pos.to_dict(), "close_price": price,
                        "closed_at": datetime.now().isoformat(),
                        "agent_id": self.agent_id
                    }
                    self.trade_history.append(trade_record)
                    today = datetime.now().strftime("%Y-%m-%d")
                    self.daily_pnl[today] = self.daily_pnl.get(today, 0) + pnl
                    del self.positions[coin]
                    closed.append(trade_record)
                    emoji = "✅" if pnl > 0 else "❌"
                    logger.info(f"[{self.agent_id}] {emoji} KAPANDI {coin} @ {price:.4f} | PnL: ${pnl:.2f} ({close_reason})")
        return closed

    def force_close_all(self, current_prices: dict):
        with self._lock:
            for coin, pos in list(self.positions.items()):
                price = current_prices.get(coin, pos.entry_price)
                pnl = pos.calculate_pnl(price)
                self.balance += pos.size_usd + pnl
                trade_record = {
                    **pos.to_dict(), "close_price": price,
                    "closed_at": datetime.now().isoformat(),
                    "close_reason": "force_close", "agent_id": self.agent_id
                }
                self.trade_history.append(trade_record)
            self.positions.clear()

    def get_open_positions_value(self, current_prices: dict) -> float:
        """RLock ile aynı thread'den güvenli çağrılabilir."""
        total = 0
        with self._lock:
            for coin, pos in self.positions.items():
                price = current_prices.get(coin, pos.entry_price)
                total += pos.size_usd + pos.calculate_pnl(price)
        return total

    def get_total_equity(self, current_prices: dict) -> float:
        return self.balance + self.get_open_positions_value(current_prices)

    def get_stats(self, current_prices: dict = None) -> dict:
        if current_prices is None:
            current_prices = {}
        with self._lock:
            total_trades = len(self.trade_history)
            winning = [t for t in self.trade_history if t.get("pnl", 0) > 0]
            win_rate = len(winning) / total_trades * 100 if total_trades > 0 else 0
            total_pnl = sum(t.get("pnl", 0) for t in self.trade_history)
            pnl_pct = total_pnl / self.initial_balance * 100
            today = datetime.now().strftime("%Y-%m-%d")
            today_pnl = self.daily_pnl.get(today, 0)

            # Açık pozisyon değerini lock altında hesapla (RLock: re-entrant güvenli)
            open_value = 0.0
            for coin, pos in self.positions.items():
                price = current_prices.get(coin, pos.entry_price)
                open_value += pos.size_usd + pos.calculate_pnl(price)
            equity = self.balance + open_value

            max_drawdown = (self.initial_balance - min(
                [self.initial_balance] + [
                    sum(t.get("pnl", 0) for t in self.trade_history[:i + 1]) + self.initial_balance
                    for i in range(len(self.trade_history))
                ]
            )) / self.initial_balance * 100

            return {
                "agent_id": self.agent_id,
                "balance": round(self.balance, 2),
                "equity": round(equity, 2),
                "initial_balance": self.initial_balance,
                "total_pnl": round(total_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "today_pnl": round(today_pnl, 2),
                "total_trades": total_trades,
                "win_rate": round(win_rate, 1),
                "open_positions": len(self.positions),
                "is_frozen": self.is_frozen,
                "is_eliminated": self.is_eliminated,
                "max_drawdown_pct": round(max_drawdown, 2),
                "consecutive_loss_days": self._count_consecutive_loss_days(),
            }

    def _count_consecutive_loss_days(self) -> int:
        if not self.daily_pnl:
            return 0
        count = 0
        for day_pnl in reversed(sorted(self.daily_pnl.items())):
            if day_pnl[1] < 0:
                count += 1
            else:
                break
        return count
