from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List


DEFAULT_FIXED_UNIVERSE_RAW = """OKX:BTCUSDT.P,OKX:XAUUSDT.P,OKX:ETHUSDT.P,OKX:BNBUSDT.P,OKX:BCHUSDT.P,OKX:TAOUSDT.P,OKX:ZECUSDT.P,OKX:AAVEUSDT.P,OKX:SOLUSDT.P,OKX:XAGUSDT.P,OKX:LTCUSDT.P,OKX:HYPEUSDT.P,OKX:COMPUSDT.P,OKX:AVAXUSDT.P,OKX:LINKUSDT.P,OKX:UNIUSDT.P,OKX:ORDIUSDT.P,OKX:ZROUSDT.P,OKX:ATOMUSDT.P,OKX:RENDERUSDT.P,OKX:DOTUSDT.P,OKX:XRPUSDT.P,OKX:TONUSDT.P,OKX:NEARUSDT.P,OKX:SUIUSDT.P,OKX:APTUSDT.P,OKX:VIRTUALUSDT.P,OKX:ETHFIUSDT.P,OKX:TIAUSDT.P,OKX:WLDUSDT.P,OKX:TRXUSDT.P,OKX:LDOUSDT.P,OKX:ADAUSDT.P,OKX:ONDOUSDT.P,OKX:CRVUSDT.P,OKX:EIGENUSDT.P,OKX:PIUSDT.P,OKX:XLMUSDT.P,OKX:JUPUSDT.P,OKX:OPUSDT.P,OKX:ARBUSDT.P,OKX:POLUSDT.P,OKX:DOGEUSDT.P,OKX:HBARUSDT.P,OKX:ALGOUSDT.P,OKX:STRKUSDT.P,OKX:ZKUSDT.P,OKX:PENGUUSDT.P,OKX:LINEAUSDT.P,OKX:PUMPUSDT.P"""

TRADINGVIEW_OKX_PATTERN = re.compile(r"^(?:OKX:)?(?P<base>[A-Z0-9]+?)(?P<quote>USDT|USDC|USD)\.P$")
DASH_STYLE_PATTERN = re.compile(r"^(?P<base>[A-Z0-9]+)-(?P<quote>USDT|USDC|USD)-(?P<kind>SWAP|FUTURES?)$")
SPOT_DASH_PATTERN = re.compile(r"^(?P<base>[A-Z0-9]+)-(?P<quote>USDT|USDC|USD)$")
PLAIN_PATTERN = re.compile(r"^(?P<base>[A-Z0-9]+?)(?P<quote>USDT|USDC|USD)$")


def normalize_okx_symbol(raw: str) -> str:
    s = str(raw or "").strip().upper()
    if not s:
        return ""
    m = TRADINGVIEW_OKX_PATTERN.match(s)
    if m:
        return f"{m.group('base')}-{m.group('quote')}-SWAP"
    m = DASH_STYLE_PATTERN.match(s)
    if m:
        return f"{m.group('base')}-{m.group('quote')}-SWAP"
    m = SPOT_DASH_PATTERN.match(s)
    if m:
        return f"{m.group('base')}-{m.group('quote')}-SWAP"
    m = PLAIN_PATTERN.match(s.replace("OKX:", "").replace(".P", ""))
    if m:
        return f"{m.group('base')}-{m.group('quote')}-SWAP"
    return s.replace("OKX:", "").replace(".P", "")


def parse_symbol_list(raw: str) -> List[str]:
    seen = set()
    out: List[str] = []
    cleaned = str(raw or "").replace("\n", ",")
    for item in cleaned.split(","):
        sym = normalize_okx_symbol(item)
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


@dataclass
class ServiceSettings:
    root_dir: Path
    mode: str = "paper"  # paper | live
    market_data_source: str = "okx"  # okx | csv | auto
    auto_start_scheduler: bool = True
    trading_interval_minutes: int = 15
    optimization_interval_hours: int = 6
    candles_limit: int = 260
    history_cache_bars: int = 2000
    optimize_lookback_bars: int = 960
    default_bar: str = "1H"
    okx_flag: str = "0"  # 0 prod, 1 demo
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""
    okx_base_url: str = "https://www.okx.com"
    trade_inst_type: str = "SWAP"
    td_mode: str = "cross"
    leverage: str = "3"
    settle_ccy: str = "USDT"
    max_order_notional_pct: float = 0.18
    paper_starting_equity: float = 100000.0
    optimizer_candidates: int = 16
    auto_promote_min_objective_improvement: float = 0.15
    run_jobs_on_startup: bool = False
    state_dir_name: str = "state"
    logs_dir_name: str = "logs"
    symbols: List[str] | None = None
    csv_symbol_map: Dict[str, str] | None = None
    dynamic_universe: bool = True
    universe_size: int = 50
    universe_refresh_minutes: int = 60
    universe_settle_ccy: str = "USDT"
    universe_quote_ccy: str = "USDT"
    universe_min_volume_usdt: float = 5_000_000.0  # FIX: was 0 (disabled); default 5M USDT 24h vol
    universe_max_spread_bps: float = 15.0          # FIX: new — exclude wide-spread instruments
    universe_include_symbols: List[str] | None = None
    min_loaded_symbols: int = 12
    optimization_min_symbols: int = 8
    optimizer_history_floor_bars: int = 240
    root_redirect_to_dashboard: bool = True
    fixed_universe_symbols_raw: str = DEFAULT_FIXED_UNIVERSE_RAW

    @classmethod
    def from_env(cls, root_dir: str | Path) -> "ServiceSettings":
        root = Path(root_dir)
        market_data_source = os.getenv("MARKET_DATA_SOURCE", "okx").lower()
        fixed_raw = os.getenv("FIXED_UNIVERSE_SYMBOLS", DEFAULT_FIXED_UNIVERSE_RAW)
        raw_symbols = os.getenv("OKX_SYMBOLS", fixed_raw)
        raw_include = os.getenv("UNIVERSE_INCLUDE_SYMBOLS", raw_symbols)
        explicit_symbols = parse_symbol_list(raw_symbols)
        include_symbols = parse_symbol_list(raw_include)
        fixed_mode = os.getenv("FIXED_UNIVERSE_MODE", "true").lower() == "true"
        explicit_pairs_requested = bool(explicit_symbols) and fixed_mode
        dynamic_default = "false" if explicit_pairs_requested or market_data_source == "csv" else "true"

        return cls(
            root_dir=root,
            mode=os.getenv("TRADING_MODE", "paper").lower(),
            market_data_source=market_data_source,
            auto_start_scheduler=os.getenv("AUTO_START_SCHEDULER", "true").lower() == "true",
            trading_interval_minutes=int(os.getenv("TRADING_INTERVAL_MINUTES", "15")),
            optimization_interval_hours=int(os.getenv("OPTIMIZATION_INTERVAL_HOURS", "6")),
            candles_limit=int(os.getenv("CANDLES_LIMIT", "260")),
            history_cache_bars=int(os.getenv("HISTORY_CACHE_BARS", "2000")),
            optimize_lookback_bars=int(os.getenv("OPTIMIZE_LOOKBACK_BARS", "960")),
            default_bar=os.getenv("OKX_BAR", "1H"),
            okx_flag=os.getenv("OKX_FLAG", os.getenv("OKX_DEMO", "0")),
            okx_api_key=os.getenv("OKX_API_KEY", ""),
            okx_api_secret=os.getenv("OKX_API_SECRET", ""),
            okx_passphrase=os.getenv("OKX_PASSPHRASE", ""),
            okx_base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com"),
            trade_inst_type=os.getenv("OKX_INST_TYPE", "SWAP"),
            td_mode=os.getenv("OKX_TD_MODE", "cross"),
            leverage=os.getenv("OKX_LEVERAGE", "3"),
            settle_ccy=os.getenv("SETTLE_CCY", "USDT"),
            max_order_notional_pct=float(os.getenv("MAX_ORDER_NOTIONAL_PCT", "0.18")),
            paper_starting_equity=float(os.getenv("PAPER_STARTING_EQUITY", "100000")),
            optimizer_candidates=int(os.getenv("OPTIMIZER_CANDIDATES", "16")),
            auto_promote_min_objective_improvement=float(os.getenv("AUTO_PROMOTE_MIN_OBJECTIVE_IMPROVEMENT", "0.15")),
            run_jobs_on_startup=os.getenv("RUN_JOBS_ON_STARTUP", "false").lower() == "true",
            symbols=explicit_symbols,
            csv_symbol_map={
                "BTC-USDT-SWAP": "BTCUSDT",
                "ETH-USDT-SWAP": "ETHUSDT",
                "SOL-USDT-SWAP": "SOLUSDT",
                "BTC-USDT": "BTCUSDT",
                "ETH-USDT": "ETHUSDT",
                "SOL-USDT": "SOLUSDT",
            },
            dynamic_universe=(os.getenv("DYNAMIC_UNIVERSE", dynamic_default).lower() == "true") if not explicit_pairs_requested else False,
            universe_size=int(os.getenv("UNIVERSE_SIZE", str(max(len(explicit_symbols), 1) if explicit_symbols else 50))),
            universe_refresh_minutes=int(os.getenv("UNIVERSE_REFRESH_MINUTES", "60")),
            universe_settle_ccy=os.getenv("UNIVERSE_SETTLE_CCY", os.getenv("SETTLE_CCY", "USDT")),
            universe_quote_ccy=os.getenv("UNIVERSE_QUOTE_CCY", "USDT"),
            universe_min_volume_usdt=float(os.getenv("UNIVERSE_MIN_VOLUME_USDT", "5000000")),
            universe_max_spread_bps=float(os.getenv("UNIVERSE_MAX_SPREAD_BPS", "15.0")),
            universe_include_symbols=include_symbols,
            min_loaded_symbols=int(os.getenv("MIN_LOADED_SYMBOLS", "8" if explicit_pairs_requested else "12")),
            optimization_min_symbols=int(os.getenv("OPTIMIZATION_MIN_SYMBOLS", "6" if explicit_pairs_requested else "8")),
            optimizer_history_floor_bars=int(os.getenv("OPTIMIZER_HISTORY_FLOOR_BARS", "240")),
            root_redirect_to_dashboard=os.getenv("ROOT_REDIRECT_TO_DASHBOARD", "true").lower() == "true",
            fixed_universe_symbols_raw=fixed_raw,
        )

    @property
    def state_dir(self) -> Path:
        return self.root_dir / self.state_dir_name

    @property
    def logs_dir(self) -> Path:
        return self.root_dir / self.logs_dir_name

    @property
    def has_private_okx_credentials(self) -> bool:
        return bool(self.okx_api_key and self.okx_api_secret and self.okx_passphrase)

    def to_dict(self) -> Dict:
        payload = asdict(self)
        payload["root_dir"] = str(self.root_dir)
        payload["state_dir"] = str(self.state_dir)
        payload["logs_dir"] = str(self.logs_dir)
        payload["okx_api_secret"] = "***" if self.okx_api_secret else ""
        payload["okx_api_key"] = "***" if self.okx_api_key else ""
        payload["okx_passphrase"] = "***" if self.okx_passphrase else ""
        return payload
