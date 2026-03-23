from pathlib import Path
from src.adaptive_trading.config import load_config
from src.adaptive_trading.data import load_symbol_csvs
from src.adaptive_trading.backtester import BacktestEngine
from src.adaptive_trading.performance import metrics_to_text


def main() -> None:
    root = Path(__file__).resolve().parent
    config = load_config(root / "config" / "default.yaml")
    market = load_symbol_csvs(root / "data", config["symbols"])
    engine = BacktestEngine(config=config)
    result = engine.run(market)

    print("=== Adaptive Trading System v2 Demo Backtest ===")
    print(metrics_to_text(result.metrics))
    print(f"Trades: {len(result.trades)}")
    print(f"Artifacts written to: {(root / 'artifacts').as_posix()}")

    result.save(root / "artifacts" / "demo_backtest")


if __name__ == "__main__":
    main()
