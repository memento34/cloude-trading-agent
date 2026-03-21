
"""
GLOBAL RİSK YÖNETİCİSİ — Tüm sistemi korur, hiçbir agent aşamaz
"""
import threading
import logging
from datetime import datetime
from config.settings import GLOBAL_RISK

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._trading_paused = False
        self._pause_reason = ""
        self._daily_system_loss = 0.0
        self._coin_agent_count: dict[str, int] = {}  # coin -> kaç agent pozisyon açmış
        self._last_btc_price = None
        self._emergency_stop = False

    def update_btc_price(self, price: float):
        """BTC fiyatı büyük değişirse tüm sistemi durdur"""
        if self._last_btc_price and price > 0:
            change_pct = abs(price - self._last_btc_price) / self._last_btc_price * 100
            if change_pct >= GLOBAL_RISK["pause_on_btc_move_pct"]:
                self.pause_trading(f"BTC {change_pct:.1f}% hareket etti (son 5dk)")
            elif self._trading_paused and "BTC" in self._pause_reason:
                self.resume_trading()
        self._last_btc_price = price

    def can_open_trade(self, coin: str, agent_id: str) -> tuple[bool, str]:
        if self._emergency_stop:
            return False, "ACİL DURDURMA aktif"
        if self._trading_paused:
            return False, f"İşlem duraklatıldı: {self._pause_reason}"
        with self._lock:
            count = self._coin_agent_count.get(coin, 0)
            if count >= GLOBAL_RISK["max_same_coin_agents"]:
                return False, f"{coin} için zaten {count} agent pozisyonda (max {GLOBAL_RISK['max_same_coin_agents']})"
        return True, "OK"

    def register_open(self, coin: str, agent_id: str):
        with self._lock:
            self._coin_agent_count[coin] = self._coin_agent_count.get(coin, 0) + 1

    def register_close(self, coin: str, agent_id: str, pnl: float, initial_balance: float):
        with self._lock:
            if coin in self._coin_agent_count:
                self._coin_agent_count[coin] = max(0, self._coin_agent_count[coin] - 1)
            self._daily_system_loss += pnl
        # Günlük kayıp limiti kontrolü
        if initial_balance > 0:
            loss_pct = abs(self._daily_system_loss) / initial_balance
            if self._daily_system_loss < 0 and loss_pct >= GLOBAL_RISK["max_daily_loss_pct"]:
                self.emergency_stop(f"Günlük kayıp limiti aşıldı: %{loss_pct*100:.1f}")

    def pause_trading(self, reason: str):
        self._trading_paused = True
        self._pause_reason = reason
        logger.warning(f"⏸️  İşlem DURAKLATILDI: {reason}")

    def resume_trading(self):
        self._trading_paused = False
        self._pause_reason = ""
        logger.info("▶️  İşlem DEVAM EDİYOR")

    def emergency_stop(self, reason: str):
        self._emergency_stop = True
        self._trading_paused = True
        self._pause_reason = f"ACİL DURUŞ: {reason}"
        logger.critical(f"🛑 ACİL DURUŞ: {reason}")

    def reset_daily(self):
        """Her gün gece çalışır, günlük sayaçları sıfırlar"""
        with self._lock:
            self._daily_system_loss = 0.0
        if self._trading_paused and "günlük kayıp" in self._pause_reason.lower():
            self.resume_trading()
        logger.info("✅ Günlük risk sayaçları sıfırlandı")

    def get_status(self) -> dict:
        return {
            "trading_paused": self._trading_paused,
            "pause_reason": self._pause_reason,
            "emergency_stop": self._emergency_stop,
            "daily_system_loss": round(self._daily_system_loss, 2),
            "active_coins": {k: v for k, v in self._coin_agent_count.items() if v > 0},
            "last_btc_price": self._last_btc_price,
        }

risk_manager = RiskManager()
