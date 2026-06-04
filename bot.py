#!/usr/bin/env python3
"""
Kronos Paper Trader — bot.py
Runs every hour via GitHub Actions.
Signals: Kronos-small on BTC/USDT, ETH/USDT, SOL/USDT
Capital:  5 000 € simulados, estado en Supabase
"""

import os, sys, logging
from datetime import datetime, timezone
import pandas as pd
import ccxt
from supabase import create_client, Client

# ── Kronos path (clonado por el workflow de CI) ─────────────────
sys.path.insert(0, os.environ.get("KRONOS_PATH", "kronos_repo"))
from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

# ══════════════════════════════════════════════════════════════
#  Parámetros — ajusta aquí si quieres experimentar
# ══════════════════════════════════════════════════════════════
PAIRS            = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME        = "1h"
LOOKBACK         = 400          # velas históricas que ingesta Kronos
PRED_LEN         = 24           # predicción de las próximas 24 h
INITIAL_CAPITAL  = 5_000.0      # euros simulados
MAX_POSITIONS    = 3            # posiciones simultáneas máximas
ENTRY_THRESH     = 0.015        # necesita +1.5 % de retorno esperado para entrar
EXIT_THRESH      = 0.005        # cierra si el forecast cae por debajo de +0.5 %
STOP_LOSS        = 0.02         # cierre duro en -2 %
FEE              = 0.001        # 0.1 % por lado (comisión Binance taker)
PAUSE_DRAWDOWN   = 0.10         # pausa si -10 % desde el máximo histórico
SAMPLE_COUNT     = 3            # muestras de Kronos a promediar (más = más lento)
MIN_TRADE_EUR    = 20.0         # tamaño mínimo de operación

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("kronos-bot")

_now = lambda: datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════
#  Helpers Supabase
# ══════════════════════════════════════════════════════════════

def get_or_init_portfolio(sb: Client) -> dict:
    """Devuelve la última fila del portfolio; la crea si está vacío."""
    res = (sb.table("portfolio")
             .select("*")
             .order("created_at", desc=True)
             .limit(1)
             .execute())
    if res.data:
        return res.data[0]
    row = {
        "cash": INITIAL_CAPITAL, "total_value": INITIAL_CAPITAL,
        "peak_value": INITIAL_CAPITAL, "open_positions_count": 0,
        "paused": False, "created_at": _now(),
    }
    sb.table("portfolio").insert(row).execute()
    log.info(f"Portfolio inicializado con {INITIAL_CAPITAL:.0f} €")
    return row


def get_open_positions(sb: Client) -> dict:
    """Devuelve {symbol: trade_row} de todas las posiciones abiertas."""
    res = sb.table("trades").select("*").eq("status", "open").execute()
    return {r["symbol"]: r for r in (res.data or [])}


def db_open_trade(sb, symbol, price, qty, cost, exp_ret):
    sb.table("trades").insert({
        "symbol": symbol, "entry_price": price, "qty": qty,
        "cost": cost, "status": "open", "entry_time": _now(),
        "expected_return": exp_ret,
    }).execute()
    log.info(f"  ABRIR  {symbol}  qty={qty:.6f}  coste={cost:.2f}€  exp={exp_ret*100:+.2f}%")


def db_close_trade(sb, trade_id, price, pnl, reason):
    sb.table("trades").update({
        "status": "closed", "exit_price": price,
        "exit_time": _now(), "pnl": pnl, "close_reason": reason,
    }).eq("id", trade_id).execute()
    log.info(f"  CERRAR  id={trade_id}  precio={price:.4f}  pnl={pnl:+.2f}€  motivo={reason}")


def db_save_signal(sb, symbol, price, pred24, exp_ret):
    sb.table("signals").insert({
        "symbol": symbol, "current_price": price,
        "predicted_price_24h": pred24, "expected_return": exp_ret,
        "created_at": _now(),
    }).execute()


def db_save_portfolio(sb, cash, total, peak, n_open, paused):
    sb.table("portfolio").insert({
        "cash": cash, "total_value": total, "peak_value": peak,
        "open_positions_count": n_open, "paused": paused,
        "created_at": _now(),
    }).execute()


# ══════════════════════════════════════════════════════════════
#  Datos de mercado
# ══════════════════════════════════════════════════════════════

def fetch_ohlcv(exchange, symbol: str) -> pd.DataFrame:
    """Descarga las últimas LOOKBACK velas de 1h desde Binance."""
    raw = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=LOOKBACK + 1)
    df  = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.iloc[:-1].reset_index(drop=True)   # elimina la vela incompleta actual


# ══════════════════════════════════════════════════════════════
#  Kronos
# ══════════════════════════════════════════════════════════════

def load_kronos() -> KronosPredictor:
    log.info("Cargando Kronos-small …")
    tok   = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    pred  = KronosPredictor(model, tok, max_context=512)
    log.info("Kronos listo.")
    return pred


def get_signal(kronos: KronosPredictor, df: pd.DataFrame) -> tuple[float, float]:
    """
    Retorna (retorno_esperado_24h, precio_predicho_24h).
    retorno_esperado = (precio_predicho - precio_actual) / precio_actual
    """
    last_ts   = df["timestamp"].iloc[-1]
    future_ts = pd.date_range(last_ts + pd.Timedelta(hours=1),
                               periods=PRED_LEN, freq="1h", tz="UTC")
    pred_df = kronos.predict(
        df=df[["open","high","low","close","volume"]],
        x_timestamp=df["timestamp"],
        y_timestamp=pd.Series(future_ts),
        pred_len=PRED_LEN, T=1.0, top_p=0.9,
        sample_count=SAMPLE_COUNT,
    )
    precio_actual  = float(df["close"].iloc[-1])
    precio_pred    = float(pred_df["close"].iloc[-1])
    return (precio_pred - precio_actual) / precio_actual, precio_pred


# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════

def main():
    log.info("━━━━━━━━━━━━━━━━  Kronos Paper Trader — inicio  ━━━━━━━━━━━━━━━━")

    sb       = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    exchange = ccxt.binance({"enableRateLimit": True})
    kronos   = load_kronos()

    # ── 1. Cargar estado ──────────────────────────────────────
    pf        = get_or_init_portfolio(sb)
    cash      = float(pf["cash"])
    peak      = float(pf["peak_value"])
    paused    = bool(pf["paused"])
    positions = get_open_positions(sb)
    log.info(f"Estado  cash={cash:.2f}€  posiciones={len(positions)}  pausado={paused}")

    # ── 2. Señales Kronos para todos los pares ────────────────
    signals: dict[str, dict] = {}
    for sym in PAIRS:
        log.info(f"── {sym}")
        try:
            df  = fetch_ohlcv(exchange, sym)
            exp, pred24 = get_signal(kronos, df)
            price = float(df["close"].iloc[-1])
            db_save_signal(sb, sym, price, pred24, exp)
            signals[sym] = {"price": price, "exp_ret": exp}
            log.info(f"   precio={price:,.4f}  pred24h={pred24:,.4f}  exp={exp*100:+.2f}%")
        except Exception as e:
            log.error(f"   error en {sym}: {e}")

    if not signals:
        log.error("Sin señales — abortando esta ejecución")
        return

    # ── 3. Gestionar posiciones abiertas ──────────────────────
    for sym, pos in list(positions.items()):
        if sym not in signals:
            continue
        price    = signals[sym]["price"]
        exp      = signals[sym]["exp_ret"]
        entry    = float(pos["entry_price"])
        qty      = float(pos["qty"])
        ret      = (price - entry) / entry
        proceeds = qty * price * (1 - FEE)

        if ret <= -STOP_LOSS:
            # Stop loss duro
            pnl = proceeds - float(pos["cost"])
            db_close_trade(sb, pos["id"], price, pnl, "stop_loss")
            cash += proceeds
            del positions[sym]
            log.warning(f"  STOP-LOSS {sym}  ret={ret*100:.2f}%  pnl={pnl:+.2f}€")

        elif exp < EXIT_THRESH and ret > 0:
            # La señal se ha debilitado, tomamos beneficios
            pnl = proceeds - float(pos["cost"])
            db_close_trade(sb, pos["id"], price, pnl, "signal_exit")
            cash += proceeds
            del positions[sym]

    # ── 4. Abrir nuevas posiciones ────────────────────────────
    if not paused:
        # Calcular valor actual del portfolio para sizing equitativo
        pos_value_now = sum(
            float(positions[s]["qty"]) * signals[s]["price"]
            for s in positions if s in signals
        )
        total_now    = cash + pos_value_now
        target_size  = (total_now / MAX_POSITIONS) * 0.95   # 95% para dejar margen

        # Ordenar oportunidades de mayor a menor retorno esperado
        opps = sorted(
            [(s, d) for s, d in signals.items()
             if s not in positions and d["exp_ret"] >= ENTRY_THRESH],
            key=lambda x: x[1]["exp_ret"], reverse=True
        )
        for sym, sig in opps:
            if len(positions) >= MAX_POSITIONS:
                break
            size = min(target_size, cash * 0.95)
            if size < MIN_TRADE_EUR:
                log.info(f"  Sin capital suficiente para abrir {sym}")
                break
            cost = size * (1 + FEE)
            if cost > cash:
                continue
            qty   = size / sig["price"]
            cash -= cost
            db_open_trade(sb, sym, sig["price"], qty, cost, sig["exp_ret"])
            positions[sym] = {"qty": qty, "cost": cost}

    # ── 5. Calcular valor total y guardar estado ──────────────
    pos_value = sum(
        float(p.get("qty", 0)) * signals.get(s, {}).get("price", 0)
        for s, p in positions.items()
    )
    total = cash + pos_value
    peak  = max(peak, total)
    roi   = (total - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # Comprobar drawdown → pausar
    if total < peak * (1 - PAUSE_DRAWDOWN):
        if not paused:
            log.warning(f"⚠ DRAWDOWN >{PAUSE_DRAWDOWN*100:.0f}% — pausando el bot")
        paused = True
    elif paused and total > peak * (1 - PAUSE_DRAWDOWN / 2):
        paused = False
        log.info("Recuperación detectada — reanudando trading")

    db_save_portfolio(sb, cash, total, peak, len(positions), paused)
    log.info(
        f"━━━  Fin  cash={cash:.2f}€  posiciones={pos_value:.2f}€  "
        f"total={total:.2f}€  ROI={roi:+.2f}%  ━━━"
    )


if __name__ == "__main__":
    main()
