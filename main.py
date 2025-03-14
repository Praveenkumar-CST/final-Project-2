from flask import Flask, request, session, redirect, url_for
import yfinance as yf
from yahooquery import search
from flask_session import Session  # For server-side session storage
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)

# Configure session to use filesystem (server-side storage)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = "your_secret_key_here"  # Replace with a secure key
Session(app)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['Mydatabase']  # Database name: Mydatabase
collection = db['names']  # Collection name: names

def get_ticker_symbol(company_name):
    """Find the stock ticker symbol for a given company name from NSE/BSE only."""
    try:
        result = search(company_name)
        if "quotes" in result and result["quotes"]:
            for quote in result["quotes"]:
                if quote["exchange"] in ["NSI", "BSE"]:
                    return quote["symbol"]
        return "INVALID"
    except Exception:
        return None

def get_company_details(ticker):
    """Fetch company details from Yahoo Finance with error handling."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or "longName" not in info:
            return None
        details = {
            "Name": info.get("longName", "N/A"),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "CEO": info.get("companyOfficers", [{}])[0].get("name", "N/A"),
            "Market Cap": info.get("marketCap", 0),
            "P/E Ratio": info.get("trailingPE", "N/A"),
            "EPS": info.get("trailingEps", "N/A"),
            "Dividend Yield": info.get("dividendYield", "N/A") or 0,
            "Website": info.get("website", "N/A"),
            "Description": info.get("longBusinessSummary", "No description available."),
            "52W High": info.get("fiftyTwoWeekHigh", "N/A"),
            "52W Low": info.get("fiftyTwoWeekLow", "N/A"),
            "Beta": info.get("beta", "N/A"),
            "Avg Volume": info.get("averageVolume", "N/A"),
        }
        return details
    except Exception:
        return None

def get_stock_data(ticker):
    """Fetch live stock data with analysis and additional metrics."""
    try:
        stock = yf.Ticker(ticker)
        stock_info = stock.history(period="1mo", interval="1d")
        if stock_info.empty:
            return None

        latest_price = float(stock_info["Close"].iloc[-1])
        previous_close = float(stock_info["Close"].iloc[-2]) if len(stock_info) > 1 else latest_price
        price_change = latest_price - previous_close
        price_change_pct = (price_change / previous_close) * 100 if previous_close != 0 else 0
        high_price = float(stock_info["High"].max())
        low_price = float(stock_info["Low"].min())
        volume = int(stock_info["Volume"].iloc[-1])

        daily_returns = stock_info["Close"].pct_change().dropna()
        volatility = float(daily_returns.std() * (252 ** 0.5)) if not daily_returns.empty else "N/A"

        short_term_ma = float(stock_info["Close"].rolling(window=20).mean().iloc[-1])
        long_term_ma = float(stock_info["Close"].rolling(window=50).mean().iloc[-1])

        if latest_price > short_term_ma > long_term_ma:
            recommendation = "✅ Strong Buy"
            advice = "Uptrend confirmed! Buying now may be profitable."
        elif latest_price > short_term_ma:
            recommendation = "⚠️ Hold"
            advice = "Stock above short-term trend but below long-term average. Watch carefully."
        else:
            recommendation = "🚨 Sell"
            advice = "Stock below both moving averages. Consider selling."

        hist_data = stock.history(period="1y")
        yearly_change = float(((latest_price - hist_data["Close"].iloc[0]) / hist_data["Close"].iloc[0]) * 100)

        pe = stock.info.get("trailingPE", float('inf'))
        div_yield = stock.info.get("dividendYield", 0)
        health = "Strong" if pe < 20 and div_yield > 0.02 else "Moderate" if pe < 30 else "Weak"

        return (latest_price, high_price, low_price, volume, recommendation, advice, yearly_change,
                price_change, price_change_pct, volatility, health)
    except Exception:
        return None

def calculate_investment_suggestion(amount, years, latest_price, company_details, recommendation, volatility):
    """Calculate investment suggestion with additional detailed metrics."""
    try:
        amount = float(amount)
        years = int(years)
        if amount <= 0:
            return """
            <div class='investment-box error-box'>
                <h3>❌ Invalid Input</h3>
                <p>Amount must be greater than ₹0. Please enter a positive value.</p>
            </div>
            """

        num_shares = amount / latest_price
        total_investment = amount
        annual_return = company_details["Dividend Yield"] if company_details["Dividend Yield"] != "N/A" else 0.10
        future_value = total_investment * (1 + annual_return) ** years

        annualized_return = ((future_value / total_investment) ** (1 / years) - 1) * 100
        cumulative_return = ((future_value - total_investment) / total_investment) * 100

        annual_dividend_per_share = latest_price * annual_return
        total_dividends = annual_dividend_per_share * num_shares * years

        beta = company_details["Beta"] if isinstance(company_details["Beta"], (int, float)) else 1.0
        risk_adjusted_return = annualized_return / beta if beta != 0 else annualized_return

        vol_factor = volatility if isinstance(volatility, float) else 0.10
        lower_bound = future_value * (1 - vol_factor)
        upper_bound = future_value * (1 + vol_factor)

        suggestion = f"""
        <div class='investment-box'>
            <h3>💡 Investment Projection</h3>
            <p><strong>With ₹{amount:,.2f}</strong> invested in <strong>{company_details['Name']}</strong> for <strong>{years} years</strong>:</p>
            <p>📊 Shares: <strong>{num_shares:.2f}</strong> at ₹{latest_price:.2f} each</p>
            <p>💰 Initial Investment: <strong>₹{total_investment:,.2f}</strong></p>
            <p>📈 Projected Value: <strong>₹{future_value:,.2f}</strong> ({annual_return * 100:.1f}% annual return)</p>
            <p>📅 Annualized Return: <strong>{annualized_return:.2f}%</strong></p>
            <p>🌟 Cumulative Return: <strong>{cumulative_return:.2f}%</strong></p>
            <p>💵 Total Dividends Earned: <strong>₹{total_dividends:,.2f}</strong> (assuming constant yield)</p>
            <p>🛡️ Risk-Adjusted Return: <strong>{risk_adjusted_return:.2f}%</strong> (adjusted by Beta: {beta})</p>
            <p>📉 Value Range (Volatility ±{vol_factor * 100:.1f}%): <strong>₹{lower_bound:,.2f} - ₹{upper_bound:,.2f}</strong></p>
        """
        if num_shares < 1:
            suggestion += "<p class='warning'>⚠️ Note: Less than 1 share. Fractional shares may not be tradable on all platforms.</p>"
        if recommendation == "✅ Strong Buy":
            suggestion += "<p class='success'>✅ Great opportunity based on current trends!</p>"
        elif recommendation == "⚠️ Hold":
            suggestion += "<p class='warning'>⚠️ Monitor closely or diversify.</p>"
        else:
            suggestion += "<p class='danger'>🚨 Consider alternatives.</p>"
        suggestion += "<p class='note'>⚠️ Note: Projections assume stable conditions and constant dividend yield.</p></div>"
        return suggestion
    except ValueError:
        return "<div class='investment-box error-box'><h3>❌ Error</h3><p>Please enter valid numbers for amount and years.</p></div>"

def store_company_data(ticker, company_details, stock_data):
    """Store company data in MongoDB."""
    if company_details and stock_data:
        (latest_price, high_price, low_price, volume, recommendation, advice, yearly_change,
         price_change, price_change_pct, volatility, health) = stock_data

        # Prepare data to store
        data = {
            "ticker": ticker.upper(),
            "company_details": company_details,
            "stock_data": {
                "latest_price": latest_price,
                "high_price": high_price,
                "low_price": low_price,
                "volume": volume,
                "recommendation": recommendation,
                "advice": advice,
                "yearly_change": yearly_change,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "volatility": volatility,
                "health": health
            },
            "timestamp": datetime.utcnow()  # Store the time of data fetch
        }

        # Update or insert the document (upsert=True ensures it updates if exists, inserts if not)
        collection.update_one(
            {"ticker": ticker.upper()},
            {"$set": data},
            upsert=True
        )

@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize session history if not already present
    if "history" not in session:
        session["history"] = []

    stock_details = """
    <div class='welcome'>
        <h1>📈 Live Stock Advisor</h1>
        <p>Enter an Indian company name to analyze its stock performance.</p>
    </div>
    """

    # Get company_name from query parameter (if coming from history)
    prefilled_company = request.args.get("company_name", "")

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()

        if company_name:
            ticker = get_ticker_symbol(company_name)
            if ticker and ticker != "INVALID" and ticker is not None:
                # Add to history only if valid ticker and not already the last entry
                if not session["history"] or session["history"][-1] != company_name:
                    session["history"].append(company_name)
                    session.modified = True  # Ensure session updates

            if "amount" not in request.form:  # Initial lookup
                if not company_name:
                    stock_details = "<p class='error'>❌ Please enter a company name.</p>"
                else:
                    if ticker == "INVALID":
                        stock_details = "<p class='error'>❌ Only Indian stocks (NSE/BSE) are supported.</p>"
                    elif ticker is None:
                        stock_details = "<p class='error'>❌ Stock not found. Try another name.</p>"
                    else:
                        stock_data = get_stock_data(ticker)
                        company_details = get_company_details(ticker)

                        if not stock_data or not company_details:
                            stock_details = "<p class='error'>❌ Unable to fetch stock data.</p>"
                        else:
                            # Store data in MongoDB
                            store_company_data(ticker, company_details, stock_data)

                            (latest_price, high_price, low_price, volume, recommendation, advice, yearly_change,
                             price_change, price_change_pct, volatility, health) = stock_data
                            stock_details = f"""
                            <div class='stock-card'>
                                <h2>{company_details['Name']} ({ticker.upper()})</h2>
                                <p class='price'><strong>Live Price:</strong> <span>₹{latest_price:.2f}</span></p>
                                <div class='stats'>
                                    <p>🔼 <strong>High:</strong> ₹{high_price:.2f}</p>
                                    <p>🔽 <strong>Low:</strong> ₹{low_price:.2f}</p>
                                    <p>📊 <strong>Volume:</strong> {volume:,}</p>
                                    <p>📉 <strong>Avg Volume (3M):</strong> {company_details['Avg Volume']:,}</p>
                                    <p>💰 <strong>Market Cap:</strong> ₹{company_details['Market Cap']:,}</p>
                                    <p>📈 <strong>P/E Ratio:</strong> {company_details['P/E Ratio']}</p>
                                    <p>📊 <strong>EPS:</strong> {company_details['EPS']}</p>
                                    <p>💵 <strong>Dividend Yield:</strong> {company_details['Dividend Yield']}</p>
                                    <p>📅 <strong>52W High:</strong> ₹{company_details['52W High']}</p>
                                    <p>📅 <strong>52W Low:</strong> ₹{company_details['52W Low']}</p>
                                    <p>📈 <strong>1Y Change:</strong> {yearly_change:.2f}%</p>
                                    <p>📊 <strong>Price Change (Day):</strong> ₹{price_change:.2f} ({price_change_pct:.2f}%)</p>
                                    <p>⚡ <strong>Volatility (Annual):</strong> {f'{volatility:.2f}' if isinstance(volatility, float) else volatility}</p>
                                    <p>🛡️ <strong>Beta:</strong> {company_details['Beta']}</p>
                                    <p>💪 <strong>Financial Health:</strong> {health} (Mock)</p>
                                </div>
                                <div class='recommendation'>
                                    <h3>📢 Recommendation: {recommendation}</h3>
                                    <p><strong>Advice:</strong> {advice}</p>
                                </div>
                                <div class='analyst-ratings'>
                                    <h3>⭐ Analyst Ratings (Mock)</h3>
                                    <p>Buy: <strong>65%</strong> | Hold: <strong>25%</strong> | Sell: <strong>10%</strong></p>
                                </div>
                                <div class='company-info'>
                                    <h3>🏢 About {company_details['Name']}</h3>
                                    <p><strong>Sector:</strong> {company_details['Sector']}</p>
                                    <p><strong>Industry:</strong> {company_details['Industry']}</p>
                                    <p><strong>CEO:</strong> {company_details['CEO']}</p>
                                    <p><strong>Website:</strong> <a href='{company_details['Website']}' target='_blank'>{company_details['Website']}</a></p>
                                    <p><strong>Summary:</strong> {company_details['Description'][:600]}...</p>
                                </div>
                                <div class='investment-form'>
                                    <h3>💰 Calculate Investment</h3>
                                    <form method='post'>
                                        <input type='hidden' name='company_name' value='{company_name}'>
                                        <input type='number' name='amount' placeholder='Enter Amount (₹)' min='0.01' step='0.01' required>
                                        <input type='number' name='years' placeholder='Years' min='1' max='50' required>
                                        <button type='submit'>Get Suggestion</button>
                                    </form>
                                </div>
                            </div>
                            """

            elif "amount" in request.form and "years" in request.form:  # Investment calculation
                amount = request.form.get("amount")
                years = request.form.get("years")
                stock_data = get_stock_data(ticker)
                company_details = get_company_details(ticker)

                if not stock_data or not company_details:
                    stock_details = "<p class='error'>❌ Unable to fetch stock data.</p>"
                else:
                    # Store data in MongoDB
                    store_company_data(ticker, company_details, stock_data)

                    (latest_price, high_price, low_price, volume, recommendation, advice, yearly_change,
                     price_change, price_change_pct, volatility, health) = stock_data
                    stock_details = f"""
                    <div class='stock-card'>
                        <h2>{company_details['Name']} ({ticker.upper()})</h2>
                        <p class='price'><strong>Live Price:</strong> <span>₹{latest_price:.2f}</span></p>
                        <div class='stats'>
                            <p>🔼 <strong>High:</strong> ₹{high_price:.2f}</p>
                            <p>🔽 <strong>Low:</strong> ₹{low_price:.2f}</p>
                            <p>📊 <strong>Volume:</strong> {volume:,}</p>
                            <p>📉 <strong>Avg Volume (3M):</strong> {company_details['Avg Volume']:,}</p>
                            <p>💰 <strong>Market Cap:</strong> ₹{company_details['Market Cap']:,}</p>
                            <p>📈 <strong>P/E Ratio:</strong> {company_details['P/E Ratio']}</p>
                            <p>📊 <strong>EPS:</strong> {company_details['EPS']}</p>
                            <p>💵 <strong>Dividend Yield:</strong> {company_details['Dividend Yield']}</p>
                            <p>📅 <strong>52W High:</strong> ₹{company_details['52W High']}</p>
                            <p>📅 <strong>52W Low:</strong> ₹{company_details['52W Low']}</p>
                            <p>📈 <strong>1Y Change:</strong> {yearly_change:.2f}%</p>
                            <p>📊 <strong>Price Change (Day):</strong> ₹{price_change:.2f} ({price_change_pct:.2f}%)</p>
                            <p>⚡ <strong>Volatility (Annual):</strong> {f'{volatility:.2f}' if isinstance(volatility, float) else volatility}</p>
                            <p>🛡️ <strong>Beta:</strong> {company_details['Beta']}</p>
                            <p>💪 <strong>Financial Health:</strong> {health} (Mock)</p>
                        </div>
                        <div class='recommendation'>
                            <h3>📢 Recommendation: {recommendation}</h3>
                            <p><strong>Advice:</strong> {advice}</p>
                        </div>
                        <div class='analyst-ratings'>
                            <h3>⭐ Analyst Ratings (Mock)</h3>
                            <p>Buy: <strong>65%</strong> | Hold: <strong>25%</strong> | Sell: <strong>10%</strong></p>
                        </div>
                        <div class='company-info'>
                            <h3>🏢 About {company_details['Name']}</h3>
                            <p><strong>Sector:</strong> {company_details['Sector']}</p>
                            <p><strong>Industry:</strong> {company_details['Industry']}</p>
                            <p><strong>CEO:</strong> {company_details['CEO']}</p>
                            <p><strong>Website:</strong> <a href='{company_details['Website']}' target='_blank'>{company_details['Website']}</a></p>
                            <p><strong>Summary:</strong> {company_details['Description'][:600]}...</p>
                        </div>
                        {calculate_investment_suggestion(amount, years, latest_price, company_details, recommendation, volatility)}
                        <div class='investment-form'>
                            <h3>💰 Recalculate Investment</h3>
                            <form method='post'>
                                <input type='hidden' name='company_name' value='{company_name}'>
                                <input type='number' name='amount' placeholder='Enter Amount (₹)' min='0.01' step='0.01' required>
                                <input type='number' name='years' placeholder='Years' min='1' max='50' required>
                                <button type='submit'>Update Suggestion</button>
                            </form>
                        </div>
                    </div>
                    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Stock Advisor</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: url('/static/kl.webp') no-repeat center center fixed;
                background-size: cover;
                color: #fff;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }}
            .container {{
                background: rgba(0, 0, 0, 0.85);
                padding: 30px;
                border-radius: 15px;
                max-width: 800px;
                box-shadow: 0 0 20px rgba(255, 255, 255, 0.3);
                overflow-y: auto;
                max-height: 85vh;
            }}
            h1, h2, h3 {{
                color: #00e676;
                text-shadow: 1px 1px 5px rgba(0, 0, 0, 0.5);
            }}
            input, button, .toggle-button {{
                padding: 12px 20px;
                font-size: 16px;
                border-radius: 8px;
                border: none;
                margin: 10px;
                transition: all 0.3s;
            }}
            input {{
                background: rgba(255, 255, 255, 0.9);
                width: 200px;
            }}
            button, .toggle-button {{
                background: #00e676;
                color: #fff;
                font-weight: bold;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
            }}
            button:hover, .toggle-button:hover {{
                background: #00c853;
                transform: scale(1.05);
            }}
            .stock-card {{
                background: rgba(50, 50, 50, 0.9);
                padding: 25px;
                border-radius: 12px;
                margin-top: 30px;
            }}
            .price span {{
                font-size: 28px;
                color: #00e676;
                font-weight: bold;
            }}
            .stats p, .company-info p {{
                margin: 8px 0;
            }}
            .recommendation, .analyst-ratings, .investment-form {{
                margin: 20px 0;
                padding: 15px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }}
            .investment-box {{
                margin-top: 20px;
                padding: 15px;
                background: rgba(0, 255, 123, 0.1);
                border-radius: 8px;
            }}
            .error-box {{
                background: rgba(255, 82, 82, 0.2);
            }}
            .error, .danger {{
                color: #ff5252;
                font-weight: bold;
            }}
            .success {{
                color: #00e676;
                font-weight: bold;
            }}
            .warning {{
                color: #ffca28;
                font-weight: bold;
            }}
            .note {{
                font-size: 12px;
                color: #b0bec5;
            }}
            .welcome {{
                text-align: center;
            }}
            .toggle-bar {{
                text-align: center;
                margin-top: 20px;
            }}
            ::-webkit-scrollbar {{
                width: 10px;
            }}
            ::-webkit-scrollbar-thumb {{
                background: #00e676;
                border-radius: 5px;
            }}
            ::-webkit-scrollbar-track {{
                background: rgba(255, 255, 255, 0.1);
            }}
        </style>
        <script>
            window.onload = function() {{
                var companyName = "{prefilled_company}";
                if (companyName) {{
                    document.querySelector('input[name="company_name"]').value = companyName;
                }}
            }};
        </script>
    </head>
    <body>
        <div class="container">
            <form method="post">
                <h1>📊 Live Stock Advisor (India)</h1>
                <input type="text" name="company_name" placeholder="Enter Company Name" required>
                <button type="submit">Analyze Stock</button>
            </form>
            {stock_details}
            <div class="toggle-bar">
                <a href="{url_for('history')}" class="toggle-button">Show History</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/history", methods=["GET", "POST"])
def history():
    # Initialize session history if not already present
    if "history" not in session:
        session["history"] = []

    if request.method == "POST" and "clear_history" in request.form:
        session["history"] = []
        session.modified = True  # Ensure session updates
        return redirect(url_for("history"))

    history_html = "<ul>"
    if session["history"]:
        for item in session["history"]:
            history_html += f"""
            <li>
                <a href="{url_for('index', company_name=item)}" class="history-item">{item}</a>
            </li>
            """
    else:
        history_html += "<li>No history yet.</li>"
    history_html += "</ul>"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Search History - Live Stock Advisor</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background: url('/static/kl.webp') no-repeat center center fixed;
                background-size: cover;
                color: #fff;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }}
            .container {{
                background: rgba(0, 0, 0, 0.85);
                padding: 30px;
                border-radius: 15px;
                max-width: 800px;
                box-shadow: 0 0 20px rgba(255, 255, 255, 0.3);
                overflow-y: auto;
                max-height: 85vh;
            }}
            h1 {{
                color: #00e676;
                text-shadow: 1px 1px 5px rgba(0, 0, 0, 0.5);
                text-align: center;
            }}
            ul {{
                list-style: none;
                padding: 0;
            }}
            li {{
                margin: 10px 0;
            }}
            .history-item {{
                display: block;
                padding: 10px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: #fff;
                text-decoration: none;
                font-size: 16px;
                transition: all 0.3s;
            }}
            .history-item:hover {{
                background: rgba(0, 230, 118, 0.3);
                transform: scale(1.02);
            }}
            button, .back-button {{
                padding: 12px 20px;
                font-size: 16px;
                border-radius: 8px;
                border: none;
                margin: 10px;
                background: #00e676;
                color: #fff;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }}
            button:hover, .back-button:hover {{
                background: #00c853;
                transform: scale(1.05);
            }}
            .button-bar {{
                text-align: center;
                margin-top: 20px;
            }}
            ::-webkit-scrollbar {{
                width: 10px;
            }}
            ::-webkit-scrollbar-thumb {{
                background: #00e676;
                border-radius: 5px;
            }}
            ::-webkit-scrollbar-track {{
                background: rgba(255, 255, 255, 0.1);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📜 Search History</h1>
            {history_html}
            <div class="button-bar">
                <a href="{url_for('index')}" class="back-button">Back to Home</a>
                <form method="post" style="display: inline;">
                    <button type="submit" name="clear_history" value="clear">Clear History</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)