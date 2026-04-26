import streamlit as st
import requests
import pandas as pd
import time

API = "http://localhost:8080"

st.set_page_config(layout="wide")

st.title("💰 AI Fund Dashboard v2")

# ===== helper =====
def get(path):
    try:
        return requests.get(API + path).json()
    except:
        return {}

def post(path, data):
    try:
        return requests.post(API + path, json=data).json()
    except:
        return {}

# ===== controls =====
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("▶️ Start Engine"):
        post("/api/command", {"command": "/start_v7_engine {\"markets\":[\"A\",\"B\"],\"capital\":100}"})

with col2:
    if st.button("⛔ Stop Engine"):
        post("/api/command", {"command": "/stop_v7_engine"})

with col3:
    if st.button("🔄 Refresh"):
        st.rerun()

st.divider()

# ===== STATE =====
state = get("/api/command?cmd=get_state")
if not state:
    state = {}

positions = state.get("positions", {})
trades = state.get("trades", [])
pnl = state.get("pnl", 0)

# ===== TOP METRICS =====
c1, c2, c3 = st.columns(3)

c1.metric("PnL", round(pnl, 4))
c2.metric("Positions", len(positions))
c3.metric("Trades", len(trades))

st.divider()

# ===== POSITIONS =====
st.subheader("📊 Positions")

if positions:
    df_pos = pd.DataFrame([
        {"asset": k, "size": v["size"], "avg": v["avg"]}
        for k, v in positions.items()
    ])
    st.dataframe(df_pos, use_container_width=True)
else:
    st.info("No positions")

# ===== TRADES =====
st.subheader("📜 Recent Trades")

if trades:
    df_trades = pd.DataFrame(trades)
    st.dataframe(df_trades.tail(20), use_container_width=True)
else:
    st.info("No trades")

# ===== STRATEGY =====
st.subheader("🧠 Strategy Ranking")

ranking = post("/api/command", {"command": "/strategy_get_rankings"})

if isinstance(ranking, dict) and "output" in ranking:
    try:
        data = eval(ranking["output"])
        df = pd.DataFrame([
            {
                "strategy": k,
                "pnl": v["pnl"],
                "winrate": v["winrate"],
                "dd": v["drawdown"]
            }
            for k, v in data
        ])
        st.dataframe(df, use_container_width=True)
    except:
        st.text(ranking["output"])

# ===== ALLOCATION =====
st.subheader("💰 Capital Allocation")

alloc = post("/api/command", {"command": "/allocator_get_allocation_map"})

if isinstance(alloc, dict) and "output" in alloc:
    try:
        data = eval(alloc["output"])
        df = pd.DataFrame([
            {"strategy": k, "weight": v}
            for k, v in data.items()
        ])
        st.bar_chart(df.set_index("strategy"))
    except:
        st.text(alloc["output"])

# ===== WALLET LEADERS =====
st.subheader("🐋 Smart Money Leaders")

leaders = post("/api/command", {"command": "/wa_get_leaders"})

if isinstance(leaders, dict) and "output" in leaders:
    try:
        data = eval(leaders["output"])
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    except:
        st.text(leaders["output"])

st.caption("Auto refresh every 3s")
time.sleep(3)
st.rerun()
