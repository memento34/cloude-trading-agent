
"""
SINYAL HAVUZU — Oracle'lar buraya yazar, Agent'lar buradan okur
Thread-safe, son 500 sinyali tutar
"""
import threading
from datetime import datetime
from collections import deque

class SignalHub:
    def __init__(self):
        self._signals = deque(maxlen=500)
        self._lock = threading.Lock()
        self._latest_by_source = {}   # En son sinyal: {"technical": {...}, "hype": {...}}
        self._regime = {"regime": "ANY", "volatility": "MEDIUM", "timestamp": None}

    def publish(self, signal: dict):
        """Oracle buraya sinyal yazar"""
        signal["timestamp"] = datetime.now().isoformat()
        with self._lock:
            self._signals.append(signal)
            source = signal.get("source", "unknown")
            # Kaynak bazında en son sinyali güncelle
            if source not in self._latest_by_source:
                self._latest_by_source[source] = []
            self._latest_by_source[source].append(signal)
            if len(self._latest_by_source[source]) > 50:
                self._latest_by_source[source].pop(0)

    def set_regime(self, regime: dict):
        """Piyasa rejimini güncelle"""
        with self._lock:
            regime["timestamp"] = datetime.now().isoformat()
            self._regime = regime

    def get_regime(self) -> dict:
        with self._lock:
            return dict(self._regime)

    def get_signals_for_coin(self, coin: str, source: str = None, limit: int = 10) -> list:
        """Belirli bir coin için sinyalleri getir"""
        with self._lock:
            signals = list(self._signals)
        signals = [s for s in signals if s.get("coin") == coin]
        if source:
            signals = [s for s in signals if s.get("source") == source]
        return signals[-limit:]

    def get_latest_signals(self, source: str = None, limit: int = 20) -> list:
        """En son sinyalleri getir"""
        with self._lock:
            if source and source in self._latest_by_source:
                return list(self._latest_by_source[source])[-limit:]
            return list(self._signals)[-limit:]

    def get_all_recent(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._signals)[-limit:]

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "total_signals": len(self._signals),
                "sources": list(self._latest_by_source.keys()),
                "regime": self._regime
            }

# Global singleton
signal_hub = SignalHub()
