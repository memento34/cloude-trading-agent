
"""
MERKEZI FİYAT CACHE — Fiyatlar bir kere çekilir, herkes buradan okur
"""
import time, threading, logging
logger = logging.getLogger(__name__)

class PriceCache:
    def __init__(self):
        self._prices   = {}     # symbol → float
        self._updated  = 0.0
        self._lock     = threading.Lock()
        self._source   = "none"

    def update(self, exchange, coins: list):
        """Ana döngüden bir kere çağrılır"""
        try:
            tickers = exchange.fetch_tickers(coins)
            new_prices = {}
            for sym, t in tickers.items():
                if t.get("last") and float(t["last"]) > 0:
                    new_prices[sym] = float(t["last"])
            if new_prices:
                with self._lock:
                    self._prices.update(new_prices)
                    self._updated = time.time()
                    self._source  = getattr(exchange, "get_source", lambda: "?")()
                logger.info(f"💰 Fiyat cache güncellendi: {len(new_prices)} coin [{self._source}]")
                return True
        except Exception as e:
            logger.warning(f"Fiyat cache güncelleme hatası: {e}")
        return False

    def get(self, symbol: str) -> float | None:
        with self._lock:
            return self._prices.get(symbol)

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._prices)

    def age_seconds(self) -> float:
        return time.time() - self._updated if self._updated else 999

    def is_fresh(self, max_age=120) -> bool:
        return self.age_seconds() < max_age

price_cache = PriceCache()
