import streamlit as st
import requests
import pandas as pd
import time

API = "http://localhost:8080"

st.set_page_config(layout="wide")
st.title("🚀 AI FUND DASHBOARD V3")

# ===== helpers =====
def get(path):
    try:
        return requests.get(API + path).json()
    except:
        return {}

def post(cmd):
    try:
        return requests.post(API + "/api/command", json={"command": cmd}).json()
    except:
        return {}

# ===== CONTROL PANEL =====
st.sidebar.title("🎮 Control")

if st.sidebar.button("▶️ Start Engine"):
    post('/start_v7_engine {"markets":["A","B"],"capital":100}')

if st.sidebar.button("⛔ Stop Engine"):
    post('/stop_v7_engine')

capital = st.sidebar.slider("Capital", 10, 1000, 100)

# ===== STATE =====
state = post("/get_state")
if "output" in state:
    try:
        state = eval(state["output"])
    except:
        state = {}

positions = state.get("positions", {})
trades = state.get("trades", [])
pnl = state.get("pnl", 0)

df_trades = pd.DataFrame(trades) if trades else pd.DataFrame()

# ===== TOP METRICS =====
c1, c2, c3, c4 = st.columns(4)

c1.metric("PnL", round(pnl, 4))
c2.metric("Trades", len(trades))
c3.metric("Positions", len(positions))

winrate = 0
if not df_trades.empty:
    winrate = (df_trades["pnl_delta"] > 0).mean()

c4.metric("Winrate", round(winrate, 2))

st.divider()

# ===== EQUITY CURVE =====
st.subheader("📈 Equity Curve")

if not df_trades.empty:
    df_trades["equity"] = df_trades["pnl_delta"].cumsum()
    st.line_chart(df_trades["equity"])

# ===== DRAWDOWN =====
st.subheader("📉 Drawdown")

if not df_trades.empty:
    eq = df_trades["equity"]
    peak = eq.cummax()
    dd = peak - eq
    st.line_chart(dd)

# ===== STRATEGY ATTRIBUTION =====
st.subheader("🧠 Strategy Attribution")

if not df_trades.empty:
    strat = df_trades.groupby("strategy_id")["pnl_delta"].sum()
    st.bar_chart(strat)

# ===== ASSET PNL =====
st.subheader("💰 Asset PnL")

if not df_trades.empty:
    asset = df_trades.groupby("asset_id")["pnl_delta"].sum()
    st.bar_chart(asset)

# ===== EXECUTION STATS =====
st.subheader("⚡ Execution Stats")

if not df_trades.empty:
    avg_size = df_trades["size"].mean()
    total_volume = df_trades["size"].sum()

    st.write({
        "avg_trade_size": avg_size,
        "total_volume": total_volume
    })

# ===== WALLET LEADERS =====
st.subheader("🐋 Smart Money")

leaders = post("/wa_get_leaders")

if "output" in leaders:
    try:
        df = pd.DataFrame(eval(leaders["output"]))
        st.dataframe(df)
    except:
        st.text(leaders["output"])

# ===== MANUAL TRADE =====
st.subheader("🎯 Manual Trade")

col1, col2, col3 = st.columns(3)

asset = col1.text_input("Asset", "A")
side = col2.selectbox("Side", ["buy", "sell"])
size = col3.number_input("Size", value=1.0)

if st.button("EXECUTE"):
    post(f'/pm_limit {{"asset_id":"{asset}","side":"{side}","price":0.5,"size":{size},"ioc":true}}')

# ===== AUTO REFRESH =====
time.sleep(2)
st.rerun()
