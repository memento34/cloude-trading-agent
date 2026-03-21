
"""
ELİMİNATÖR — Her gün performansları değerlendirir
En iyiler ödüllenir, kötüler elenir
"""
import logging
from datetime import datetime, timedelta
from config.settings import ELIMINATION, INITIAL_BALANCE

logger = logging.getLogger(__name__)

class Eliminator:
    def __init__(self, agents: dict, paper_traders: dict, risk_manager):
        self.agents = agents
        self.paper_traders = paper_traders
        self.risk_manager = risk_manager
        self.elimination_log = []

    def daily_check(self, current_prices: dict):
        """Her gün gece çalışır"""
        logger.info("🏆 ELİMİNATÖR günlük değerlendirme başlıyor...")
        results = []
        for agent_id, trader in self.paper_traders.items():
            stats = trader.get_stats(current_prices)
            # Ardışık kayıp günü kontrolü
            if stats["consecutive_loss_days"] >= ELIMINATION["consecutive_loss_days_freeze"]:
                if not trader.is_frozen and not trader.is_eliminated:
                    trader.is_frozen = True
                    msg = f"[{agent_id}] ❄️  DONDURULDU: {stats['consecutive_loss_days']} gün üst üste zarar"
                    logger.warning(msg)
                    self.elimination_log.append({"time": datetime.now().isoformat(), "event": msg})
            # Max drawdown kontrolü
            if stats["max_drawdown_pct"] >= ELIMINATION["max_drawdown_emergency_stop"] * 100:
                if not trader.is_eliminated:
                    trader.is_eliminated = True
                    trader.force_close_all(current_prices)
                    msg = f"[{agent_id}] 🚫 ELİNDİ: Max drawdown %{stats['max_drawdown_pct']:.1f}"
                    logger.error(msg)
                    self.elimination_log.append({"time": datetime.now().isoformat(), "event": msg})
            results.append((agent_id, stats))

        # Haftalık değerlendirme (Pazar günleri)
        if datetime.now().weekday() == 6:
            self._weekly_evaluation(results, current_prices)

        # Risk manager günlük sıfırlama
        self.risk_manager.reset_daily()
        return results

    def _weekly_evaluation(self, results: list, current_prices: dict):
        """Haftalık sıralama ve bütçe ayarlaması"""
        logger.info("📊 HAFTALIK DEĞERLENDİRME başlıyor...")
        # PnL'e göre sırala (elinen ve dondurulmuş hariç)
        active = [(aid, s) for aid, s in results
                  if not self.paper_traders[aid].is_eliminated]
        active.sort(key=lambda x: x[1]["pnl_pct"], reverse=True)

        for rank, (agent_id, stats) in enumerate(active, 1):
            trader = self.paper_traders[agent_id]
            old_balance = trader.initial_balance
            if rank == 1:
                # 1. sıra: bütçe artır
                new_balance = old_balance * (1 + ELIMINATION["weekly_rank_budget_boost"])
                trader.initial_balance = new_balance
                trader.balance += (new_balance - old_balance)
                msg = f"[{agent_id}] 🥇 1. sıra! Bütçe ${old_balance:.0f} → ${new_balance:.0f}"
            elif rank <= 3:
                msg = f"[{agent_id}] 🥈 {rank}. sıra, bütçe aynı kalıyor"
            else:
                # Alt sıralar: bütçe azalt
                new_balance = old_balance * (1 - ELIMINATION["weekly_rank_budget_cut"])
                trader.initial_balance = new_balance
                trader.balance = max(0, trader.balance - (old_balance - new_balance))
                msg = f"[{agent_id}] ⬇️  {rank}. sıra, bütçe ${old_balance:.0f} → ${new_balance:.0f}"
            # 7 günde -%5'ten fazla kayıp = elinme
            if stats["pnl_pct"] <= ELIMINATION["weekly_loss_elimination"] * 100:
                trader.is_eliminated = True
                trader.force_close_all(current_prices)
                msg += f" | 🚫 ELİNDİ (Haftalık PnL: %{stats['pnl_pct']:.1f})"
            logger.info(msg)
            self.elimination_log.append({"time": datetime.now().isoformat(), "event": msg})

    def get_leaderboard(self, current_prices: dict) -> list:
        """Anlık sıralama tablosu"""
        results = []
        for agent_id, trader in self.paper_traders.items():
            stats = trader.get_stats(current_prices)
            score = self._calculate_score(stats)
            results.append({**stats, "score": round(score, 2)})
        results.sort(key=lambda x: (x["is_eliminated"], x["is_frozen"], -x["score"]))
        return results

    def _calculate_score(self, stats: dict) -> float:
        """Performans skoru hesapla"""
        if stats["is_eliminated"]:
            return -999
        win_score = stats["win_rate"] * 0.3
        pnl_score = max(-50, min(50, stats["pnl_pct"])) * 0.4
        dd_score = max(0, 10 - stats["max_drawdown_pct"]) * 0.3
        return win_score + pnl_score + dd_score

    def get_log(self, limit: int = 20) -> list:
        return self.elimination_log[-limit:]

eliminator_instance = None

def get_eliminator():
    return eliminator_instance
