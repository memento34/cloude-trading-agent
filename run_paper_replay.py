from pathlib import Path
from src.adaptive_trading.config import load_config
from src.adaptive_trading.data import load_symbol_csvs
from src.adaptive_trading.promotion import ContinuousPaperOptimizer


def main() -> None:
    root = Path(__file__).resolve().parent
    config = load_config(root / "config" / "default.yaml")
    market = load_symbol_csvs(root / "data", config["symbols"])

    runner = ContinuousPaperOptimizer(config=config)
    result = runner.run_replay(market)
    print("=== Paper Replay with Continuous Optimization ===")
    print(result.summary_text())
    result.save(root / "artifacts" / "paper_replay")


if __name__ == "__main__":
    main()
