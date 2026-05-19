"""
Bot v3 — Multi-pair crypto signal bot
Pairs    : BTCUSDT, ETHUSDT, SOLUSDT
Interval : 1h candles
BUY rule : ≥58 % of technical indicators agree → BUY signal
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

try:
    import ccxt
    import pandas as pd
    import pandas_ta as ta
except ImportError as e:
    raise SystemExit(
        f"Missing dependency: {e}\n"
        "Install with: pip install ccxt pandas pandas-ta"
    )

# ── Config ────────────────────────────────────────────────────────────────────
PAIRS     = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
INTERVAL  = "1h"
BUY_THRESHOLD = 0.58          # ≥58 % of indicators must agree

LOOP_SECONDS = 60             # how often to re-check (seconds)
CANDLES      = 100            # history needed for indicator warmup

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot_v3")


# ── Exchange ──────────────────────────────────────────────────────────────────
def build_exchange() -> ccxt.Exchange:
    exchange = ccxt.binance({"enableRateLimit": True})
    exchange.load_markets()
    return exchange


def fetch_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").astype(float)
    return df


# ── Signal logic ──────────────────────────────────────────────────────────────
def compute_signals(df: pd.DataFrame) -> dict[str, str]:
    """
    Return a dict of {indicator_name: "BUY" | "SELL" | "NEUTRAL"} for the latest candle.
    Uses: RSI, MACD, EMA cross, Bollinger Bands, Stochastic, ADX.
    """
    c = df["close"]
    h = df["high"]
    l = df["low"]
    signals: dict[str, str] = {}

    # 1. RSI-14
    rsi = ta.rsi(c, length=14)
    if rsi is not None and not rsi.empty:
        v = rsi.iloc[-1]
        signals["RSI"] = "BUY" if v < 50 else "SELL" if v > 60 else "NEUTRAL"

    # 2. MACD (12,26,9)
    macd_df = ta.macd(c, fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        hist = macd_df["MACDh_12_26_9"].iloc[-1]
        prev = macd_df["MACDh_12_26_9"].iloc[-2]
        signals["MACD"] = "BUY" if hist > 0 and hist > prev else "SELL" if hist < 0 and hist < prev else "NEUTRAL"

    # 3. EMA cross (9 / 21)
    ema9  = ta.ema(c, length=9)
    ema21 = ta.ema(c, length=21)
    if ema9 is not None and ema21 is not None:
        signals["EMA_cross"] = "BUY" if ema9.iloc[-1] > ema21.iloc[-1] else "SELL"

    # 4. Bollinger Bands (20, 2)
    bb = ta.bbands(c, length=20, std=2)
    if bb is not None and not bb.empty:
        price = c.iloc[-1]
        lower = bb["BBL_20_2.0"].iloc[-1]
        upper = bb["BBU_20_2.0"].iloc[-1]
        mid   = bb["BBM_20_2.0"].iloc[-1]
        if price < lower:
            signals["BB"] = "BUY"
        elif price > upper:
            signals["BB"] = "SELL"
        else:
            signals["BB"] = "BUY" if price < mid else "SELL"

    # 5. Stochastic (14,3)
    stoch = ta.stoch(h, l, c, k=14, d=3)
    if stoch is not None and not stoch.empty:
        k = stoch["STOCHk_14_3_3"].iloc[-1]
        signals["Stoch"] = "BUY" if k < 50 else "SELL"

    # 6. ADX trend strength (14) — only signal when trending
    adx_df = ta.adx(h, l, c, length=14)
    if adx_df is not None and not adx_df.empty:
        adx  = adx_df["ADX_14"].iloc[-1]
        dmp  = adx_df["DMP_14"].iloc[-1]
        dmn  = adx_df["DMN_14"].iloc[-1]
        if adx > 25:
            signals["ADX"] = "BUY" if dmp > dmn else "SELL"
        else:
            signals["ADX"] = "NEUTRAL"

    return signals


def evaluate(signals: dict[str, str]) -> tuple[str, float]:
    """Return (action, buy_pct) where action is BUY / SELL / HOLD."""
    total = len(signals)
    if total == 0:
        return "HOLD", 0.0
    buys  = sum(1 for v in signals.values() if v == "BUY")
    sells = sum(1 for v in signals.values() if v == "SELL")
    buy_pct  = buys  / total
    sell_pct = sells / total
    if buy_pct >= BUY_THRESHOLD:
        return "BUY", buy_pct
    if sell_pct >= BUY_THRESHOLD:
        return "SELL", sell_pct
    return "HOLD", buy_pct


# ── Main loop ─────────────────────────────────────────────────────────────────
def run_once(exchange: ccxt.Exchange) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log.info("── Scan @ %s ──────────────────", now)

    for symbol in PAIRS:
        try:
            df = fetch_ohlcv(exchange, symbol, INTERVAL, CANDLES)
            signals = compute_signals(df)
            action, pct = evaluate(signals)

            detail = " | ".join(f"{k}:{v}" for k, v in signals.items())
            log.info(
                "%-10s  %s  buy=%.0f%%  [%s]",
                symbol, action, pct * 100, detail,
            )

            if action == "BUY":
                on_buy_signal(symbol, df["close"].iloc[-1], pct)
            elif action == "SELL":
                on_sell_signal(symbol, df["close"].iloc[-1], pct)

        except Exception as exc:
            log.error("Error processing %s: %s", symbol, exc)


def on_buy_signal(symbol: str, price: float, confidence: float) -> None:
    """Hook: called when a BUY signal fires. Replace with real order logic."""
    log.warning("*** BUY  %s @ %.4f  (confidence %.0f%%) ***", symbol, price, confidence * 100)


def on_sell_signal(symbol: str, price: float, confidence: float) -> None:
    """Hook: called when a SELL signal fires."""
    log.warning("*** SELL %s @ %.4f  (confidence %.0f%%) ***", symbol, price, confidence * 100)


def main() -> None:
    log.info("Bot v3 starting — pairs=%s  interval=%s  BUY≥%.0f%%",
             [p.replace("/", "") for p in PAIRS], INTERVAL, BUY_THRESHOLD * 100)
    exchange = build_exchange()
    log.info("Exchange ready: %s", exchange.id)

    while True:
        try:
            run_once(exchange)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as exc:
            log.error("Unhandled error in main loop: %s", exc)
        time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()
