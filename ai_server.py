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

prices = []


# =========================
# FETCH PRICE
# =========================

def fetch_price():

    urls = [

        "https://api.coindesk.com/v1/bpi/currentprice/BTC.json",

        "https://api.coinbase.com/v2/prices/spot?currency=USD"
    ]

    for url in urls:

        try:

            response = requests.get(url, timeout=10)

            data = response.json()

            # COINDESK
            if "coindesk" in url:

                price = data["bpi"]["USD"]["rate"]

                price = price.replace(",", "")

                return float(price)

            # COINBASE
            else:

                return float(data["data"]["amount"])

        except:
            continue

    raise Exception("All price APIs failed")


# =========================
# EMA
# =========================

def ema(data, period):

    if len(data) < period:
        return None

    multiplier = 2 / (period + 1)

    ema_value = sum(data[:period]) / period

    for price in data[period:]:
        ema_value = (
            (price - ema_value) * multiplier
        ) + ema_value

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

    avg_gain = (
        sum(gains[-period:]) / period
        if gains else 0.01
    )

    avg_loss = (
        sum(losses[-period:]) / period
        if losses else 0.01
    )

    rs = avg_gain / avg_loss

    return round(
        100 - (100 / (1 + rs)),
        2
    )


# =========================
# SIGNAL ENGINE
# =========================

def signal_logic(price, ema20, ema50, rsi14):

    signal = {
        "direction": "WAIT",
        "confidence": 0,
        "reasons": []
    }

    if (
        ema20 and
        ema50 and
        rsi14
    ):

        # LONG
        if (
            price > ema20 and
            ema20 > ema50 and
            rsi14 > 55
        ):

            signal["direction"] = "LONG"

            signal["confidence"] = 75

            signal["reasons"] = [
                "Bullish EMA trend",
                "Strong RSI momentum"
            ]

        # SHORT
        elif (
            price < ema20 and
            ema20 < ema50 and
            rsi14 < 45
        ):

            signal["direction"] = "SHORT"

            signal["confidence"] = 75

            signal["reasons"] = [
                "Bearish EMA trend",
                "Weak RSI momentum"
            ]

    return signal


# =========================
# ENGINE
# =========================

def update_market():

    global market_data
    global prices

    while True:

        try:

            price = fetch_price()

            prices.append(price)

            if len(prices) > 200:
                prices.pop(0)

            ema20 = ema(prices, 20)
            ema50 = ema(prices, 50)

            rsi14 = rsi(prices)

            structure = "RANGE"

            if ema20 and ema50:

                if price > ema20 > ema50:
                    structure = "BULLISH"

                elif price < ema20 < ema50:
                    structure = "BEARISH"

            signal = signal_logic(
                price,
                ema20,
                ema50,
                rsi14
            )

            market_data = {

                "status": "ONLINE",

                "symbol": "BTCUSD",

                "live_price": price,

                "market_structure": structure,

                "signal": signal,

                "indicators": {

                    "ema20": ema20,

                    "ema50": ema50,

                    "rsi14": rsi14
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
