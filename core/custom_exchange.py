
"""
CUSTOM EXCHANGE v2 — Railway'den çalışan API'ler
Öncelik: CryptoCompare (ücretsiz, hızlı) → CoinGecko → Kraken → Mock
"""
import requests, time, logging
import pandas as pd

logger = logging.getLogger(__name__)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

# Sembol eşleştirme
def _base(symbol): return symbol.split("/")[0]
def _binance_sym(symbol): return symbol.replace("/","")

COINGECKO_IDS = {
    "BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin",
    "XRP":"ripple","ADA":"cardano","DOGE":"dogecoin","AVAX":"avalanche-2",
    "DOT":"polkadot","MATIC":"matic-network","LINK":"chainlink","LTC":"litecoin",
    "UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic",
    "NEAR":"near","APT":"aptos","FIL":"filecoin","ARB":"arbitrum",
    "OP":"optimism","SUI":"sui","INJ":"injective-protocol","PEPE":"pepe",
    "WIF":"dogwifcoin","AAVE":"aave","MKR":"maker","LDO":"lido-dao",
    "RUNE":"thorchain","GRT":"the-graph","SNX":"havven","CRV":"curve-dao-token",
    "SAND":"the-sandbox","MANA":"decentraland","AXS":"axie-infinity",
    "GALA":"gala","CHZ":"chiliz","THETA":"theta-token","VET":"vechain",
    "FTM":"fantom","ENS":"ethereum-name-service","CAKE":"pancakeswap-token",
    "BLUR":"blur","ORDI":"ordi","WLD":"worldcoin-wld","IMX":"immutable-x",
    "SEI":"sei-network","TIA":"celestia","CFX":"conflux-token",
    "JUP":"jupiter-exchange-solana",
}

# Gerçekçi mock fiyatlar (Railway'den hiçbir API çalışmazsa)
MOCK_PRICES = {
    "BTC/USDT":83500,"ETH/USDT":1900,"SOL/USDT":130,"BNB/USDT":580,
    "XRP/USDT":0.55,"ADA/USDT":0.45,"DOGE/USDT":0.17,"AVAX/USDT":22,
    "DOT/USDT":4.5,"MATIC/USDT":0.50,"LINK/USDT":13,"LTC/USDT":80,
    "UNI/USDT":7.2,"ATOM/USDT":5.1,"XLM/USDT":0.095,"ETC/USDT":18,
    "NEAR/USDT":2.8,"APT/USDT":5.5,"FIL/USDT":3.2,"ARB/USDT":0.38,
    "OP/USDT":0.72,"SUI/USDT":2.1,"INJ/USDT":12,"PEPE/USDT":0.0000075,
    "WIF/USDT":0.85,"AAVE/USDT":145,"MKR/USDT":1450,"LDO/USDT":0.90,
    "RUNE/USDT":1.35,"GRT/USDT":0.10,"SNX/USDT":0.85,"CRV/USDT":0.33,
    "SAND/USDT":0.28,"MANA/USDT":0.30,"AXS/USDT":4.5,"GALA/USDT":0.017,
    "CHZ/USDT":0.055,"THETA/USDT":0.75,"VET/USDT":0.023,"FTM/USDT":0.52,
    "ENS/USDT":18,"CAKE/USDT":1.9,"BLUR/USDT":0.12,"ORDI/USDT":20,
    "WLD/USDT":0.95,"IMX/USDT":0.65,"SEI/USDT":0.19,"TIA/USDT":2.8,"CFX/USDT":0.12,
}

class CustomExchange:
    def __init__(self):
        self.markets = {}
        self._ohlcv_cache = {}
        self._source_used = "none"
        self._last_bulk   = 0
        self._bulk_prices = {}
        logger.info("🔌 CustomExchange v2 başlatıldı")

    def load_markets(self): return {}
    def get_source(self): return self._source_used

    # ─── Fiyat API'leri ───────────────────────────────────────
    def fetch_ticker(self, symbol):
        p = self._get_single_price(symbol)
        return {"last": p, "symbol": symbol}

    def fetch_tickers(self, symbols):
        """Tek çağrıda tüm fiyatları çek"""
        prices = self._fetch_all_prices(symbols)
        return {s: {"last": prices.get(s, MOCK_PRICES.get(s, 1.0)), "symbol": s}
                for s in symbols}

    def _fetch_all_prices(self, symbols):
        """Sırasıyla dene: CryptoCompare → CoinGecko → Mock"""
        # 1. CryptoCompare multi-price (hızlı, Railway'den çalışır)
        try:
            bases = list({_base(s) for s in symbols})[:50]
            r = SESSION.get(
                "https://min-api.cryptocompare.com/data/pricemulti",
                params={"fsyms": ",".join(bases), "tsyms": "USD"},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                result = {}
                for sym in symbols:
                    b = _base(sym)
                    p = data.get(b, {}).get("USD")
                    if p and float(p) > 0:
                        result[sym] = float(p)
                if len(result) >= len(symbols) // 2:
                    self._source_used = "cryptocompare"
                    self._bulk_prices = result
                    return result
        except Exception as e:
            logger.debug(f"CryptoCompare: {e}")

        # 2. CoinGecko simple price (ücretsiz, güvenilir)
        try:
            ids_needed = [COINGECKO_IDS[_base(s)] for s in symbols if _base(s) in COINGECKO_IDS]
            if ids_needed:
                r = SESSION.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": ",".join(ids_needed[:50]), "vs_currencies": "usd"},
                    timeout=12
                )
                if r.status_code == 200:
                    data = r.json()
                    id_to_base = {v: k for k,v in COINGECKO_IDS.items()}
                    result = {}
                    for sym in symbols:
                        b  = _base(sym)
                        cid = COINGECKO_IDS.get(b)
                        if cid and cid in data:
                            p = data[cid].get("usd")
                            if p:
                                result[sym] = float(p)
                    if result:
                        self._source_used = "coingecko"
                        self._bulk_prices = result
                        return result
        except Exception as e:
            logger.debug(f"CoinGecko bulk: {e}")

        # 3. Mock (son çare)
        self._source_used = "mock"
        import random
        result = {}
        for s in symbols:
            base = MOCK_PRICES.get(s, 1.0)
            result[s] = base * (1 + random.gauss(0, 0.002))
        return result

    def _get_single_price(self, symbol):
        # Bulk cache'de varsa kullan
        if symbol in self._bulk_prices:
            return self._bulk_prices[symbol]
        # CryptoCompare single
        try:
            b = _base(symbol)
            r = SESSION.get("https://min-api.cryptocompare.com/data/price",
                           params={"fsym": b, "tsyms": "USD"}, timeout=6)
            if r.status_code == 200:
                p = r.json().get("USD")
                if p: return float(p)
        except Exception: pass
        # Mock fallback
        import random
        return MOCK_PRICES.get(symbol, 1.0) * (1 + random.gauss(0, 0.002))

    # ─── OHLCV ────────────────────────────────────────────────
    TF_MAP = {"1m":"1m","5m":"5m","15m":"15m","1h":"1h","4h":"4h","1d":"1d"}
    CG_DAYS = {"1m":1,"5m":1,"15m":2,"1h":7,"4h":30,"1d":90}

    def fetch_ohlcv(self, symbol, timeframe="4h", limit=100):
        key = (symbol, timeframe)
        cached = self._ohlcv_cache.get(key)
        if cached and time.time() - cached[1] < 180:
            return cached[0]
        data = (self._cryptocompare_ohlcv(symbol, timeframe, limit) or
                self._coingecko_ohlcv(symbol, timeframe, limit) or
                self._mock_ohlcv(symbol, limit))
        if data:
            self._ohlcv_cache[key] = (data, time.time())
        return data or []

    def _cryptocompare_ohlcv(self, symbol, tf, limit):
        try:
            b = _base(symbol)
            ep = {"1m":"histominute","5m":"histominute","15m":"histominute",
                  "1h":"histohour","4h":"histohour","1d":"histoday"}.get(tf,"histohour")
            aggregate = {"1m":1,"5m":5,"15m":15,"1h":1,"4h":4,"1d":1}.get(tf,4)
            r = SESSION.get(
                f"https://min-api.cryptocompare.com/data/v2/{ep}",
                params={"fsym":b,"tsym":"USD","limit":limit,"aggregate":aggregate},
                timeout=10
            )
            if r.status_code == 200:
                raw = r.json().get("Data",{}).get("Data",[])
                if raw:
                    return [[int(c["time"])*1000, float(c["open"]), float(c["high"]),
                             float(c["low"]), float(c["close"]), float(c["volumefrom"])]
                            for c in raw if c.get("close",0) > 0]
        except Exception as e:
            logger.debug(f"CC OHLCV {symbol}: {e}")
        return None

    def _coingecko_ohlcv(self, symbol, tf, limit):
        try:
            b   = _base(symbol)
            cid = COINGECKO_IDS.get(b)
            if not cid: return None
            days = self.CG_DAYS.get(tf, 30)
            r = SESSION.get(
                f"https://api.coingecko.com/api/v3/coins/{cid}/ohlc",
                params={"vs_currency":"usd","days":days}, timeout=12
            )
            if r.status_code == 200:
                raw = r.json()
                data = [[int(c[0]),float(c[1]),float(c[2]),float(c[3]),float(c[4]),0.0]
                        for c in raw]
                return data[-limit:]
        except Exception as e:
            logger.debug(f"CG OHLCV {symbol}: {e}")
        return None

    def _mock_ohlcv(self, symbol, limit):
        import random
        p = MOCK_PRICES.get(symbol, 1.0)
        t = int(time.time()*1000)
        data = []
        for i in range(limit):
            o = p * (1 + random.gauss(0, 0.008))
            c = o * (1 + random.gauss(0, 0.004))
            h = max(o,c)*(1+abs(random.gauss(0,0.002)))
            l = min(o,c)*(1-abs(random.gauss(0,0.002)))
            data.append([t-(limit-i)*14400000, o, h, l, c, random.uniform(500,5000)])
        return data
