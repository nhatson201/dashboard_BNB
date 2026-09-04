from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/orderbook')
def get_option_order_book():
    try:
        # 1. Lấy thông tin các mã Options từ Binance Options API
        info_url = "https://eapi.binance.com/eapi/v1/exchangeInfo"
        info_res = requests.get(info_url, headers=HEADERS, timeout=5).json()
        
        target_symbol = None
        option_symbols = info_res.get('optionSymbols', [])
        
        # Tìm kiếm hợp đồng thuộc tài sản XAU hoặc XAUUSDT
        for sym in option_symbols:
            underlying = sym.get('underlying', '')
            symbol_name = sym.get('symbol', '')
            if 'XAU' in underlying or 'XAU' in symbol_name:
                target_symbol = symbol_name
                break
        
        # Nếu vẫn không tìm thấy, lấy bất kỳ mã option đầu tiên có trong danh sách giao dịch
        if not target_symbol and len(option_symbols) > 0:
            for sym in option_symbols:
                if sym.get('status') == 'TRADING':
                    target_symbol = sym.get('symbol')
                    break
        
        if not target_symbol:
            return jsonify({'error': 'Không tìm thấy hợp đồng Option nào đang hoạt động trên hệ thống Binance.'}), 500

        # 2. Lấy Order Book (Depth) của mã Option cụ thể đó
        book_url = f"https://eapi.binance.com/eapi/v1/depth?symbol={target_symbol}&limit=5"
        book_res = requests.get(book_url, headers=HEADERS, timeout=5).json()
        
        # 3. Lấy Recent Trades của Option
        trades_url = f"https://eapi.binance.com/eapi/v1/trades?symbol={target_symbol}&limit=50"
        trades_res = requests.get(trades_url, headers=HEADERS, timeout=5).json()
        
        if 'asks' not in book_res or 'bids' not in book_res:
            return jsonify({'error': f'Không lấy được dữ liệu Depth cho mã {target_symbol}'}), 500

        # Tính Tape Delta từ trades của Options
        recent_delta = 0
        if isinstance(trades_res, list):
            for t in trades_res:
                qty = float(t.get('qty', 0))
                if t.get('side') == 'SELL':
                    recent_delta -= qty
                else:
                    recent_delta += qty

        # Xử lý ASKS
        asks_raw = sorted([[float(p), float(s)] for p, s in book_res['asks']], key=lambda x: x[0], reverse=True)
        asks = []
        cum_ask = 0
        total_ask_size = sum([item[1] for item in asks_raw]) if asks_raw else 1
        
        for price, size in asks_raw:
            cum_ask += size
            weight = size / total_ask_size if total_ask_size > 0 else 0
            step_delta = round(recent_delta * weight, 2)
            oi_dollar_chg = round(step_delta * price * 0.5, 2)
            oi_weighted = round(price * (1 + (weight * 0.0002)), 2)

            asks.append({
                'price': price,
                'size': size,
                'cumulative': cum_ask,
                'total_val': price * size,
                'tape_delta': step_delta,
                'oi_change_usd': oi_dollar_chg,
                'oi_weighted': oi_weighted
            })
        max_cum_ask = cum_ask if cum_ask > 0 else 1
            
        # Xử lý BIDS
        bids_raw = sorted([[float(p), float(s)] for p, s in book_res['bids']], key=lambda x: x[0], reverse=True)
        bids = []
        cum_bid = 0
        total_bid_size = sum([item[1] for item in bids_raw]) if bids_raw else 1

        for price, size in bids_raw:
            cum_bid += size
            weight = size / total_bid_size if total_bid_size > 0 else 0
            step_delta = round(recent_delta * weight, 2)
            oi_dollar_chg = round(step_delta * price * 0.5, 2)
            oi_weighted = round(price * (1 - (weight * 0.0002)), 2)

            bids.append({
                'price': price,
                'size': size,
                'cumulative': cum_bid,
                'total_val': price * size,
                'tape_delta': step_delta,
                'oi_change_usd': oi_dollar_chg,
                'oi_weighted': oi_weighted
            })
        max_cum_bid = cum_bid if cum_bid > 0 else 1
            
        best_ask = asks_raw[-1][0] if asks_raw else 0
        best_bid = bids_raw[0][0] if bids_raw else 0
        spread = round(best_ask - best_bid, 4)

        return jsonify({
            'symbol': target_symbol,
            'timestamp': 'Live Options Real-time',
            'asks': asks,
            'bids': bids,
            'max_cum_ask': max_cum_ask,
            'max_cum_bid': max_cum_bid,
            'best_ask': best_ask,
            'best_bid': best_bid,
            'spread': spread,
            'net_delta': round(recent_delta, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
