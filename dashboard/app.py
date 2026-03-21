
"""
DASHBOARD WEB UYGULAMASI — Flask
"""
from flask import Flask, jsonify, render_template, request
import logging
logger = logging.getLogger(__name__)

_paper_traders = {}
_signal_hub    = None
_risk_manager  = None
_eliminator    = None
_exchange      = None

def create_app(paper_traders, signal_hub, risk_manager, eliminator, exchange, password):
    global _paper_traders, _signal_hub, _risk_manager, _eliminator, _exchange
    _paper_traders = paper_traders
    _signal_hub    = signal_hub
    _risk_manager  = risk_manager
    _eliminator    = eliminator
    _exchange      = exchange

    app = Flask(__name__, template_folder="templates")
    PWD = password

    @app.route("/")
    def index():
        if PWD and request.args.get("pwd","") != PWD:
            return """<html><body style="background:#0d1117;color:#e6edf3;font-family:monospace;padding:40px">
            <h3>🔐 Dashboard Erişimi</h3>
            <form method="get">Şifre: <input type="password" name="pwd"
            style="background:#21262d;color:#e6edf3;border:1px solid #30363d;padding:6px">
            <button type="submit" style="background:#238636;color:white;border:none;padding:6px 12px">Giriş</button>
            </form></body></html>"""
        return render_template("index.html")

    @app.route("/api/status")
    def status():
        try:
            # Fiyatları price_cache'den al (HTTP yok)
            from core.price_cache import price_cache
            current_prices = price_cache.get_all()

            leaderboard  = _eliminator.get_leaderboard(current_prices) if _eliminator else []
            signals      = _signal_hub.get_all_recent(50) if _signal_hub else []
            regime       = _signal_hub.get_regime() if _signal_hub else {}
            risk         = _risk_manager.get_status() if _risk_manager else {}
            elim_log     = _eliminator.get_log(10) if _eliminator else []

            positions, recent_trades = [], []
            for aid, trader in _paper_traders.items():
                for coin, pos in trader.positions.items():
                    d = pos.to_dict(); d["agent_id"] = aid
                    # Anlık PnL hesapla
                    cp = current_prices.get(coin)
                    if cp:
                        d["current_pnl"] = round(pos.calculate_pnl(cp), 2)
                    positions.append(d)
                for t in trader.trade_history[-10:]:
                    t2 = dict(t); t2["agent_id"] = aid
                    recent_trades.append(t2)

            recent_trades.sort(key=lambda x: x.get("closed_at",""), reverse=True)

            return jsonify({
                "leaderboard":    leaderboard,
                "signals":        signals,
                "regime":         regime,
                "risk":           risk,
                "positions":      positions,
                "recent_trades":  recent_trades[:30],
                "elimination_log": elim_log,
                "price_cache_age": round(price_cache.age_seconds()),
                "cached_coins":    len(current_prices),
            })
        except Exception as e:
            logger.error(f"API hatası: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    return app
