from flask import Flask, jsonify
from flask_cors import CORS

import websocket
import threading
import requests
import json
import time

from datetime import datetime

# ==========================================
# CONFIG
# ==========================================

SYMBOL = "BTCUSDT"

TIMEFRAMES = ["1m", "5m"]

UPDATE_INTERVAL = 5

HISTORY_LIMIT = 120

# ==========================================
# APP
# ==========================================

app = Flask(__name__)

CORS(app)

# ==========================================
# GLOBAL
# ==========================================

market_data = {}

live_price = 0

last_update = 0

histories = {
    tf: []
    for tf in TIMEFRAMES
}

# ==========================================
# ROUND
# ==========================================

def r(v):

    if v is None:
        return None

    return round(float(v), 2)

# ==========================================
# LOAD HISTORY
# ==========================================

def load_history(interval):

    url = (
        f"https://api.binance.com/api/v3/klines"
        f"?symbol={SYMBOL}"
        f"&interval={interval}"
        f"&limit=120"
    )

    data = requests.get(url).json()

    candles = []

    for c in data:

        candles.append({

            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5])
        })

    return candles

# ==========================================
# EMA
# ==========================================

def ema(values, period):

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    value = sum(values[:period]) / period

    for p in values[period:]:

        value = ((p - value) * multiplier) + value

    return r(value)

# ==========================================
# RSI
# ==========================================

def rsi(values, period=14):

    if len(values) < period + 1:
        return None

    gains = 0

    losses = 0

    for i in range(-period, 0):

        diff = values[i] - values[i - 1]

        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)

    if losses == 0:
        return 100

    rs = gains / losses

    return r(100 - (100 / (1 + rs)))

# ==========================================
# ANALYZE
# ==========================================

def analyze(interval):

    candles = histories[interval]

    closes = [c["close"] for c in candles]

    highs = [c["high"] for c in candles]

    lows = [c["low"] for c in candles]

    volumes = [c["volume"] for c in candles]

    ema20 = ema(closes, 20)

    ema50 = ema(closes, 50)

    rsi14 = rsi(closes)

    support = min(lows[-20:])

    resistance = max(highs[-20:])

    avg_volume = sum(volumes[-20:]) / 20

    volume_ratio = volumes[-1] / avg_volume

    trend = "neutral"

    if ema20 and ema50:

        if ema20 > ema50:
            trend = "bullish"

        elif ema20 < ema50:
            trend = "bearish"

    return {

        "price": r(closes[-1]),

        "ema20": ema20,

        "ema50": ema50,

        "rsi14": rsi14,

        "support": r(support),

        "resistance": r(resistance),

        "volume_ratio": r(volume_ratio),

        "trend": trend
    }

# ==========================================
# AI ENGINE
# ==========================================

def build_signal(tf5, tf1):

    long_score = 0

    short_score = 0

    reasons = []

    # 5M TREND

    if tf5["trend"] == "bullish":

        long_score += 30

        reasons.append("5m bullish")

    elif tf5["trend"] == "bearish":

        short_score += 30

        reasons.append("5m bearish")

    # RSI

    if tf1["rsi14"]:

        if tf1["rsi14"] > 60:

            long_score += 20

            reasons.append("bullish momentum")

        elif tf1["rsi14"] < 40:

            short_score += 20

            reasons.append("bearish momentum")

    # VOLUME

    if tf1["volume_ratio"] > 1.2:

        if tf1["trend"] == "bullish":

            long_score += 20

            reasons.append("bullish volume")

        elif tf1["trend"] == "bearish":

            short_score += 20

            reasons.append("bearish volume")

    # FINAL

    direction = "neutral"

    confidence = 0

    if long_score > short_score:

        confidence = long_score / 100

        if confidence >= 0.60:

            direction = "long"

    elif short_score > long_score:

        confidence = short_score / 100

        if confidence >= 0.60:

            direction = "short"

    return {

        "direction": direction,

        "confidence": r(confidence),

        "long_score": long_score,

        "short_score": short_score,

        "reasons": reasons
    }

# ==========================================
# BUILD MARKET
# ==========================================

def build_market():

    global market_data

    tf5 = analyze("5m")

    tf1 = analyze("1m")

    signal = build_signal(tf5, tf1)

    stop_loss = None

    take_profit = None

    if signal["direction"] == "long":

        stop_loss = tf1["support"]

        risk = live_price - stop_loss

        take_profit = live_price + (risk * 2)

    elif signal["direction"] == "short":

        stop_loss = tf1["resistance"]

        risk = stop_loss - live_price

        take_profit = live_price - (risk * 2)

    market_data = {

        "symbol": SYMBOL,

        "timestamp": datetime.now().isoformat(),

        "live_price": r(live_price),

        "signal": signal,

        "trade_plan": {

            "entry": r(live_price),

            "stop_loss": r(stop_loss),

            "take_profit": r(take_profit)
        },

        "timeframes": {

            "5m": tf5,

            "1m": tf1
        }
    }

# ==========================================
# SOCKET
# ==========================================

def on_message(ws, message):

    global live_price
    global last_update

    payload = json.loads(message)

    if "stream" not in payload:
        return

    stream = payload["stream"]

    data = payload["data"]

    # PRICE

    if "@miniTicker" in stream:

        live_price = float(data["c"])

    # KLINE

    if "@kline_" in stream:

        candle = data["k"]

        interval = candle["i"]

        if interval not in histories:
            return

        new_data = {

            "high": float(candle["h"]),
            "low": float(candle["l"]),
            "close": float(candle["c"]),
            "volume": float(candle["v"])
        }

        if histories[interval]:

            histories[interval][-1] = new_data

        else:

            histories[interval].append(new_data)

        histories[interval] = histories[interval][-HISTORY_LIMIT:]

    # UPDATE

    now = time.time()

    if now - last_update >= UPDATE_INTERVAL:

        build_market()

        last_update = now

# ==========================================
# SOCKET EVENTS
# ==========================================

def on_error(ws, error):

    print("ERROR:", error)

def on_close(ws, a, b):

    print("Disconnected Binance")

def on_open(ws):

    print("Connected Binance")

# ==========================================
# START SOCKET
# ==========================================

def start_socket():

    streams = [

        f"{SYMBOL.lower()}@miniTicker",

        f"{SYMBOL.lower()}@kline_1m",

        f"{SYMBOL.lower()}@kline_5m"
    ]

    socket = (
        "wss://stream.binance.com:9443/stream?streams="
        + "/".join(streams)
    )

    ws = websocket.WebSocketApp(

        socket,

        on_open=on_open,

        on_message=on_message,

        on_error=on_error,

        on_close=on_close
    )

    ws.run_forever()

# ==========================================
# ENGINE
# ==========================================

def engine():

    print("\nLOADING AI ENGINE...\n")

    for tf in TIMEFRAMES:

        histories[tf] = load_history(tf)

        print(tf, "READY")

    print("\nSYSTEM ONLINE\n")

    while True:

        try:

            start_socket()

        except Exception as e:

            print("SOCKET ERROR:", e)

        print("Reconnect after 5 sec...")

        time.sleep(5)

# ==========================================
# ROUTES
# ==========================================

@app.route("/")

def home():

    return jsonify({

        "status": "ONLINE"
    })

@app.route("/market")

def market():

    return jsonify(market_data)

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    thread = threading.Thread(
        target=engine
    )

    thread.daemon = True

    thread.start()

    app.run(
        host="0.0.0.0",
        port=8000,
        threaded=True
    )

