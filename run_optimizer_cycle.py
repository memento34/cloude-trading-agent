from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from adaptive_trading.live.worker import TradingServiceWorker


def main():
    worker = TradingServiceWorker(ROOT)
    result = worker.optimization_cycle()
    print(json.dumps(result, indent=2, default=str))
    return result


if __name__ == "__main__":
    main()
