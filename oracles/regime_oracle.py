"""
REJİM ORACLE v2 — Piyasanın genel durumunu belirler
12 agent için öneri listesi güncellendi
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class RegimeOracle:
    def __init__(self, exchange, signal_hub):
        self.exchange = exchange
        self.signal_hub = signal_hub
        self.name = "regime"
        self._current_regime = "ANY"

    def run(self):
        logger.info("🌐 Rejim Oracle çalışıyor...")
        try:
            regime = self._detect_regime()
            self.signal_hub.set_regime(regime)
            self._current_regime = regime["regime"]
            logger.info(f"🌐 Piyasa Rejimi: {regime['regime']} | Volatilite: {regime['volatility']}")
        except Exception as e:
            logger.error(f"Rejim Oracle hatası: {e}")

    def _detect_regime(self) -> dict:
        btc_daily = self.exchange.fetch_ohlcv("BTC/USDT", "1d", limit=30)
        btc_4h    = self.exchange.fetch_ohlcv("BTC/USDT", "4h", limit=50)

        df_d  = pd.DataFrame(btc_daily, columns=["ts","open","high","low","close","vol"])
        df_4h = pd.DataFrame(btc_4h,   columns=["ts","open","high","low","close","vol"])

        close_d  = df_d["close"].astype(float)
        close_4h = df_4h["close"].astype(float)

        ma7  = float(close_d.rolling(7).mean().iloc[-1])
        ma20 = float(close_d.rolling(20).mean().iloc[-1])
        current_btc = float(close_d.iloc[-1])

        vol_pct = float(close_4h.pct_change().std() * 100)
        ret_7d  = (current_btc - float(close_d.iloc[-7])) / float(close_d.iloc[-7]) * 100

        # ADX-benzeri trend gücü (EMA20/EMA50 ayrışması)
        ema20_d = float(close_d.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50_d = float(close_d.ewm(span=50, adjust=False).mean().iloc[-1])
        trend_strength = abs(ema20_d - ema50_d) / ema50_d * 100 if ema50_d > 0 else 0

        if vol_pct > 3.0:
            regime = "VOLATILE"
        elif ma7 > ma20 and ret_7d > 3 and trend_strength > 0.5:
            regime = "TRENDING_BULL"
        elif ma7 < ma20 and ret_7d < -3 and trend_strength > 0.5:
            regime = "TRENDING_BEAR"
        else:
            regime = "RANGE"

        volatility = "HIGH" if vol_pct > 3 else ("MEDIUM" if vol_pct > 1.5 else "LOW")

        return {
            "regime": regime,
            "volatility": volatility,
            "btc_price": current_btc,
            "ma7": round(ma7, 2),
            "ma20": round(ma20, 2),
            "ret_7d_pct": round(ret_7d, 2),
            "vol_4h_pct": round(vol_pct, 3),
            "trend_strength_pct": round(trend_strength, 3),
            "recommended_strategies": self._recommend(regime),
        }

    def _recommend(self, regime: str) -> list:
        mapping = {
            "TRENDING_BULL": [
                "SENTINEL","MOMENTUM","BREAKOUT","SYNTHESIZER",
                "TREND_RIDER","VOLUME_SHARK","ICHIMOKU_SENSEI","SWING_TRADER"
            ],
            "TRENDING_BEAR": [
                "SENTINEL","BREAKOUT","SYNTHESIZER",
                "TREND_RIDER","VOLUME_SHARK","ICHIMOKU_SENSEI"
            ],
            "RANGE": [
                "BOUNCER","SCALPER","BREAKOUT","SYNTHESIZER",
                "MEAN_REVERTER","CONTRARIAN","SWING_TRADER"
            ],
            "VOLATILE": [
                "MOMENTUM","BOUNCER","SCALPER","SYNTHESIZER",
                "VOLUME_SHARK","CONTRARIAN","MEAN_REVERTER"
            ],
        }
        return mapping.get(regime, ["SYNTHESIZER","SCALPER"])
