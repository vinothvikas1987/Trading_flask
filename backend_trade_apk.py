from flask import Flask, request, jsonify
import yfinance as yf
import pandas as pd
import pytz
from datetime import datetime
import ta

app = Flask(__name__)

def get_high_low(df, label):
    if df.empty:
        return {f"{label} High": None, f"{label} Low": None}
    return {
        f"{label} High": df['High'].max(),
        f"{label} Low": df['Low'].min()
    }

@app.route('/analyze', methods=['GET'])
def analyze():
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        return jsonify({"Error": "Ticker is required"}), 400

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="max")
    except Exception as e:
        return jsonify({"Error": f"Could not fetch data: {e}"}), 500

    if df.empty:
        return jsonify({"Error": f"No data found for {ticker}"}), 404

    df['MA50'] = df['Close'].rolling(window=50).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    df['RSI'] = ta.momentum.RSIIndicator(df['Close']).rsi()

    latest = df.iloc[-1]
    current_price = latest['Close']
    ma50 = latest['MA50']
    ma200 = latest['MA200']
    rsi = latest['RSI']

    try:
        info = stock.get_info()
        pe_ratio = info.get("trailingPE")
        roe = info.get("returnOnEquity")
    except Exception:
        pe_ratio = None
        roe = None

    decision = "Hold"
    reasons = []

    if pd.notna(ma200):
        if current_price > ma200:
            reasons.append("Price above 200-day MA (uptrend)")
        else:
            reasons.append("Price below 200-day MA (downtrend)")
    else:
        reasons.append("200-day MA not available")

    if pd.notna(rsi):
        if 40 <= rsi <= 60:
            reasons.append(f"RSI is neutral at {rsi:.2f}")
        elif rsi > 70:
            reasons.append(f"RSI is overbought at {rsi:.2f}")
        elif rsi < 30:
            reasons.append(f"RSI is oversold at {rsi:.2f}")
    else:
        reasons.append("RSI not available")

    if pe_ratio is not None:
        if pe_ratio < 25:
            reasons.append(f"PE ratio is attractive at {pe_ratio}")
        else:
            reasons.append(f"PE ratio is high at {pe_ratio}")

    if roe is not None:
        reasons.append(f"ROE: {roe*100:.2f}%")

    if pd.notna(ma200) and pd.notna(rsi):
        if current_price < ma200 and 40 <= rsi <= 60 and (pe_ratio is None or pe_ratio < 30):
            decision = "Buy"
        elif current_price > ma200 or rsi > 70:
            decision = "Sell"

    tz = pytz.timezone("Asia/Kolkata")
    current_year = datetime.now(tz).year
    high_low_data = {}

    for y in [1, 2, 3, 4, 5, 10]:
        year_to_analyze = current_year - y + 1
        start = pd.Timestamp(f"{year_to_analyze}-01-01", tz=tz)
        end = pd.Timestamp(f"{year_to_analyze}-12-31", tz=tz)
        df_period = df[(df.index >= start) & (df.index <= end)]
        high_low_data.update(get_high_low(df_period, f"{y} Year"))

    high_low_data.update(get_high_low(df, "Max"))

    high_vals = []
    low_vals = []
    for y in [1, 2, 3]:
        high = high_low_data.get(f"{y} Year High")
        low = high_low_data.get(f"{y} Year Low")
        if high is not None:
            high_vals.append(high)
        if low is not None:
            low_vals.append(low)

    if len(high_vals) == 3:
        avg_high_3yr = sum(high_vals) / 3
        if current_price > avg_high_3yr:
            reasons.append(f"Alert triggered for Sell: Current price {current_price:.2f} > 3-year average high {avg_high_3yr:.2f}")
        else:
            reasons.append(f"No trigger for sell")

    if len(low_vals) == 3:
        avg_low_3yr = sum(low_vals) / 3
        if current_price < avg_low_3yr:
            reasons.append(f"Alert triggered for Buy: Current price {current_price:.2f} < 3-year average low {avg_low_3yr:.2f}")
        else:
            reasons.append(f"No trigger for buy")

    return jsonify({
        "Ticker": ticker,
        "Current Price": round(current_price, 2),
        "50-day MA": round(ma50, 2) if pd.notna(ma50) else "N/A",
        "200-day MA": round(ma200, 2) if pd.notna(ma200) else "N/A",
        "RSI": round(rsi, 2) if pd.notna(rsi) else "N/A",
        "PE Ratio": pe_ratio if pe_ratio is not None else "Unavailable",
        "ROE": f"{roe*100:.2f}%" if roe is not None else "Unavailable",
        "Decision": decision,
        "Reasons": reasons,
        **high_low_data
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

