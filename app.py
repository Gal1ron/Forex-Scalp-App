import streamlit as st
import requests
import pandas as pd
import datetime as dt  # This clears up the confusion
import time
from streamlit_autorefresh import st_autorefresh

# --- CONFIG & SECRETS ---
# This line works for both local (secrets.toml) and Streamlit Cloud
try:
    FMP_API_KEY = st.secrets["FMP_API_KEY"]
except:
    FMP_API_KEY = "t9Hx8gbQBNWlMscylPQMDXhXlRRiE2qu"

LIMIT_PER_DAY = 250  # FMP Free Tier is actually ~250/day
COOLDOWN_SEC = 15 

# --- SESSION STATE ---
if 'daily_count' not in st.session_state: st.session_state.daily_count = 0
if 'last_call' not in st.session_state: 
    st.session_state.last_call = dt.datetime.min
if 'api_status' not in st.session_state: st.session_state.api_status = "Unknown"
if 'history' not in st.session_state: 
    st.session_state.history = pd.DataFrame(columns=["Time", "Pair", "Sentiment", "Signal"])

# --- MARKET & API TOOLS ---
def get_market_status():
    # Use dt.datetime and dt.timezone
    now = dt.datetime.now(dt.timezone.utc)
    is_weekend = (now.weekday() == 4 and now.hour >= 22) or \
                 (now.weekday() == 5) or \
                 (now.weekday() == 6 and now.hour < 22)
    return "🔴 CLOSED" if is_weekend else "🟢 OPEN"

def check_api_health():
    url = f"https://financialmodelingprep.com/api/v3/quote/EURUSD?apikey={FMP_API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200 and isinstance(res.json(), list):
            return "🟢 Healthy"
        elif res.status_code == 403:
            return "🔴 Invalid Key"
        else:
            return "🟡 Limited/Error"
    except:
        return "🔴 Offline"

# --- DATA FETCH ---
def fetch_fmp_data(pair="EURUSD", interval="1min"):
    try:
        p_url = f"https://financialmodelingprep.com/api/v3/historical-chart/{interval}/{pair}?apikey={FMP_API_KEY}"
        p_res = requests.get(p_url).json()
        
        # KEYERROR PROTECTION
        if not isinstance(p_res, list) or len(p_res) < 2:
            return None, None, None
            
        latest_p = p_res[0]["close"]
        velocity = abs(latest_p - p_res[1]["close"])

        n_url = f"https://financialmodelingprep.com/api/v3/forex_news?symbol={pair}&limit=5&apikey={FMP_API_KEY}"
        n_res = requests.get(n_url).json()
        
        score = 0
        if isinstance(n_res, list):
            keywords = {'up': 0.2, 'rise': 0.2, 'strong': 0.2, 'fall': -0.2, 'weak': -0.2, 'drop': -0.2}
            for n in n_res:
                title = n.get('title', '').lower()
                for word, val in keywords.items():
                    if word in title: score += val
        
        return latest_p, velocity, round(score, 2)
    except:
        return None, None, None

# --- SIDEBAR STATUS DASHBOARD ---
with st.sidebar:
    st.title("🛠 System Monitor")
    st.metric("Market Status", get_market_status())
    
    # API Health Section
    with st.expander("API Status Details", expanded=True):
        if st.button("Check Connection"):
            st.session_state.api_status = check_api_health()
        st.write(f"Connection: **{st.session_state.api_status}**")
        
        usage_pct = st.session_state.daily_count / LIMIT_PER_DAY
        st.write(f"Daily Usage: {st.session_state.daily_count} / {LIMIT_PER_DAY}")
        st.progress(min(usage_pct, 1.0))
    
    st.divider()
    pair = st.selectbox("Select Pair", ["EURUSD", "GBPUSD", "USDJPY"])
    mode = st.selectbox("Timeframe", ["1min", "5min", "15min"])
    auto_on = st.checkbox("Auto-Refresh (60s)")

# --- MAIN APP LOGIC ---
st.title("⚡ FX War Room")

if auto_on:
    st_autorefresh(interval=60000, key="auto_refresh")

# Execution button
wait_time = max(0, COOLDOWN_SEC - int((dt.datetime.now() - st.session_state.last_call).total_seconds()))
ready = wait_time == 0 and st.session_state.daily_count < LIMIT_PER_DAY

if ready:
    if st.button("🔍 SCAN FOR DIVERGENCE") or auto_on:
        st.session_state.last_call = dt.datetime.now()
        st.session_state.daily_count += 2 # Costs 2 calls (Price + News)
        
        price, vel, sent = fetch_fmp_data(pair, mode)
        
        if price:
            c1, c2, c3 = st.columns(3)
            c1.metric("Live Price", price)
            c2.metric("Velocity", f"{vel:.5f}")
            c3.metric("Sentiment", sent)
            
            # Simple Prediction Logic
            if sent > 0.4 and vel < 0.0001:
                st.success("🎯 SIGNAL: BULLISH DIVERGENCE (Price Lagging News)")
                log_sig = "LONG"
            elif sent < -0.4 and vel < 0.0001:
                st.error("🚨 SIGNAL: BEARISH DIVERGENCE (Price Lagging News)")
                log_sig = "SHORT"
            else:
                st.info("Market Equilibrium")
                log_sig = "WAIT"

            # Log to history
            new_row = {"Time": datetime.now().strftime("%H:%M:%S"), "Pair": pair, "Sentiment": sent, "Signal": log_sig}
            st.session_state.history = pd.concat([pd.DataFrame([new_row]), st.session_state.history], ignore_index=True)
else:
    st.button(f"⏳ Cooldown: {wait_time}s", disabled=True)

st.divider()
st.subheader("📝 Live Trade Log")
st.dataframe(st.session_state.history, use_container_width=True)