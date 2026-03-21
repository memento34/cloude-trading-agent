
"""
HYPE ORACLE — CoinMarketCap hacim anomalileri + Fear & Greed Index
Olağandışı işlem hacmi = potansiyel hype sinyali
"""
import requests
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

FEAR_GREED_URL  = "https://api.alternative.me/fng/?limit=1"
CMC_LISTINGS_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"

# CMC API olmadan kullanılabilecek ücretsiz kaynak
CMC_FREE_URL = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing"

class HypeOracle:
    def __init__(self, signal_hub, cmc_api_key: str = ""):
        self.signal_hub = signal_hub
        self.cmc_api_key = cmc_api_key
        self.name = "hype"
        self._last_volumes: dict = {}   # coin -> önceki hacim
        self._fear_greed = 50           # Son Fear & Greed değeri

    def run(self):
        """Hype analizi çalıştır"""
        logger.info("🔥 Hype Oracle çalışıyor...")
        self._update_fear_greed()
        self._analyze_volume_spikes()

    def _update_fear_greed(self):
        """Fear & Greed Index güncelle (ücretsiz, API key gerektirmez)"""
        try:
            resp = requests.get(FEAR_GREED_URL, timeout=10)
            data = resp.json()
            if data.get("data"):
                self._fear_greed = int(data["data"][0]["value"])
                regime_signal = {
                    "coin": "MARKET",
                    "signal": "FEAR_GREED",
                    "strength": self._fear_greed / 100,
                    "source": "hype",
                    "reason": f"Fear & Greed: {self._fear_greed} ({data['data'][0]['value_classification']})",
                    "value": self._fear_greed,
                }
                self.signal_hub.publish(regime_signal)
                logger.info(f"🌡️  Fear & Greed: {self._fear_greed}")
        except Exception as e:
            logger.debug(f"Fear & Greed hatası: {e}")

    def _analyze_volume_spikes(self):
        """CMC'den hacim anomalisi tara"""
        try:
            if self.cmc_api_key:
                data = self._fetch_cmc_paid()
            else:
                data = self._fetch_cmc_free()

            if not data:
                return

            for coin_data in data[:50]:
                symbol = coin_data.get("symbol", "")
                coin = f"{symbol}/USDT"
                volume_24h = coin_data.get("volume_24h", 0)
                volume_change = coin_data.get("volume_change_24h", 0)  # % değişim

                # Önceki hacimle karşılaştır
                prev_volume = self._last_volumes.get(symbol, volume_24h)
                spike_ratio = volume_24h / prev_volume if prev_volume > 0 else 1.0
                self._last_volumes[symbol] = volume_24h

                # %100 üzeri hacim artışı veya yüksek volume_change → HYPE ALERT
                if volume_change > 100 or spike_ratio > 2.0:
                    strength = min(1.0, 0.6 + (volume_change / 500 if volume_change > 0 else spike_ratio / 10))
                    signal = {
                        "coin": coin,
                        "signal": "HYPE_ALERT",
                        "strength": round(strength, 3),
                        "source": "hype",
                        "reason": f"Hacim artışı: %{volume_change:.0f} (x{spike_ratio:.1f})",
                        "volume_change_pct": volume_change,
                        "fear_greed": self._fear_greed,
                    }
                    self.signal_hub.publish(signal)
                    logger.info(f"🔥 HYPE ALERT: {coin} | Hacim +%{volume_change:.0f}")
                    time.sleep(0.1)

        except Exception as e:
            logger.debug(f"Hacim analizi hatası: {e}")

    def _fetch_cmc_paid(self) -> list:
        headers = {"X-CMC_PRO_API_KEY": self.cmc_api_key}
        params = {"limit": 50, "convert": "USD", "sort": "volume_24h"}
        resp = requests.get(CMC_LISTINGS_URL, headers=headers, params=params, timeout=15)
        data = resp.json()
        result = []
        for item in data.get("data", []):
            q = item.get("quote", {}).get("USD", {})
            result.append({
                "symbol": item["symbol"],
                "volume_24h": q.get("volume_24h", 0),
                "volume_change_24h": q.get("volume_change_24h", 0),
                "price_change_24h": q.get("percent_change_24h", 0),
            })
        return result

    def _fetch_cmc_free(self) -> list:
        """API key olmadan temel CMC verisi (rate limit var, dikkatli kullan)"""
        try:
            params = {"start": "1", "limit": "50", "sortBy": "volume24h", "sortType": "desc",
                      "convert": "USD", "cryptoType": "all", "tagType": "all"}
            resp = requests.get(CMC_FREE_URL, params=params, timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"})
            data = resp.json()
            result = []
            for item in data.get("data", {}).get("cryptoCurrencyList", []):
                stats = item.get("statistics", {})
                result.append({
                    "symbol": item.get("symbol", ""),
                    "volume_24h": stats.get("volume24h", 0),
                    "volume_change_24h": stats.get("volumeChangePercentage24h", 0),
                    "price_change_24h": stats.get("priceChangePercentage24h", 0),
                })
            return result
        except Exception as e:
            logger.debug(f"CMC free fetch hatası: {e}")
            return []

    def get_fear_greed(self) -> int:
        return self._fear_greed
