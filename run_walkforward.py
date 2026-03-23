from pathlib import Path
from src.adaptive_trading.config import load_config
from src.adaptive_trading.data import load_symbol_csvs
from src.adaptive_trading.walkforward import WalkForwardRunner
from src.adaptive_trading.performance import metrics_to_text


def main() -> None:
    root = Path(__file__).resolve().parent
    config = load_config(root / "config" / "default.yaml")
    market = load_symbol_csvs(root / "data", config["symbols"])

    runner = WalkForwardRunner(config=config)
    result = runner.run(market)
    print("=== Walk-Forward Result ===")
    print(metrics_to_text(result.aggregate_metrics))
    print(f"Windows: {len(result.windows)}")
    result.save(root / "artifacts" / "walkforward")


if __name__ == "__main__":
    main()
