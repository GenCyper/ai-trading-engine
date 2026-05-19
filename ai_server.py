from flask import Flask, jsonify
from flask_cors import CORS
import requests
import threading
import time

app = Flask(__name__)
CORS(app)

market_data = {
    "status": "STARTING"
}

SYMBOL = "BTCUSDT"


# =========================
# BYBIT FETCH
# =========================

def get_klines(interval="1", limit=100):

    interval_map = {
        "1m": "1",
        "5m": "5",
        "15m": "15"
    }

    bybit_interval = interval_map.get(interval, "1")

    url = (
        f"https://api.bybit.com/v5/market/kline"
        f"?category=linear"
        f"&symbol={SYMBOL}"
        f"&interval={bybit_interval}"
        f"&limit={limit}"
    )

    response = requests.get(url, timeout=10)

    data = response.json()

    if data["retCode"] != 0:
        raise Exception(data["retMsg"])

    candles = data["result"]["list"]

    closes = []
    highs = []
    lows = []

    # Bybit trả nến mới nhất trước
    candles.reverse()

    for c in candles:

        closes.append(float(c[4]))
        highs.append(float(c[2]))
        lows.append(float(c[3]))

    return closes, highs, lows


# =========================
# EMA
# =========================

def ema(data, period):

    if len(data) < period:
        return None

    multiplier = 2 / (period + 1)

    ema_value = sum(data[:period]) / period

    for price in data[period:]:
        ema_value = (price - ema_value) * multiplier + ema_value

    return round(ema_value, 2)


# =========================
# RSI
# =========================

def rsi(data, period=14):

    if len(data) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(data)):

        diff = data[i] - data[i - 1]

        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period if gains else 0.01
    avg_loss = sum(losses[-period:]) / period if losses else 0.01

    rs = avg_gain / avg_loss

    return round(100 - (100 / (1 + rs)), 2)


# =========================
# STRUCTURE
# =========================

def structure(price, ema20, ema50):

    if ema20 is None or ema50 is None:
        return "UNKNOWN"

    if price > ema20 > ema50:
        return "BULLISH"

    if price < ema20 < ema50:
        return "BEARISH"

    return "RANGE"


# =========================
# SIGNAL ENGINE
# =========================

def signal_logic(price, ema20, ema50, rsi_value):

    signal = {
        "direction": "WAIT",
        "confidence": 0,
        "reasons": []
    }

    if (
        price > ema20 and
        ema20 > ema50 and
        rsi_value > 55
    ):

        signal["direction"] = "LONG"
        signal["confidence"] = 78

        signal["reasons"] = [
            "Bullish EMA alignment",
            "Strong RSI momentum"
        ]

    elif (
        price < ema20 and
        ema20 < ema50 and
        rsi_value < 45
    ):

        signal["direction"] = "SHORT"
        signal["confidence"] = 76

        signal["reasons"] = [
            "Bearish EMA alignment",
            "Weak RSI momentum"
        ]

    return signal


# =========================
# UPDATE ENGINE
# =========================

def update_market():

    global market_data

    while True:

        try:

            # ========= 1M =========

            closes_1m, highs_1m, lows_1m = get_klines("1m")

            price = closes_1m[-1]

            ema20_1m = ema(closes_1m, 20)
            ema50_1m = ema(closes_1m, 50)

            rsi_1m = rsi(closes_1m)

            support_1m = round(min(lows_1m[-20:]), 2)
            resistance_1m = round(max(highs_1m[-20:]), 2)

            structure_1m = structure(
                price,
                ema20_1m,
                ema50_1m
            )

            signal = signal_logic(
                price,
                ema20_1m,
                ema50_1m,
                rsi_1m
            )

            # ========= 5M =========

            closes_5m, highs_5m, lows_5m = get_klines("5m")

            ema20_5m = ema(closes_5m, 20)
            ema50_5m = ema(closes_5m, 50)

            structure_5m = structure(
                price,
                ema20_5m,
                ema50_5m
            )

            # ========= 15M =========

            closes_15m, highs_15m, lows_15m = get_klines("15m")

            ema20_15m = ema(closes_15m, 20)
            ema50_15m = ema(closes_15m, 50)

            structure_15m = structure(
                price,
                ema20_15m,
                ema50_15m
            )

            # ========= SESSION =========

            current_hour = time.gmtime().tm_hour

            if 0 <= current_hour < 8:
                session = "ASIA"
            elif 8 <= current_hour < 16:
                session = "LONDON"
            else:
                session = "NEW_YORK"

            # ========= SAVE =========

            market_data = {

                "status": "ONLINE",

                "symbol": SYMBOL,

                "live_price": price,

                "market_session": session,

                "signal": signal,

                "timeframes": {

                    "1m": {
                        "price": price,
                        "ema20": ema20_1m,
                        "ema50": ema50_1m,
                        "rsi14": rsi_1m,
                        "support": support_1m,
                        "resistance": resistance_1m,
                        "structure": structure_1m
                    },

                    "5m": {
                        "ema20": ema20_5m,
                        "ema50": ema50_5m,
                        "structure": structure_5m
                    },

                    "15m": {
                        "ema20": ema20_15m,
                        "ema50": ema50_15m,
                        "structure": structure_15m
                    }
                },

                "risk_management": {
                    "max_trades_per_day": 3,
                    "risk_reward": 2
                },

                "warnings": [
                    "Always use stop loss",
                    "Avoid revenge trade",
                    "Avoid over leverage"
                ]
            }

            print("UPDATED:", price)

            time.sleep(5)

        except Exception as e:

            market_data = {
                "status": "ERROR",
                "message": str(e)
            }

            print("ERROR:", e)

            time.sleep(10)


# =========================
# START ENGINE
# =========================

threading.Thread(
    target=update_market,
    daemon=True
).start()


# =========================
# ROUTES
# =========================

@app.route("/")
def home():

    return jsonify({
        "status": "ONLINE"
    })


@app.route("/market")
def market():

    return jsonify(market_data)


# =========================
# RUN
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
