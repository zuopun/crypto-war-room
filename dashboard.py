import streamlit as st
import streamlit.components.v1 as components
import ccxt.async_support as ccxt_async
import asyncio
import pandas as pd
import aiohttp
from datetime import datetime
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator

# ================= 設定區 =================
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except:
    TELEGRAM_TOKEN = "8368203057:AAECjZIhHJKcid-itLTMhVbfpV2ko6vU4HU" 
    TELEGRAM_CHAT_ID = "1510241198"
# ========================================

st.set_page_config(page_title="幣安戰情室 V27 (Debug)", page_icon="🔧", layout="wide")

# CSS 美化
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-family: 'Roboto Mono', monospace; font-size: 24px; }
    .analysis-panel { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
    .signal-header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
    .signal-title { font-size: 22px; font-weight: 700; display: flex; align-items: center; }
    .signal-reason { color: #8b949e; font-size: 15px; font-style: italic; }
    .data-grid-wide { display: grid; grid-template-columns: repeat(6, 1fr); gap: 15px; }
    @media (max-width: 1000px) { .data-grid-wide { grid-template-columns: repeat(3, 1fr); } }
    .data-item { background-color: #0d1117; padding: 12px; border-radius: 4px; text-align: center; border: 1px solid #30363d; }
    .data-label { font-size: 12px; color: #8b949e; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px; }
    .data-value { font-size: 18px; font-weight: bold; font-family: 'Roboto Mono'; color: #e6edf3; }
    .text-green { color: #3fb950 !important; }
    .text-red { color: #f85149 !important; }
    .stDataFrame td { font-family: 'Roboto Mono', monospace; font-size: 13px; }
    section[data-testid="stSidebar"] { background-color: #010409; }
</style>
""", unsafe_allow_html=True)

# --- 參數 ---
SCAN_LIMIT = 30
SCAN_TIMEFRAME = '15m' 

if 'selected_coin' not in st.session_state: st.session_state.selected_coin = 'BTC/USDT'

# --- Telegram ---
async def send_telegram(text):
    if not TELEGRAM_TOKEN or "你的_TOKEN" in TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    async with aiohttp.ClientSession() as session:
        try: await session.post(url, json=payload)
        except: pass

# --- 核心邏輯 ---
def calculate_signal(row, open_price, last_price, bb_upper, bb_lower, rsi, atr, is_aggressive):
    signal = "⚪ 觀望 (Neutral)"
    entry_price = 0.0
    tp_price = 0.0
    sl_price = 0.0
    reason = "Scanning..."
    direction = "NONE"
    
    is_red_candle = last_price < open_price
    is_green_candle = last_price > open_price

    rsi_overbought = 65 if is_aggressive else 70
    rsi_oversold = 35 if is_aggressive else 30
    atr_sl_mult = 2.0 if is_aggressive else 1.5
    atr_tp_mult = 3.0
    
    sl_dist = atr * atr_sl_mult
    tp_dist = atr * atr_tp_mult

    # 空
    if last_price > bb_upper:
        if rsi > 85:
            signal = "⚠️ 風險過高 (Overbought)"
            reason = "RSI > 85 (過熱保護)"
            direction = "WAIT"
        elif is_aggressive and rsi > rsi_overbought:
            signal = "⚡ 激進做空 (Short)"
            direction = "SHORT"
            entry_price = last_price
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
            reason = f"激進模式: 觸頂 + RSI>{rsi_overbought}"
        elif not is_aggressive and rsi > rsi_overbought and is_red_candle:
            signal = "🔴 趨勢反轉空 (Short)"
            direction = "SHORT"
            entry_price = last_price 
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
            reason = "觸頂 + 紅K確認"
        elif not is_aggressive and rsi > rsi_overbought:
            reason = "超買區整理中 (等待紅K)"
            direction = "WATCH"

    # 多
    elif last_price < bb_lower:
        if rsi < 15:
            signal = "⚠️ 風險過高 (Oversold)"
            reason = "RSI < 15 (接刀保護)"
            direction = "WAIT"
        elif is_aggressive and rsi < rsi_oversold:
            signal = "⚡ 激進做多 (Long)"
            direction = "LONG"
            entry_price = last_price
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
            reason = f"激進模式: 觸底 + RSI<{rsi_oversold}"
        elif not is_aggressive and rsi < rsi_oversold and is_green_candle:
            signal = "🔵 趨勢反轉多 (Long)"
            direction = "LONG"
            entry_price = last_price
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
            reason = "觸底 + 綠K確認"
        elif not is_aggressive and rsi < rsi_oversold:
            reason = "超賣區整理中 (等待綠K)"
            direction = "WATCH"

    # 爆量
    elif row['vol_ratio'] > (2.0 if is_aggressive else 3.0):
        sl_dist_vol = atr * 2.0
        tp_dist_vol = atr * 4.0
        check_green = True if is_aggressive else is_green_candle
        check_red = True if is_aggressive else is_red_candle
        
        if row['change'] > 2.0 and check_green:
            signal = "🟢 爆量順勢多 (Vol Long)"
            direction = "LONG"
            entry_price = last_price
            sl_price = entry_price - sl_dist_vol
            tp_price = entry_price + tp_dist_vol
            reason = "成交量異常放大 (多方)"
        elif row['change'] < -2.0 and check_red:
            signal = "🟠 爆量順勢空 (Vol Short)"
            direction = "SHORT"
            entry_price = last_price
            sl_price = entry_price + sl_dist_vol
            tp_price = entry_price - tp_dist_vol
            reason = "成交量異常放大 (空方)"
        
    return signal, entry_price, tp_price, sl_price, reason, direction

# --- 數據處理 (V27 除錯版) ---
async def get_scan_data(vol_threshold, is_aggressive):
    exchange = ccxt_async.binanceusdm()
    data_store = []
    try:
        # 測試連線
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
        
        # 抓取 USDT 對
        usdt_pairs = [k for k, v in tickers.items() if '/USDT:USDT' in k]
        if not usdt_pairs:
            return "錯誤：找不到 USDT 合約交易對 (可能是 API 連線問題)"
            
        sorted_pairs = sorted(usdt_pairs, key=lambda x: tickers[x]['quoteVolume'], reverse=True)[:SCAN_LIMIT]
        
        tasks = []
        for symbol in sorted_pairs:
            tasks.append(process_symbol(exchange, symbol, tickers[symbol], vol_threshold, is_aggressive))
        
        results = await asyncio.gather(*tasks)
        data_store = [r for r in results if r is not None]
        
        if not data_store:
            return "警告：有連線但抓不到任何 K 線數據 (可能是 Rate Limit)"

    except Exception as e:
        # === 關鍵修改：回傳錯誤訊息 ===
        return f"API 連線錯誤: {str(e)}"
    finally:
        await exchange.close()
    
    data_store.sort(key=lambda x: x['quote_vol'], reverse=True)
    return data_store

async def process_symbol(exchange, symbol, ticker_data, vol_threshold, is_aggressive):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, SCAN_TIMEFRAME, limit=30)
        if not ohlcv: return None
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        bb = BollingerBands(close=df['close'], window=20, window_dev=2)
        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
        atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
        
        vol_ma = df['vol'].rolling(20).mean().iloc[-1]
        vol_cur = df['vol'].iloc[-1]
        vol_ratio = vol_cur / vol_ma if vol_ma > 0 else 1.0
        change = float(ticker_data['percentage'])
        price = float(ticker_data['last'])
        
        sig_text, entry, tp, sl, reason, direction = calculate_signal(
            {'vol_ratio': vol_ratio, 'change': change}, 
            df['open'].iloc[-1], price, upper, lower, rsi, atr, is_aggressive
        )
        
        score = 50
        if vol_ratio > vol_threshold: score += 20
        if abs(change) > 5.0: score += 15
        if direction in ["LONG", "SHORT"]: score += 20 

        status = "正常"
        if vol_ratio > vol_threshold: status = "🔥 爆量"
        elif abs(change) > 8: status = "⚠️ 劇烈"

        return {
            "symbol": symbol.split(':')[0],
            "full_symbol": symbol,
            "price": price,
            "change": change,
            "vol_ratio": vol_ratio,
            "rsi": rsi,
            "atr": atr,
            "score": min(score, 100),
            "signal": sig_text,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "reason": reason,
            "status": status,
            "direction": direction,
            "quote_vol": ticker_data['quoteVolume']
        }
    except: return None

async def get_coin_detail(symbol):
    exchange = ccxt_async.binanceusdm()
    result = {'oi_val': 0, 'funding': 0}
    try:
        t_funding = exchange.fetch_funding_rate(symbol)
        t_oi = exchange.fetch_open_interest(symbol)
        data = await asyncio.gather(t_funding, t_oi, return_exceptions=True)
        if not isinstance(data[0], Exception): result['funding'] = data[0].get('fundingRate', 0) * 100
        if not isinstance(data[1], Exception): result['oi_val'] = float(data[1].get('openInterestValue', 0))
    except: pass
    finally: await exchange.close()
    return result

def render_tradingview_widget(symbol):
    tv_symbol = f"BINANCE:{symbol.replace('/', '').replace(':USDT', '')}.P"
    html_code = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_widget"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%", "height": 550, "symbol": "{tv_symbol}", "interval": "15",
        "timezone": "Asia/Taipei", "theme": "dark", "style": "1", "locale": "zh_TW",
        "enable_publishing": false, "withdateranges": true, "hide_side_toolbar": false,
        "allow_symbol_change": true, "details": true, "hotlist": true, "calendar": false,
        "studies": ["RSI@tv-basicstudies", "BB@tv-basicstudies"],
        "container_id": "tradingview_widget"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=560)

# --- 主程式 ---
async def main_loop():
    placeholder = st.empty()
    signal_history = {} 
    refresh_count = 0

    with st.sidebar:
        st.subheader("參數設定")
        is_aggressive = st.checkbox("激進模式 (Aggressive)", value=False)
        st.divider()
        vol_threshold = st.slider("爆量倍數 (Volume)", 1.5, 5.0, 2.5, 0.1)
        cooldown_minutes = st.slider("訊號冷卻 (分鐘)", 5, 120, 30 if is_aggressive else 60, 5)

    mode_text = "激進 (Aggressive)" if is_aggressive else "穩健 (Conservative)"
    await send_telegram(f"🚀 <b>系統啟動</b> | 模式: {mode_text}")

    while True:
        refresh_count += 1
        data = await get_scan_data(vol_threshold, is_aggressive)
        current_scan_list = []
        
        with placeholder.container():
            # === V27 除錯邏輯 ===
            if isinstance(data, str) and "錯誤" in data:
                st.error(f"❌ {data}")
                st.info("提示: 請檢查 GitHub 的 requirements.txt 是否包含 ccxt, aiohttp")
            elif not data:
                st.warning("⚠️ 數據連線中... (若超過 1 分鐘請檢查網路狀態)")
            else:
                current_scan_list = [d['symbol'] for d in data] if data else []
                # 1. 頂部重點指標
                st.subheader("🔥 市場熱度概覽 (Top 5 Volume)")
                top_5 = data[:5]
                cols = st.columns(5)
                for i, coin in enumerate(top_5):
                    cols[i].metric(coin['symbol'], f"${coin['price']:.4f}", f"{coin['change']:.2f}%")
                
                st.divider()

                # 2. 深度分析區
                st.subheader("📊 深度技術分析 (Deep Technical Analysis)")
                try: idx = current_scan_list.index(st.session_state.selected_coin)
                except: idx = 0
                sel_coin = st.selectbox("選擇分析標的", current_scan_list, index=idx, key=f"sel_{refresh_count}")
                st.session_state.selected_coin = sel_coin
                
                target = next((item for item in data if item["symbol"] == sel_coin), None)
                if target:
                    detail = await get_coin_detail(target['full_symbol'])
                    
                    status_color = "#8b949e"
                    if "空" in target['signal']: status_color = "#f85149"
                    elif "多" in target['signal']: status_color = "#3fb950"
                    elif "WAIT" in target['direction']: status_color = "#e3b341"
                    
                    def fmt(v): return f"${v:.5f}" if v > 0 else "-"
                    
                    html_content = f"""<div class="analysis-panel" style="border-left: 4px solid {status_color};">
<div class="signal-header-row">
<div class="signal-title" style="color: {status_color};">{target['signal']}</div>
<div class="signal-reason">💡 {target['reason']}</div>
</div>
<div class="data-grid-wide">
<div class="data-item"><div class="data-label">進場 (Entry)</div><div class="data-value">{fmt(target['entry'])}</div></div>
<div class="data-item"><div class="data-label">止盈 (TP)</div><div class="data-value text-green">{fmt(target['tp'])}</div></div>
<div class="data-item"><div class="data-label">止損 (SL)</div><div class="data-value text-red">{fmt(target['sl'])}</div></div>
<div class="data-item"><div class="data-label">ATR 波幅</div><div class="data-value" style="font-size:16px;">{target['atr']:.4f}</div></div>
<div class="data-item"><div class="data-label">RSI 強度</div><div class="data-value" style="font-size:16px;">{target['rsi']:.1f}</div></div>
<div class="data-item"><div class="data-label">資金費率</div><div class="data-value" style="font-size:16px;">{detail['funding']:.4f}%</div></div>
</div>
</div>"""
                    st.markdown(html_content, unsafe_allow_html=True)
                    render_tradingview_widget(sel_coin)
                
                st.write("")
                st.divider()

                # 3. 完整表格
                st.subheader("📡 市場即時監控 (Real-time Monitor)")
                df_raw = pd.DataFrame(data)
                df_show = df_raw[['symbol', 'price', 'change', 'vol_ratio', 'signal', 'score']].copy()
                
                def color_rows(row):
                    color = '#3fb950' if row['change'] > 0 else '#f85149'
                    return [f'color:{color}' if c in ['price', 'change'] else '' for c in row.index]

                st.dataframe(
                    df_show.style.apply(color_rows, axis=1).format({'price': '${:.4f}', 'change': '{:+.2f}%', 'vol_ratio': '{:.1f}x'}),
                    use_container_width=True, height=600, hide_index=True
                )

                # 通知邏輯
                for coin in data:
                    symbol = coin['symbol']
                    current_dir = coin['direction']
                    if current_dir not in ["LONG", "SHORT"]: continue
                    
                    now = datetime.now()
                    should_notify = False
                    if symbol in signal_history:
                        last = signal_history[symbol]
                        if current_dir != last['direction']: should_notify = True
                        elif (now - last['time']).seconds > (cooldown_minutes * 60): should_notify = True
                    else: should_notify = True

                    if should_notify:
                        n_detail = await get_coin_detail(coin['full_symbol'])
                        funding = n_detail.get('funding', 0)
                        oi = n_detail.get('oi_val', 0) / 1000000
                        
                        icon = "🟢" if current_dir == "LONG" else "🔴"
                        change_sign = "+" if coin['change'] > 0 else ""
                        fund_alert = "⚠️" if abs(funding) > 0.03 else "✅"
                        
                        msg = f"""
<b>{icon} 訊號觸發 | #{coin['symbol']}</b>
-------------------------
<b>🤖 策略:</b> {coin['signal']}
<b>🎯 進場:</b> <code>{coin['entry']:.5f}</code>
<b>💰 止盈:</b> <code>{coin['tp']:.5f}</code> | <b>🛑 止損:</b> <code>{coin['sl']:.5f}</code>
-------------------------
<b>📊 市場數據矩陣</b>
• 15m 漲跌: {change_sign}{coin['change']:.2f}%
• 資金費率: {funding:.4f}% {fund_alert}
• 持倉量(OI): ${oi:.1f}M
-------------------------
💡 <i>{coin['reason']}</i>
                        """
                        await send_telegram(msg)
                        signal_history[symbol] = {'direction': current_dir, 'time': now}

        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main_loop())
