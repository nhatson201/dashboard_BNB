from flask import Flask, render_template, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/orderbook')
def get_order_book():
    try:
        # 1. Lấy dữ liệu Sổ lệnh (Order Book) từ Binance Futures XAUUSDT
        book_url = "https://fapi.binance.com/fapi/v1/depth?symbol=XAUUSDT&limit=5"
        book_res = requests.get(book_url, timeout=5).json()
        
        # 2. Lấy dữ liệu Recent Trades từ Binance Futures
        trades_url = "https://fapi.binance.com/fapi/v1/trades?symbol=XAUUSDT&limit=50"
        trades_res = requests.get(trades_url, timeout=5).json()
        
        if 'asks' not in book_res or 'bids' not in book_res:
            return jsonify({'error': 'Không lấy được dữ liệu từ Binance'}), 500

        # Tính tổng Tape Delta thô từ các giao dịch gần đây
        recent_delta = 0
        if isinstance(trades_res, list):
            for t in trades_res:
                qty = float(t['qty'])
                # Sửa lại thành 'isBuyerMaker' theo chuẩn phản hồi của Binance Futures API
                if t.get('isBuyerMaker', False):
                    recent_delta -= qty
                else:
                    recent_delta += qty

        # Xử lý phía ASKS (Bên bán) - Sắp xếp giá giảm dần lên trên
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
            
        # Xử lý phía BIDS (Bên mua) - Sắp xếp giá giảm dần
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
        spread = round(best_ask - best_bid, 2)

        return jsonify({
            'symbol': 'XAUUSDT',
            'timestamp': 'Live Real-time',
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
    print("Khởi động Local Server tại: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)