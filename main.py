"""
MAIN v5 — 12 Agent, $10k/agent, zengin teknik sinyal
"""
import os, logging, threading, time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

from config.settings import (
    OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE,
    TOP_COINS, INITIAL_BALANCE, AGENT_CONFIGS,
    ORACLE_INTERVAL_MINUTES, AGENT_INTERVAL_MINUTES,
    ELIMINATOR_HOUR, DASHBOARD_PASSWORD, CMC_API_KEY, PAPER_TRADING
)
from core.signal_hub        import signal_hub
from core.paper_trader      import PaperTrader
from core.risk_manager      import risk_manager
from core.eliminator        import Eliminator
from core.custom_exchange   import CustomExchange
from core.price_cache       import price_cache

from oracles.technical_oracle import TechnicalOracle
from oracles.hype_oracle      import HypeOracle
from oracles.regime_oracle    import RegimeOracle

# ── Orijinal 6 agent ──────────────────────────────────────────
from agents.sentinel    import SentinelAgent
from agents.momentum    import MomentumAgent
from agents.bouncer     import BouncerAgent
from agents.breakout    import BreakoutAgent
from agents.scalper     import ScalperAgent
from agents.synthesizer import SynthesizerAgent
# ── Yeni 6 agent ──────────────────────────────────────────────
from agents.trend_rider      import TrendRiderAgent
from agents.mean_reverter    import MeanReverterAgent
from agents.volume_shark     import VolumeSharkAgent
from agents.contrarian       import ContrarianAgent
from agents.ichimoku_sensei  import IchimokuSenseiAgent
from agents.swing_trader     import SwingTraderAgent

from dashboard.app import create_app
from apscheduler.schedulers.background import BackgroundScheduler

# ── Exchange ──────────────────────────────────────────────────
exchange = CustomExchange()
try:
    t = exchange.fetch_ticker("BTC/USDT")
    logger.info(f"✅ Exchange OK — BTC: ${t['last']:.0f} [{exchange.get_source()}]")
except Exception as e:
    logger.warning(f"Exchange test: {e}")

# ── Paper Traders — $10k/agent ─────────────────────────────────
paper_traders = {aid: PaperTrader(aid, INITIAL_BALANCE) for aid in AGENT_CONFIGS}
total_capital = INITIAL_BALANCE * len(paper_traders)
logger.info(f"✅ {len(paper_traders)} paper trader | ${INITIAL_BALANCE:,.0f}/agent | Toplam: ${total_capital:,.0f}")

# ── Oracles ───────────────────────────────────────────────────
technical_oracle = TechnicalOracle(exchange, signal_hub, TOP_COINS)
hype_oracle      = HypeOracle(signal_hub, CMC_API_KEY)
regime_oracle    = RegimeOracle(exchange, signal_hub)

# ── 12 Agent ──────────────────────────────────────────────────
AGENT_CLASSES = {
    "SENTINEL":         SentinelAgent,
    "MOMENTUM":         MomentumAgent,
    "BOUNCER":          BouncerAgent,
    "BREAKOUT":         BreakoutAgent,
    "SCALPER":          ScalperAgent,
    "SYNTHESIZER":      SynthesizerAgent,
    "TREND_RIDER":      TrendRiderAgent,
    "MEAN_REVERTER":    MeanReverterAgent,
    "VOLUME_SHARK":     VolumeSharkAgent,
    "CONTRARIAN":       ContrarianAgent,
    "ICHIMOKU_SENSEI":  IchimokuSenseiAgent,
    "SWING_TRADER":     SwingTraderAgent,
}

agents = {}
for agent_id, AgentClass in AGENT_CLASSES.items():
    cfg = dict(AGENT_CONFIGS[agent_id])
    cfg["allowed_coins"] = cfg.get("allowed_coins", TOP_COINS)
    agents[agent_id] = AgentClass(
        agent_id=agent_id, config=cfg,
        paper_trader=paper_traders[agent_id],
        signal_hub=signal_hub, risk_manager=risk_manager,
        exchange=exchange, coins=TOP_COINS
    )
logger.info(f"✅ {len(agents)} agent: {list(agents.keys())}")

eliminator = Eliminator(agents, paper_traders, risk_manager)
import core.eliminator as elim_module
elim_module.eliminator_instance = eliminator

# ── Scheduler Jobs ────────────────────────────────────────────
def run_oracles():
    logger.info("⏰ Oracle döngüsü başlıyor...")
    ok = price_cache.update(exchange, TOP_COINS)
    if ok:
        prices = price_cache.get_all()
        btc = prices.get("BTC/USDT")
        if btc:
            risk_manager.update_btc_price(btc)
        logger.info(f"💰 {len(prices)} coin fiyatı cache'lendi | BTC: ${btc:.0f}" if btc else f"💰 {len(prices)} coin")
    for name, fn in [("Regime",    regime_oracle.run),
                     ("Technical", technical_oracle.run),
                     ("Hype",      hype_oracle.run)]:
        try:
            fn()
        except Exception as e:
            logger.error(f"{name} hatası: {e}")

def run_agents():
    logger.info("⏰ Agent döngüsü başlıyor...")
    prices = price_cache.get_all()
    if not prices:
        logger.warning("⚠️  Fiyat cache boş, oracle bekleniyor...")
        return

    regime = signal_hub.get_regime().get("regime", "ANY")
    logger.info(f"📊 {len(prices)} coin | Rejim: {regime}")

    for aid, agent in agents.items():
        try:
            agent.run(prices=prices)
            pos_count = len(agent.trader.positions)
            stats = agent.trader.get_stats(prices)
            status = (
                "❄️ DONDURULDU" if agent.trader.is_frozen
                else ("🚫 ELİNDİ" if agent.trader.is_eliminated else "✅")
            )
            logger.info(
                f"  [{aid:16s}] {status} | "
                f"pos={pos_count} | "
                f"pnl=${stats['total_pnl']:+.2f} | "
                f"equity=${stats['equity']:.0f} | "
                f"win={stats['win_rate']:.0f}%"
            )
        except Exception as e:
            logger.error(f"[{aid}] hata: {e}")

    logger.info("✅ Agent döngüsü tamamlandı")

def run_eliminator():
    try:
        eliminator.daily_check(price_cache.get_all())
    except Exception as e:
        logger.error(f"Eliminator: {e}")

# ── Scheduler ─────────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(run_oracles, "interval", minutes=ORACLE_INTERVAL_MINUTES,
                  id="oracles", coalesce=True, max_instances=1,
                  misfire_grace_time=120, next_run_time=datetime.now())
scheduler.add_job(run_agents, "interval", minutes=AGENT_INTERVAL_MINUTES,
                  id="agents", coalesce=True, max_instances=1,
                  misfire_grace_time=120,
                  next_run_time=datetime.fromtimestamp(time.time() + 35))
scheduler.add_job(run_eliminator, "cron", hour=ELIMINATOR_HOUR, minute=0,
                  id="eliminator", coalesce=True)
scheduler.start()
logger.info("✅ Scheduler başladı")

# ── Dashboard ─────────────────────────────────────────────────
flask_app = create_app(
    paper_traders=paper_traders, signal_hub=signal_hub,
    risk_manager=risk_manager, eliminator=eliminator,
    exchange=exchange, password=DASHBOARD_PASSWORD,
)

logger.info("=" * 65)
logger.info(f"🚀 Trading System v5 | Paper:{PAPER_TRADING} | {len(agents)} agent | {len(TOP_COINS)} coin")
logger.info(f"💰 Başlangıç: ${INITIAL_BALANCE:,.0f}/agent | Toplam: ${total_capital:,.0f}")
logger.info("=" * 65)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)
