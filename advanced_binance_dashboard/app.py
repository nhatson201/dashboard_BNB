import streamlit as st
import requests
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, timezone
import time

# ===================== CẤU HÌNH =====================
FUTURES_URL = "https://fapi.binance.com"       # ✅ ĐƯỢC CHẶP NHẬN — KHÔNG BỊ CHẶN
OPTIONS_URL = "https://eapi.binance.com"        # ⚠️ Có thể bị chặn
RISK_FREE_RATE = 0.045
CONTRACT_MULTIPLIER = 1
# =====================================================

st.set_page_config(page_title="GEX Calculator - XAUUSDT", layout="wide")

# === Trang kiểm tra sức khỏe cho UptimeRobot ===
query_params = st.query_params
if "health" in query_params:
    st.write("OK")
    st.stop()

st.title("📊 Gamma Exposure (GEX) — XAUUSDT Options")
st.markdown("---")

# Cache dữ liệu 5 phút
@st.cache_data(ttl=300)
def get_data():
    results = {}

    # =====================================================
    # 💰 LẤY GIÁ TỪ FUTURES API — CHẮC CHẮN LẤY ĐƯỢC!
    # =====================================================
    S = None
    sources_tried = []

    # ✅ NGUỒN 1: Binance Futures API — ĐÃ XÁC NHẬN LẤY ĐƯỢC GIÁ!
    try:
        r = requests.get(f"{FUTURES_URL}/fapi/v1/ticker/price", params={"symbol": "XAUUSDT"}, timeout=15)
        data = r.json()
        if 'price' in data:
            val = float(data['price'])
            if 2000 < val < 5000:
                S = val
                sources_tried.append(f"✅ Binance Futures API: {S}")
    except Exception as e:
        sources_tried.append(f"❌ Binance Futures API: {str(e)[:60]}")

    # ✅ NGUỒN 2: Sổ lệnh Futures — cũng lấy được giá
    if not S:
        try:
            r = requests.get(f"{FUTURES_URL}/fapi/v1/depth", params={"symbol": "XAUUSDT", "limit": 5}, timeout=15)
            data = r.json()
            if 'bids' in data and len(data['bids']) > 0:
                val = float(data['bids'][0][0])
                if 2000 < val < 5000:
                    S = val
                    sources_tried.append(f"✅ Binance Futures Orderbook: {S}")
        except Exception as e:
            sources_tried.append(f"❌ Binance Futures Orderbook: {str(e)[:60]}")

    # ✅ NGUỒN 3: Dự phòng — CoinGecko
    if not S:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                             params={"ids": "gold", "vs_currencies": "usd"}, timeout=15)
            data = r.json()
            if 'gold' in data and 'usd' in data['gold']:
                val = float(data['gold']['usd'])
                if 2000 < val < 5000:
                    S = val
                    sources_tried.append(f"✅ CoinGecko: {S}")
        except Exception as e:
            sources_tried.append(f"❌ CoinGecko: {str(e)[:60]}")

    # === KẾT QUẢ LẤY GIÁ ===
    if not S:
        st.error("❌ KHÔNG LẤY ĐƯỢC GIÁ TỪ BẤT KỲ NGUỒN NÀO!")
        with st.expander("🔎 Chi tiết các nguồn đã thử"):
            for s in sources_tried:
                st.write(s)
        return None

    results['price'] = S
    results['sources_tried'] = sources_tried

    # =====================================================
    # 📋 LẤY DANH SÁCH HỢP ĐỒNG QUYỀN CHỌN — THỬ TRỰC TIẾP + QUA PROXY
    # =====================================================
    options = []
    try:
        # Thử trực tiếp
        r = requests.get(f"{OPTIONS_URL}/eapi/v1/exchangeInfo", timeout=20)
        data = r.json()
        for sym in data.get('optionSymbols', []):
            if sym.get('underlying') == "XAUUSDT" and sym.get('status') == 'TRADING':
                options.append({
                    'symbol': sym['symbol'],
                    'strike': float(sym['strikePrice']),
                    'expiry': sym['expiryDate'] / 1000,
                    'type': sym['optionSide'],
                    'multiplier': float(sym['contractMultiplier'])
                })
        results['options_count'] = len(options)
    except Exception as e1:
        st.warning(f"⚠️ API Options trực tiếp bị chặn, thử qua Proxy... ({str(e1)[:50]})")
        try:
            # Dùng Proxy nếu bị chặn
            proxy = "https://api.allorigins.win/raw?url="
            r = requests.get(f"{proxy}{OPTIONS_URL}/eapi/v1/exchangeInfo", timeout=30)
            data = r.json()
            for sym in data.get('optionSymbols', []):
                if sym.get('underlying') == "XAUUSDT" and sym.get('status') == 'TRADING':
                    options.append({
                        'symbol': sym['symbol'],
                        'strike': float(sym['strikePrice']),
                        'expiry': sym['expiryDate'] / 1000,
                        'type': sym['optionSide'],
                        'multiplier': float(sym['contractMultiplier'])
                    })
            results['options_count'] = len(options)
        except Exception as e2:
            st.error(f"❌ Không lấy được danh sách hợp đồng: {e2}")
            st.info("💡 Giá đã lấy được từ Futures, nhưng dữ liệu quyền chọn bị chặn")
            return results  # Trả về giá dù không có dữ liệu quyền chọn

    if len(options) == 0:
        st.warning("⚠️ Không tìm thấy hợp đồng quyền chọn nào đang giao dịch!")
        return results

    # =====================================================
    # 📐 HÀM TÍNH GAMMA (Black-Scholes)
    # =====================================================
    def gamma(S, K, T, r, sigma):
        if T <= 0 or sigma <= 0:
            return 0.0
        try:
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            return norm.pdf(d1) / (S * sigma * np.sqrt(T))
        except:
            return 0.0

    # =====================================================
    # 📊 TÍNH GEX TỪNG HỢP ĐỒNG — THỬ TRỰC TIẾP HOẶC QUA PROXY
    # =====================================================
    current_ts = time.time()
    gex_list = []
    total_gex = 0.0
    use_proxy = False
    proxy = "https://api.allorigins.win/raw?url="

    for opt in options:
        T = max(0, (opt['expiry'] - current_ts) / (365 * 24 * 3600))
        if T <= 0:
            continue

        # Lấy MarkPrice + IV
        try:
            if use_proxy:
                url = f"{proxy}{OPTIONS_URL}/eapi/v1/markPrice?symbol={opt['symbol']}"
            else:
                url = f"{OPTIONS_URL}/eapi/v1/markPrice?symbol={opt['symbol']}"
            mp = requests.get(url, timeout=15).json()
            iv = float(mp.get('impliedVolatility', 0)) / 100.0
            if iv <= 0:
                continue
        except:
            if not use_proxy:
                # Lần đầu lỗi → bật proxy cho các lần sau
                use_proxy = True
            try:
                url = f"{proxy}{OPTIONS_URL}/eapi/v1/markPrice?symbol={opt['symbol']}"
                mp = requests.get(url, timeout=20).json()
                iv = float(mp.get('impliedVolatility', 0)) / 100.0
                if iv <= 0:
                    continue
            except:
                continue

        # Lấy OI
        try:
            if use_proxy:
                url = f"{proxy}{OPTIONS_URL}/eapi/v1/ticker?symbol={opt['symbol']}"
            else:
                url = f"{OPTIONS_URL}/eapi/v1/ticker?symbol={opt['symbol']}"
            ticker = requests.get(url, timeout=15).json()
            oi_value = float(ticker.get('openInterest', 0))
            mk_price = float(ticker.get('markPrice', 0))
            oi_contracts = oi_value / mk_price if mk_price > 0 else 0
        except:
            continue

        if oi_contracts <= 0:
            continue

        # Tính GEX
        g = gamma(S, opt['strike'], T, RISK_FREE_RATE, iv)
        mult = opt.get('multiplier', CONTRACT_MULTIPLIER)
        if opt['type'] == 'CALL':
            gex_val = g * oi_contracts * mult * (S ** 2) * 0.01
        else:
            gex_val = -g * oi_contracts * mult * (S ** 2) * 0.01

        total_gex += gex_val
        gex_list.append({
            'Strike': opt['strike'],
            'Type': opt['type'],
            'Expiry_Days': round(T * 365, 1),
            'IV(%)': round(iv * 100, 2),
            'OI_Contracts': round(oi_contracts, 1),
            'Gamma': round(g, 8),
            'GEX': round(gex_val, 2)
        })

    if not gex_list:
        st.warning("⚠️ Không tính được GEX do dữ liệu quyền chọn bị chặn!")
        return results

    # =====================================================
    # 📈 TÍNH TỔNG HỢP & GAMMA FLIP
    # =====================================================
    df = pd.DataFrame(gex_list)
    df_sorted = df.sort_values('Strike')
    df_sorted['Cumulative_GEX'] = df_sorted['GEX'].cumsum()

    gamma_flip = None
    for i in range(1, len(df_sorted)):
        prev = df_sorted.iloc[i-1]['Cumulative_GEX']
        curr = df_sorted.iloc[i]['Cumulative_GEX']
        if (prev < 0 and curr >= 0) or (prev > 0 and curr <= 0):
            gamma_flip = (df_sorted.iloc[i-1]['Strike'] + df_sorted.iloc[i]['Strike']) / 2
            break

    call_wall = df[df['Type'] == 'CALL'].nlargest(1, 'GEX').iloc[0] if len(df[df['Type'] == 'CALL']) else None
    put_wall = df[df['Type'] == 'PUT'].nsmallest(1, 'GEX').iloc[0] if len(df[df['Type'] == 'PUT']) else None

    results['total_gex'] = total_gex
    results['gamma_flip'] = gamma_flip
    results['call_wall'] = call_wall
    results['put_wall'] = put_wall
    results['df'] = df
    results['update_time'] = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    return results

# =====================================================
# 🖥️ HIỂN THỊ GIAO DIỆN
# =====================================================
data = get_data()

if data and 'price' in data:
    st.subheader(f"🕒 Cập nhật: {data.get('update_time', '---')}")
    
    if 'sources_tried' in data:
        with st.expander("🔎 Xem các nguồn giá đã thử"):
            for s in data['sources_tried']:
                st.write(s)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("💰 Giá XAUUSDT", f"{data['price']:.2f}")

    if 'total_gex' in data:
        with col2:
            gex_status = "🟢 GEX DƯƠNG" if data['total_gex'] > 0 else "🔴 GEX ÂM"
            st.metric("📈 Tổng GEX", f"{data['total_gex']:,.0f}",
                      help=f"{gex_status} — {'Bình ổn giá' if data['total_gex'] > 0 else 'Khuếch đại biến động'}")
    else:
        with col2:
            st.metric("📈 Tổng GEX", "Đang lấy dữ liệu...")

    if 'gamma_flip' in data and data['gamma_flip']:
        with col3:
            pos = "TRÊN → GEX+" if data['price'] > data['gamma_flip'] else "DƯỚI → GEX-"
            st.metric("🔄 Gamma Flip", f"{data['gamma_flip']:.2f}", delta=pos)
    else:
        with col3:
            st.metric("🔄 Gamma Flip", "Đang tính...")

    if 'call_wall' in data or 'put_wall' in data:
        c1, c2 = st.columns(2)
        with c1:
            if data.get('call_wall') is not None:
                st.info(f"🧱 **Call Wall (Kháng cự):** {data['call_wall']['Strike']:.2f} | GEX: {data['call_wall']['GEX']:,.0f}")
        with c2:
            if data.get('put_wall') is not None:
                st.info(f"🧱 **Put Wall (Hỗ trợ):** {data['put_wall']['Strike']:.2f} | GEX: {data['put_wall']['GEX']:,.0f}")

    st.markdown("---")

    if 'df' in data:
        st.subheader("📊 Chi tiết GEX theo mức giá (Top 15)")
        df_show = data['df'].sort_values('GEX', key=abs, ascending=False).head(15).reset_index(drop=True)
        st.dataframe(df_show, use_container_width=True)
    else:
        st.info("⏳ Dữ liệu quyền chọn đang được lấy qua Proxy... Vui lòng chờ hoặc thử lại sau.")

    st.markdown("---")
    st.caption(f"Nguồn: Binance Futures (Giá) + Binance Options (Dữ liệu) | Tự động cập nhật mỗi 5 phút | Hợp đồng: {data.get('options_count', 0)}")

if st.button("🔄 Làm mới dữ liệu"):
    st.cache_data.clear()
    st.rerun()
