import os
import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="V61 Dashboard", layout="wide")
st.title("V61 Complete Live Trading Dashboard")

col1, col2 = st.columns(2)
if col1.button("Refresh"):
    st.rerun()
if col2.button("Kill Switch"):
    try:
        requests.post(f"{API}/killswitch", timeout=8)
    except Exception as e:
        st.error(str(e))

try:
    metrics = requests.get(f"{API}/metrics", timeout=15).json()
    st.subheader("Summary")
    st.json(metrics.get("summary", {}))
    st.subheader("Trading")
    st.json(metrics.get("trading", {}))
    st.subheader("Open Positions")
    st.json(metrics.get("positions", []))
    st.subheader("Recent Trades")
    st.json(metrics.get("recent_trades", []))
    st.subheader("Logs")
    st.code("\n".join(metrics.get("logs", [])))
except Exception as e:
    st.error(f"API error: {e}")
