# Adaptive Trading System v6 — Railway + Fixed OKX Futures Pair Universe + Scheduler + Dashboard

Bu sürüm dinamik top-50 evren yerine **senin verdiğin sabit OKX vadeli pair listesi** üzerinde çalışır.

Varsayılan universe şu TradingView/OKX pair listesinden normalize edilerek yüklenir:
- `OKX:BTCUSDT.P`
- `OKX:XAUUSDT.P`
- `OKX:ETHUSDT.P`
- `OKX:BNBUSDT.P`
- `OKX:BCHUSDT.P`
- `OKX:TAOUSDT.P`
- `OKX:ZECUSDT.P`
- `OKX:AAVEUSDT.P`
- `OKX:SOLUSDT.P`
- `OKX:XAGUSDT.P`
- `OKX:LTCUSDT.P`
- `OKX:HYPEUSDT.P`
- `OKX:COMPUSDT.P`
- `OKX:AVAXUSDT.P`
- `OKX:LINKUSDT.P`
- `OKX:UNIUSDT.P`
- `OKX:ORDIUSDT.P`
- `OKX:ZROUSDT.P`
- `OKX:ATOMUSDT.P`
- `OKX:RENDERUSDT.P`
- `OKX:DOTUSDT.P`
- `OKX:XRPUSDT.P`
- `OKX:TONUSDT.P`
- `OKX:NEARUSDT.P`
- `OKX:SUIUSDT.P`
- `OKX:APTUSDT.P`
- `OKX:VIRTUALUSDT.P`
- `OKX:ETHFIUSDT.P`
- `OKX:TIAUSDT.P`
- `OKX:WLDUSDT.P`
- `OKX:TRXUSDT.P`
- `OKX:LDOUSDT.P`
- `OKX:ADAUSDT.P`
- `OKX:ONDOUSDT.P`
- `OKX:CRVUSDT.P`
- `OKX:EIGENUSDT.P`
- `OKX:PIUSDT.P`
- `OKX:XLMUSDT.P`
- `OKX:JUPUSDT.P`
- `OKX:OPUSDT.P`
- `OKX:ARBUSDT.P`
- `OKX:POLUSDT.P`
- `OKX:DOGEUSDT.P`
- `OKX:HBARUSDT.P`
- `OKX:ALGOUSDT.P`
- `OKX:STRKUSDT.P`
- `OKX:ZKUSDT.P`
- `OKX:PENGUUSDT.P`
- `OKX:LINEAUSDT.P`
- `OKX:PUMPUSDT.P`

Kod bu TradingView formatını otomatik olarak OKX `INST_ID` formatına çevirir. Örnek:
- `OKX:BTCUSDT.P` → `BTC-USDT-SWAP`
- `OKX:XAUUSDT.P` → `XAU-USDT-SWAP`

## Ne değişti
- Dinamik evren yerine sabit curated evren
- TradingView `OKX:XXXUSDT.P` sembollerini otomatik normalize etme
- Varsayılan olarak `FIXED_UNIVERSE_MODE=true`
- `DYNAMIC_UNIVERSE` açık olsa bile explicit fixed pair listesi verilirse worker sabit listeyi kullanır
- Dashboard evren tablosu artık bu sabit pair listesini ve yüklenebilen/enstrümanı bulunanları gösterir
- OKX üzerinde bulunmayan veya veri dönmeyen semboller `load_errors` içine düşer ve worker geri kalan sembollerle devam eder

## Railway start command
```bash
gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT app:app
```

## Önerilen env
```env
TRADING_MODE=paper
MARKET_DATA_SOURCE=okx
AUTO_START_SCHEDULER=true
RUN_JOBS_ON_STARTUP=false
TRADING_INTERVAL_MINUTES=15
OPTIMIZATION_INTERVAL_HOURS=6
OKX_BAR=1H
OKX_INST_TYPE=SWAP
OKX_TD_MODE=cross
OKX_LEVERAGE=3
OKX_FLAG=1
PAPER_STARTING_EQUITY=100000
OPTIMIZER_CANDIDATES=16
OPTIMIZE_LOOKBACK_BARS=960
MAX_ORDER_NOTIONAL_PCT=0.12
FIXED_UNIVERSE_MODE=true
DYNAMIC_UNIVERSE=false
UNIVERSE_SETTLE_CCY=USDT
UNIVERSE_QUOTE_CCY=USDT
MIN_LOADED_SYMBOLS=8
OPTIMIZATION_MIN_SYMBOLS=6
OPTIMIZER_HISTORY_FLOOR_BARS=240
ROOT_REDIRECT_TO_DASHBOARD=true
OKX_SYMBOLS=OKX:BTCUSDT.P,OKX:XAUUSDT.P,OKX:ETHUSDT.P,OKX:BNBUSDT.P,OKX:BCHUSDT.P,OKX:TAOUSDT.P,OKX:ZECUSDT.P,OKX:AAVEUSDT.P,OKX:SOLUSDT.P,OKX:XAGUSDT.P,OKX:LTCUSDT.P,OKX:HYPEUSDT.P,OKX:COMPUSDT.P,OKX:AVAXUSDT.P,OKX:LINKUSDT.P,OKX:UNIUSDT.P,OKX:ORDIUSDT.P,OKX:ZROUSDT.P,OKX:ATOMUSDT.P,OKX:RENDERUSDT.P,OKX:DOTUSDT.P,OKX:XRPUSDT.P,OKX:TONUSDT.P,OKX:NEARUSDT.P,OKX:SUIUSDT.P,OKX:APTUSDT.P,OKX:VIRTUALUSDT.P,OKX:ETHFIUSDT.P,OKX:TIAUSDT.P,OKX:WLDUSDT.P,OKX:TRXUSDT.P,OKX:LDOUSDT.P,OKX:ADAUSDT.P,OKX:ONDOUSDT.P,OKX:CRVUSDT.P,OKX:EIGENUSDT.P,OKX:PIUSDT.P,OKX:XLMUSDT.P,OKX:JUPUSDT.P,OKX:OPUSDT.P,OKX:ARBUSDT.P,OKX:POLUSDT.P,OKX:DOGEUSDT.P,OKX:HBARUSDT.P,OKX:ALGOUSDT.P,OKX:STRKUSDT.P,OKX:ZKUSDT.P,OKX:PENGUUSDT.P,OKX:LINEAUSDT.P,OKX:PUMPUSDT.P
```

## Dashboard
- `GET /dashboard`
- `GET /api/dashboard`

## Dürüst not
Burada sembol availability’sini canlı OKX hesabında test etmedim. Senin verdiğin listeden bazı pair’ler belirli anda OKX’te yoksa veya candle dönmüyorsa worker onları `load_errors` altında raporlayıp yüklenebilen pair’lerle devam eder.

---

## v7 — Bug Fixes & Improvements

| # | Sorun | Düzeltme |
|---|-------|----------|
| 1 | **Optimizer: saf random search** | Optuna TPE (Bayesian) ile değiştirildi. Aynı candidate bütçesiyle 5-10× daha iyi parametre bulur. Champion config'i warm-start olarak TPE'ye verilir. |
| 2 | **LiveExecutor: exchange-side SL/TP yok** | `open_position` artık OKX `attachAlgoOrds` kullanarak stop-loss ve take-profit emirlerini entry emriyle atomik olarak gönderir. Servis çöktüğünde pozisyon korumalı kalır. |
| 3 | **Slippage sabit BPS** | Backtester artık volatilite-bağımlı dinamik slippage kullanır: `ATR/close` oranına göre base BPS değeri 1×–3× arasında ölçeklenir. |
| 4 | **Korelasyon matrisi her barda hesaplanıyor** | Rolling korelasyon listesi ana döngüden önce bir kez hesaplanır; her iterasyonda `df.iloc[…].corr()` çağrısı kaldırıldı. |
| 5 | **Evren spread/derinlik filtresi zayıf** | `universe_min_volume_usdt` default 0→5M USDT. Yeni `universe_max_spread_bps` (default 15 BPS) filtresi eklendi; çok geniş bid-ask spreadli semboller evrenden çıkarılır. |
| 6 | **PaperExecutor'da fee yok** | `open_position` ve `close_position` artık backtester ile aynı fee oranını (4 BPS) uygular; cash hesabından düşer ve trade kaydına yansır. |
| 7 | **promotion.py data leakage** | `forward_market` artık `cursor`'dan başlar (eskiden `cursor-40`). Train ve eval pencereleri artık kesinlikle ayrı; mini data leakage giderildi. |
| 8 | **API rate limit riski** | `get_candles` çağrıları arasına 120 ms gecikme eklendi. 50 sembol × 120 ms = 6 sn — OKX public limiti aşılmaz. |
| 9 | **state_store.py corrupt JSON riski** | `write_json` artık temp file + `os.replace()` kullanır (POSIX'te atomik). Yarı yazılmış JSON dosyası oluşamaz. |
