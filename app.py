from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

# API Proxy để Backend gọi sang Binance, tránh lỗi CORS trên trình duyệt
@app.route('/api/data')
def get_binance_data():
    try:
        book_res = requests.get('https://fapi.binance.com/fapi/v1/depth?symbol=XAUUSDT&limit=50', timeout=5)
        trades_res = requests.get('https://fapi.binance.com/fapi/v1/trades?symbol=XAUUSDT&limit=50', timeout=5)
        
        return jsonify({
            "depth": book_res.json(),
            "trades": trades_res.json()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
