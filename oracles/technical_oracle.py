"""
TEKNİK ORACLE v3 — Zengin sinyal metadata
12 farklı indikatör, her agent kendi ihtiyacına göre seçer.

Yeni sinyaller:
  rsi, stoch_rsi_k, williams_r, cci, macd_bull,
  bb_below/above/pct, ema20/50/200 durumu,
  ema_golden (cross bölgesi), ema_cross_bull/bear (taze cross),
  obv_trend, vol_ratio, atr_pct, momentum_5, ich_bull,
  buy_signals / sell_signals / total_signals sayaçları
"""
import logging, time
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger.warning("ta kütüphanesi yok — MACD/BB/Ichimoku devre dışı")


class TechnicalOracle:
    def __init__(self, exchange, signal_hub, coins):
        self.exchange   = exchange
        self.signal_hub = signal_hub
        self.coins      = coins
        self.name       = "technical"

    def run(self):
        logger.info(f"🔮 Teknik Oracle çalışıyor ({len(self.coins)} coin)...")
        count = 0
        for coin in self.coins:
            try:
                sig = self._analyze(coin)
                if sig:
                    self.signal_hub.publish(sig)
                    count += 1
                time.sleep(0.1)
            except Exception as e:
                logger.debug(f"Teknik analiz {coin}: {e}")
        logger.info(f"🔮 Teknik Oracle tamamlandı: {count} sinyal")

    # ──────────────────────────────────────────────────────────
    def _analyze(self, coin: str) -> dict | None:
        ohlcv = self.exchange.fetch_ohlcv(coin, "4h", limit=100)
        if not ohlcv or len(ohlcv) < 30:
            return None

        df = pd.DataFrame(ohlcv, columns=["ts","open","high","low","close","volume"])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]
        cp     = float(close.iloc[-1])   # current price

        # ── Temel indikatörler (her zaman hesaplanır) ─────────
        rsi_val  = self._rsi(close)
        stoch_k  = self._stoch_rsi_k(close)
        wR       = self._williams_r(high, low, close)
        cci_val  = self._cci(high, low, close)
        atr_val  = self._atr(high, low, close)
        atr_pct  = atr_val / cp * 100 if cp > 0 else 0.0
        mom5     = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(close) >= 6 else 0.0
        obv_t    = self._obv_trend(close, volume)

        # EMA'lar
        ema20  = float(close.ewm(span=20,  adjust=False).mean().iloc[-1])
        ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
        ema200 = float(close.ewm(span=min(200, len(close)), adjust=False).mean().iloc[-1])
        ema20p = float(close.ewm(span=20,  adjust=False).mean().iloc[-2])
        ema50p = float(close.ewm(span=50,  adjust=False).mean().iloc[-2])
        ema_golden_cross = (ema20 > ema50) and (ema20p <= ema50p)  # taze çapraz
        ema_death_cross  = (ema20 < ema50) and (ema20p >= ema50p)
        in_golden_zone   = ema20 > ema50   # bölge (cross olmasa da)

        # Volume
        vol_avg  = float(volume.iloc[-20:-1].mean()) if len(volume) >= 20 else float(volume.mean())
        vol_last = float(volume.iloc[-1])
        vol_rat  = vol_last / vol_avg if vol_avg > 0 else 1.0

        # ── ta kütüphanesi ────────────────────────────────────
        macd_bull = False
        bb_below  = False
        bb_above  = False
        bb_pct    = 0.5
        ich_bull  = None  # True=bull, False=bear, None=bulut içi

        if TA_AVAILABLE:
            try:
                mc  = ta.trend.MACD(close=close)
                ml_ = mc.macd()
                ms_ = mc.macd_signal()
                if len(ml_) >= 2 and len(ms_) >= 2:
                    macd_bull = float(ml_.iloc[-1]) > float(ms_.iloc[-1])
            except Exception:
                pass
            try:
                bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
                lb = float(bb.bollinger_lband().iloc[-1])
                ub = float(bb.bollinger_hband().iloc[-1])
                bw = ub - lb
                bb_below = cp < lb
                bb_above = cp > ub
                bb_pct   = (cp - lb) / bw if bw > 0 else 0.5
            except Exception:
                pass
            try:
                ich = ta.trend.IchimokuIndicator(high=high, low=low,
                                                  window1=9, window2=26, window3=52)
                sp_a = float(ich.ichimoku_a().iloc[-1])
                sp_b = float(ich.ichimoku_b().iloc[-1])
                cloud_top    = max(sp_a, sp_b)
                cloud_bottom = min(sp_a, sp_b)
                tenkan = float(ich.ichimoku_conversion_line().iloc[-1])
                kijun  = float(ich.ichimoku_base_line().iloc[-1])
                if cp > cloud_top:
                    ich_bull = tenkan > kijun
                elif cp < cloud_bottom:
                    ich_bull = False if tenkan < kijun else None
                else:
                    ich_bull = None   # bulut içi = belirsiz
            except Exception:
                pass

        # ── Sinyal toplama ────────────────────────────────────
        sigs, scores = [], []

        # RSI
        if rsi_val < 30:
            sigs.append(("BUY",  f"RSI={rsi_val:.0f}↓")); scores.append(min(0.95, 0.80 + (30-rsi_val)*0.01))
        elif rsi_val > 70:
            sigs.append(("SELL", f"RSI={rsi_val:.0f}↑")); scores.append(min(0.95, 0.80 + (rsi_val-70)*0.01))

        # Stochastic RSI
        if stoch_k < 0.15:
            sigs.append(("BUY",  f"StochRSI={stoch_k:.2f}")); scores.append(0.70)
        elif stoch_k > 0.85:
            sigs.append(("SELL", f"StochRSI={stoch_k:.2f}")); scores.append(0.70)

        # Williams %R
        if wR < -80:
            sigs.append(("BUY",  f"Wm%R={wR:.0f}")); scores.append(0.65)
        elif wR > -20:
            sigs.append(("SELL", f"Wm%R={wR:.0f}")); scores.append(0.65)

        # CCI
        if cci_val < -100:
            sigs.append(("BUY",  f"CCI={cci_val:.0f}")); scores.append(0.65)
        elif cci_val > 100:
            sigs.append(("SELL", f"CCI={cci_val:.0f}")); scores.append(0.65)

        if TA_AVAILABLE:
            # MACD
            sigs.append(("BUY" if macd_bull else "SELL", "MACD"))
            scores.append(0.68)
            # Bollinger
            if bb_below:
                sigs.append(("BUY",  "BB alt bant")); scores.append(0.65)
            elif bb_above:
                sigs.append(("SELL", "BB üst bant")); scores.append(0.65)
            # Ichimoku
            if ich_bull is True:
                sigs.append(("BUY",  "Ichimoku bull")); scores.append(0.78)
            elif ich_bull is False:
                sigs.append(("SELL", "Ichimoku bear")); scores.append(0.78)

        # EMA cross (taze)
        if ema_golden_cross:
            sigs.append(("BUY",  "EMA golden cross")); scores.append(0.82)
        elif ema_death_cross:
            sigs.append(("SELL", "EMA death cross"));  scores.append(0.82)
        elif in_golden_zone:
            sigs.append(("BUY",  "EMA golden zone"));  scores.append(0.60)
        else:
            sigs.append(("SELL", "EMA death zone"));   scores.append(0.58)

        # OBV + hacim
        if obv_t > 0 and vol_rat > 1.5:
            sigs.append(("BUY",  f"OBV↑ vol×{vol_rat:.1f}")); scores.append(0.63)
        elif obv_t < 0 and vol_rat > 1.5:
            sigs.append(("SELL", f"OBV↓ vol×{vol_rat:.1f}")); scores.append(0.63)

        # Momentum
        if mom5 > 3:
            sigs.append(("BUY",  f"Mom5={mom5:.1f}%")); scores.append(0.60)
        elif mom5 < -3:
            sigs.append(("SELL", f"Mom5={mom5:.1f}%")); scores.append(0.60)

        if not sigs:
            return None

        buy_n  = sum(1 for d,_ in sigs if d == "BUY")
        sell_n = sum(1 for d,_ in sigs if d == "SELL")
        direction = "BUY" if buy_n >= sell_n else "SELL"

        agreement = max(buy_n, sell_n) / len(sigs)
        avg_score = sum(scores) / len(scores) if scores else 0.5
        vol_bonus = 0.08 if vol_rat > 2.5 else (0.04 if vol_rat > 1.5 else 0.0)
        strength  = round(min(1.0, avg_score * 0.65 + agreement * 0.35 + vol_bonus), 3)

        return {
            "coin": coin,
            "signal": direction,
            "strength": strength,
            "source": "technical",
            "price": cp,
            "reason": " | ".join(r for _,r in sigs[:4]),
            # ── Rich metadata ──────────────────────────────────
            "rsi":          round(rsi_val, 1),
            "stoch_rsi_k":  round(stoch_k, 3),
            "williams_r":   round(wR, 1),
            "cci":          round(cci_val, 1),
            "macd_bull":    macd_bull,
            "bb_below":     bb_below,
            "bb_above":     bb_above,
            "bb_pct":       round(bb_pct, 3),
            "ema20_bull":   cp > ema20,
            "ema50_bull":   cp > ema50,
            "ema200_bull":  cp > ema200,
            "ema_golden":   in_golden_zone,
            "ema_cross_bull": ema_golden_cross,
            "ema_cross_bear": ema_death_cross,
            "obv_trend":    obv_t,
            "vol_ratio":    round(vol_rat, 2),
            "atr_pct":      round(atr_pct, 2),
            "momentum_5":   round(mom5, 2),
            "ich_bull":     ich_bull,
            "buy_signals":  buy_n,
            "sell_signals": sell_n,
            "total_signals": len(sigs),
        }

    # ── Göstergeler ────────────────────────────────────────────
    def _rsi(self, close, p=14) -> float:
        delta = close.diff()
        g = delta.clip(lower=0).rolling(p).mean()
        l = (-delta.clip(upper=0)).rolling(p).mean()
        rs  = g / l.replace(0, float("nan"))
        rsi = 100 - 100/(1+rs)
        v   = float(rsi.iloc[-1])
        return v if not pd.isna(v) else 50.0

    def _stoch_rsi_k(self, close, rp=14, sp=14, sk=3) -> float:
        try:
            delta = close.diff()
            g = delta.clip(lower=0).rolling(rp).mean()
            l = (-delta.clip(upper=0)).rolling(rp).mean()
            rs = g / l.replace(0, float("nan"))
            rsi = 100 - 100/(1+rs)
            mn  = rsi.rolling(sp).min()
            mx  = rsi.rolling(sp).max()
            k   = (rsi - mn) / (mx - mn).replace(0, float("nan"))
            v   = float(k.rolling(sk).mean().iloc[-1])
            return v if not pd.isna(v) else 0.5
        except Exception:
            return 0.5

    def _williams_r(self, high, low, close, p=14) -> float:
        try:
            hh = high.rolling(p).max()
            ll = low.rolling(p).min()
            wr = (hh - close) / (hh - ll).replace(0, float("nan")) * -100
            v  = float(wr.iloc[-1])
            return v if not pd.isna(v) else -50.0
        except Exception:
            return -50.0

    def _cci(self, high, low, close, p=20) -> float:
        try:
            tp  = (high + low + close) / 3
            sma = tp.rolling(p).mean()
            mad = tp.rolling(p).apply(lambda x: abs(x - x.mean()).mean(), raw=True)
            cci = (tp - sma) / (0.015 * mad.replace(0, float("nan")))
            v   = float(cci.iloc[-1])
            return v if not pd.isna(v) else 0.0
        except Exception:
            return 0.0

    def _obv_trend(self, close, volume, p=10) -> int:
        try:
            sign = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
            obv  = (volume * sign).cumsum()
            ma   = float(obv.rolling(p).mean().iloc[-1])
            last = float(obv.iloc[-1])
            if last > ma * 1.02:  return  1
            if last < ma * 0.98:  return -1
            return 0
        except Exception:
            return 0

    def _atr(self, high, low, close, p=14) -> float:
        try:
            pc = close.shift(1)
            tr = pd.concat([high-low, (high-pc).abs(), (low-pc).abs()], axis=1).max(axis=1)
            v  = float(tr.rolling(p).mean().iloc[-1])
            return v if not pd.isna(v) else 0.0
        except Exception:
            return 0.0
