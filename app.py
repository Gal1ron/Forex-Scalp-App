import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import time
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURATION ---
FMP_API_KEY = "t9Hx8gbQBNWlMscylPQMDXhXlRRiE2qu"
LIMIT_PER_DAY = 25
COOLDOWN_SEC = 15 

# --- SESSION STATE INITIALIZATION ---
if 'daily_count' not in st.session_state:
    st.session_state.daily_count = 0
if 'last_call' not in st.session_state:
    st.session_state.last_call = datetime.min
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=["Time", "Pair", "Sentiment", "Signal"])

# --- DATA FUNCTIONS ---
def get_market_status():
    now = datetime.utcnow()
    is_weekend = (now.weekday() == 4 and now.hour >= 22) or (now.weekday() == 5) or (now.weekday() == 6 and now.hour < 22)
    return "🔴 CLOSED" if is_weekend else "🟢 OPEN"

def fetch_fmp_data(pair="EURUSD", interval="1min"):
    try:
        # 1. Price Data
        p_url = f"https://financialmodelingprep.com/api/v3/historical-chart/{interval}/{pair}?apikey={FMP_API_KEY}"
        p_res = requests.get(p_url).json()
        if not p_res or isinstance(p_res, dict): return None, None, None
        
        latest_p = p_res[0]["close"]
        velocity = abs(latest_p - p_res[1]["close"])

        # 2. Sentiment Logic (Keywords)
        n_url = f"https://financialmodelingprep.com/api/v3/forex_news?symbol={pair}&limit=5&apikey={FMP_API_KEY}"
        n_res = requests.get(n_url).json()
        
        score = 0
        keywords = {'up': 0.2, 'rise': 0.2, 'strong': 0.2, 'fall': -0.2, 'weak': -0.2, 'drop': -0.2}
        for n in n_res:
            title = n.get('title', '').lower()
            for word, val in keywords.items():
                if word in title: score += val
        
        return latest_p, velocity, round(score, 2)
    except:
        return None, None, None

def get_strength_data():
    # Comparing majors against USD to find relative strength
    majors = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    strength = {}
    for m in majors:
        url = f"https://financialmodelingprep.com/api/v3/quote/{m}?apikey={FMP_API_KEY}"
        res = requests.get(url).json()
        if res:
            strength[m] = res[0].get("changesPercentage", 0)
    return strength

# --- UI LAYOUT ---
st.set_page_config(page_title="FX Alpha Scalper", layout="wide")

# Sidebar
st.sidebar.title("🎮 Control Panel")
st.sidebar.info(f"Market: {get_market_status()}")
pair = st.sidebar.selectbox("Select Pair", ["EURUSD", "GBPUSD", "USDJPY"])
mode = st.sidebar.selectbox("Timeframe", ["1min", "5min", "15min"])
auto_on = st.sidebar.checkbox("Auto-Refresh (60s)")

if auto_on:
    st_autorefresh(interval=60000, key="auto_refresh")

# --- 1. CURRENCY STRENGTH METER ---
st.subheader("📊 Currency Relative Strength")
s_data = get_strength_data()
if s_data:
    cols = st.columns(len(s_data))
    for i, (m, val) in enumerate(s_data.items()):
        cols[i].metric(m, f"{val}%", delta=f"{val}%")



st.divider()

# --- 2. MAIN SCALPER LOGIC ---
wait_time = max(0, COOLDOWN_SEC - int((datetime.now() - st.session_state.last_call).total_seconds()))
ready = wait_time == 0 and st.session_state.daily_count < LIMIT_PER_DAY

if ready:
    if st.button("🔍 SCAN FOR DIVERGENCE") or auto_on:
        st.session_state.last_call = datetime.now()
        st.session_state.daily_count += 1
        
        price, vel, sent = fetch_fmp_data(pair, mode)
        
        if price:
            c1, c2, c3 = st.columns(3)
            c1.metric("Price", price)
            c2.metric("Velocity", round(vel, 5))
            c3.metric("News Sentiment", sent)

            # Divergence Prediction
            if sent > 0.3 and vel < 0.0001:
                st.success("🔥 BULLISH DIVERGENCE: News is positive but price is stalled. Potential Long.")
                log_sig = "LONG"
            elif sent < -0.3 and vel < 0.0001:
                st.error("🚨 BEARISH DIVERGENCE: News is negative but price is holding. Potential Short.")
                log_sig = "SHORT"
            else:
                st.warning("Neutral: Sentiment and Price are aligned.")
                log_sig = "NEUTRAL"
            
            # Update History
            new_entry = {"Time": datetime.now().strftime("%H:%M"), "Pair": pair, "Sentiment": sent, "Signal": log_sig}
            st.session_state.history = pd.concat([pd.DataFrame([new_entry]), st.session_state.history], ignore_index=True)
else:
    st.button(f"⏳ Cooldown: {wait_time}s", disabled=True)

# --- 3. HISTORY ---
st.divider()
st.subheader("📜 Session Logs")
st.dataframe(st.session_state.history, use_container_width=True)