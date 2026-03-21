import os
from dotenv import load_dotenv
load_dotenv()

OKX_API_KEY        = os.getenv("OKX_API_KEY", "")
OKX_SECRET_KEY     = os.getenv("OKX_SECRET_KEY", "")
OKX_PASSPHRASE     = os.getenv("OKX_PASSPHRASE", "")
PAPER_TRADING      = os.getenv("PAPER_TRADING", "True").lower() == "true"
INITIAL_BALANCE    = float(os.getenv("INITIAL_BALANCE", "10000"))   # $10k / agent
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
CMC_API_KEY        = os.getenv("CMC_API_KEY", "")

ORACLE_INTERVAL_MINUTES = 5    # OHLCV fetch ağır → 5 dk
AGENT_INTERVAL_MINUTES  = 5    # Fiyat cache 5 dk'da bir güncellenir
ELIMINATOR_HOUR         = 23

TOP_COINS = [
    "BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT",
    "ADA/USDT","DOGE/USDT","AVAX/USDT","DOT/USDT","MATIC/USDT",
    "LINK/USDT","LTC/USDT","UNI/USDT","ATOM/USDT","XLM/USDT",
    "ETC/USDT","NEAR/USDT","APT/USDT","FIL/USDT","ARB/USDT",
    "OP/USDT","SUI/USDT","INJ/USDT","TIA/USDT","SEI/USDT",
    "PEPE/USDT","WIF/USDT","JUP/USDT","IMX/USDT","WLD/USDT",
    "BLUR/USDT","ORDI/USDT","CFX/USDT","SAND/USDT","MANA/USDT",
    "AXS/USDT","GALA/USDT","CHZ/USDT","AAVE/USDT","MKR/USDT",
    "SNX/USDT","CRV/USDT","LDO/USDT","RUNE/USDT","THETA/USDT",
    "VET/USDT","FTM/USDT","GRT/USDT","ENS/USDT","CAKE/USDT",
]

# Global risk — paper trade için biraz gevşetildi
GLOBAL_RISK = {
    "max_single_trade_pct":  0.03,   # Tek işlem maks %3
    "max_daily_loss_pct":    0.10,   # Günlük maks %10 kayıp
    "max_same_coin_agents":  3,      # Aynı coin'de maks 3 agent
    "pause_on_btc_move_pct": 7.0,   # BTC %7 harekette dur
}

# ─────────────────────────────────────────────────────────────
# 12 AGENT — 6 orijinal (güçlendirilmiş) + 6 yeni
# ─────────────────────────────────────────────────────────────
AGENT_CONFIGS = {

    # ── ORİJİNAL 6 (geliştirilmiş) ───────────────────────────

    "SENTINEL": {
        "display_name": "Sentinel 🛡️",
        "max_position_pct": 0.10,
        "stop_loss_pct":    0.015,
        "take_profit_pct":  0.030,
        "min_signal_strength": 0.75,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","VOLATILE","ANY"],
        "use_hype_signals": False,
    },
    "MOMENTUM": {
        "display_name": "Momentum 🚀",
        "max_position_pct": 0.10,
        "stop_loss_pct":    0.020,
        "take_profit_pct":  0.050,
        "min_signal_strength": 0.58,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","VOLATILE","ANY"],
        "use_hype_signals": True,
    },
    "BOUNCER": {
        "display_name": "Bouncer 🏀",
        "max_position_pct": 0.12,
        "stop_loss_pct":    0.020,
        "take_profit_pct":  0.025,
        "min_signal_strength": 0.60,
        "max_open_trades": 4,
        "works_in_regimes": ["RANGE","VOLATILE","ANY"],
        "use_hype_signals": False,
        "rsi_oversold": 32,
    },
    "BREAKOUT": {
        "display_name": "Breakout 💥",
        "max_position_pct": 0.10,
        "stop_loss_pct":    0.018,
        "take_profit_pct":  0.045,
        "min_signal_strength": 0.68,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","RANGE","ANY"],
        "use_hype_signals": False,
    },
    "SCALPER": {
        "display_name": "Scalper ⚡",
        "max_position_pct": 0.08,
        "stop_loss_pct":    0.010,
        "take_profit_pct":  0.015,
        "min_signal_strength": 0.52,
        "max_open_trades": 5,
        "works_in_regimes": ["TRENDING_BULL","RANGE","VOLATILE","ANY"],
        "use_hype_signals": False,
        "allowed_coins": ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT"],
    },
    "SYNTHESIZER": {
        "display_name": "Synthesizer 🧠",
        "max_position_pct": 0.15,
        "stop_loss_pct":    0.022,
        "take_profit_pct":  0.040,
        "min_signal_strength": 0.68,
        "max_open_trades": 4,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","RANGE","VOLATILE","ANY"],
        "use_hype_signals": True,
        "min_oracle_agreement": 2,
    },

    # ── YENİ 6 ────────────────────────────────────────────────

    "TREND_RIDER": {
        # EMA20/EMA50 golden cross bölgesinde + EMA200 filtresi
        "display_name": "Trend Rider 🏄",
        "max_position_pct": 0.12,
        "stop_loss_pct":    0.025,
        "take_profit_pct":  0.060,
        "min_signal_strength": 0.65,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","ANY"],
        "use_hype_signals": False,
    },
    "MEAN_REVERTER": {
        # BB + RSI + CCI + StochRSI aşırı değerlerini fade eder
        "display_name": "Mean Reverter ↩️",
        "max_position_pct": 0.10,
        "stop_loss_pct":    0.018,
        "take_profit_pct":  0.022,
        "min_signal_strength": 0.58,
        "max_open_trades": 5,
        "works_in_regimes": ["RANGE","ANY"],
        "use_hype_signals": False,
        "oversold_min_score": 2,   # kaç indikatör aşırı satımı onaylamalı
    },
    "VOLUME_SHARK": {
        # Hacim patlaması + OBV yönü + momentum uyuşması
        "display_name": "Volume Shark 🦈",
        "max_position_pct": 0.10,
        "stop_loss_pct":    0.020,
        "take_profit_pct":  0.040,
        "min_signal_strength": 0.60,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","VOLATILE","ANY"],
        "use_hype_signals": False,
        "min_vol_ratio": 2.0,
    },
    "CONTRARIAN": {
        # RSI/StochRSI/Williams aşırı değerlerini ters yönde fade eder
        # Fear & Greed extremlerini de kullanır
        "display_name": "Contrarian 🦅",
        "max_position_pct": 0.08,
        "stop_loss_pct":    0.015,
        "take_profit_pct":  0.025,
        "min_signal_strength": 0.52,
        "max_open_trades": 4,
        "works_in_regimes": ["RANGE","VOLATILE","ANY"],
        "use_hype_signals": True,
        "rsi_extreme_buy":   22,
        "rsi_extreme_sell":  78,
        "fear_greed_buy":    18,
        "fear_greed_sell":   82,
        "min_contra_score":  2,    # kaç sinyal onaylamalı
    },
    "ICHIMOKU_SENSEI": {
        # Ichimoku bulut + Tenkan/Kijun + MACD konfirmasyonu
        "display_name": "Ichimoku Sensei 🌸",
        "max_position_pct": 0.12,
        "stop_loss_pct":    0.022,
        "take_profit_pct":  0.050,
        "min_signal_strength": 0.70,
        "max_open_trades": 3,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","ANY"],
        "use_hype_signals": False,
    },
    "SWING_TRADER": {
        # N ardışık aynı yönlü sinyal + EMA200 filtresi — büyük hamleleri yakalar
        "display_name": "Swing Trader 🎯",
        "max_position_pct": 0.15,
        "stop_loss_pct":    0.030,
        "take_profit_pct":  0.080,
        "min_signal_strength": 0.70,
        "max_open_trades": 2,
        "works_in_regimes": ["TRENDING_BULL","TRENDING_BEAR","RANGE","VOLATILE","ANY"],
        "use_hype_signals": True,
        "min_consecutive_signals": 2,
        "allowed_coins": [
            "BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT",
            "AVAX/USDT","LINK/USDT","DOT/USDT","ATOM/USDT","NEAR/USDT",
            "INJ/USDT","AAVE/USDT","MKR/USDT","RUNE/USDT","ARB/USDT",
        ],
    },
}

ELIMINATION = {
    "consecutive_loss_days_freeze": 3,
    "max_drawdown_emergency_stop":  0.15,   # %15 drawdown → elinme
    "weekly_loss_elimination":      -0.08,  # haftalık -%8 → elinme
    "weekly_rank_budget_boost":     0.25,   # 1. sıra +%25 bütçe
    "weekly_rank_budget_cut":       0.10,   # alt sıralar -%10
}
