# app/dashboard.py
import os
import time
import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="V66 Dashboard", layout="wide")
st.title("V66 Complete Live Trading Dashboard")


# =========================================================
# HELPERS
# =========================================================

def api_get(path: str, timeout: int = 15):
    r = requests.get(f"{API}{path}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload=None, timeout: int = 20):
    r = requests.post(f"{API}{path}", json=payload or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def safe_get(path: str, default=None, timeout: int = 15):
    try:
        return api_get(path, timeout=timeout)
    except Exception:
        return default


def safe_post(path: str, payload=None, timeout: int = 20):
    try:
        return api_post(path, payload=payload, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("Settings")

auto_refresh = st.sidebar.checkbox("Auto Refresh", value=False)
refresh_sec = st.sidebar.slider("Refresh Interval (sec)", 2, 60, 5)
show_logs_limit = st.sidebar.slider("Logs Limit", 50, 500, 150)
show_trades_limit = st.sidebar.slider("Trades Limit", 10, 200, 50)

st.sidebar.markdown(f"**API**: `{API}`")

if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()


# =========================================================
# TOP CONTROL BAR
# =========================================================

c1, c2, c3, c4, c5 = st.columns(5)

if c1.button("Refresh", use_container_width=True):
    st.rerun()

if c2.button("Start Engine", use_container_width=True):
    res = safe_post("/start")
    if res.get("ok"):
        st.success("Engine started")
    else:
        st.error(res.get("error", "start failed"))

if c3.button("Stop Engine", use_container_width=True):
    res = safe_post("/stop")
    if res.get("ok"):
        st.warning("Engine stopped")
    else:
        st.error(res.get("error", "stop failed"))

if c4.button("Restart Engine", use_container_width=True):
    res = safe_post("/restart")
    if res.get("ok"):
        st.success("Engine restarted")
    else:
        st.error(res.get("error", "restart failed"))

if c5.button("Kill Switch", use_container_width=True):
    res = safe_post("/killswitch")
    if res.get("ok"):
        st.error("Kill switch triggered")
    else:
        st.error(res.get("error", "killswitch failed"))


# =========================================================
# LOAD DATA
# =========================================================

health = safe_get("/health", default={})
metrics = safe_get("/metrics", default={})
positions_data = safe_get("/positions", default={"positions": []})
trades_data = safe_get(f"/trades?limit={show_trades_limit}", default={"trades": []})
signal_data = safe_get("/signal", default={})
brain_data = safe_get("/fund/brain", default={})
config_data = safe_get("/config", default={})
debug_data = safe_get("/debug/state", default={})

if not health:
    st.error("API unreachable. Check API_BASE_URL / FastAPI service / Railway deployment.")
    st.stop()


# =========================================================
# STATUS CARDS
# =========================================================

summary = metrics.get("summary", {}) or {}
performance = metrics.get("performance", {}) or {}
trading = metrics.get("trading", {}) or {}

k1, k2, k3, k4, k5, k6 = st.columns(6)

k1.metric("Engine", "RUNNING" if health.get("engine_running") else "STOPPED")
k2.metric("Task Alive", "YES" if health.get("task_alive") else "NO")
k3.metric("Capital", f"{summary.get('capital', 0):.4f}")
k4.metric("Return %", f"{summary.get('return_pct', 0) * 100:.2f}%")
k5.metric("Open Positions", f"{trading.get('open_positions', 0)}")
k6.metric("Errors", f"{trading.get('errors', 0)}")


# =========================================================
# MAIN TABS
# =========================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Overview",
    "Manual Trade",
    "Positions",
    "Trades",
    "Logs",
    "Debug",
])


# =========================================================
# TAB 1: OVERVIEW
# =========================================================

with tab1:
    a, b = st.columns(2)

    with a:
        st.subheader("Summary")
        st.json(summary)

        st.subheader("Performance")
        st.json(performance)

        st.subheader("Trading")
        st.json(trading)

    with b:
        st.subheader("Last Signal")
        st.json(signal_data)

        st.subheader("Fund Brain")
        st.json(brain_data)

        st.subheader("Config")
        st.json(config_data)


# =========================================================
# TAB 2: MANUAL TRADE
# =========================================================

with tab2:
    st.subheader("Manual Buy / Sell")

    buy_col, sell_col = st.columns(2)

    with buy_col:
        st.markdown("### Buy")
        buy_mint = st.text_input("Buy Mint", key="buy_mint")
        buy_amount = st.number_input("Amount SOL", min_value=0.0, value=0.01, step=0.001, format="%.6f", key="buy_amount")

        if st.button("Execute Buy", use_container_width=True):
            if not buy_mint.strip():
                st.error("Mint required")
            else:
                res = safe_post("/trade/buy", {
                    "mint": buy_mint.strip(),
                    "amount_sol": float(buy_amount),
                }, timeout=30)
                if res.get("ok"):
                    st.success("Buy sent")
                    st.json(res)
                else:
                    st.error(res.get("error", res))

    with sell_col:
        st.markdown("### Sell")
        sell_mint = st.text_input("Sell Mint", key="sell_mint")
        sell_pct = st.slider("Sell %", min_value=1, max_value=100, value=100, key="sell_pct")

        if st.button("Execute Sell", use_container_width=True):
            if not sell_mint.strip():
                st.error("Mint required")
            else:
                res = safe_post("/trade/sell", {
                    "mint": sell_mint.strip(),
                    "pct": float(sell_pct) / 100.0,
                }, timeout=30)
                if res.get("ok"):
                    st.success("Sell sent")
                    st.json(res)
                else:
                    st.error(res.get("error", res))

    st.markdown("---")
    if st.button("Manual Rebalance", use_container_width=True):
        res = safe_post("/fund/rebalance", timeout=30)
        if res.get("ok"):
            st.success("Rebalance triggered")
            st.json(res)
        else:
            st.error(res.get("error", res))


# =========================================================
# TAB 3: POSITIONS
# =========================================================

with tab3:
    st.subheader("Open Positions")
    positions = positions_data.get("positions", []) or metrics.get("positions", []) or []

    if positions:
        st.json(positions)
    else:
        st.info("No open positions")


# =========================================================
# TAB 4: TRADES
# =========================================================

with tab4:
    st.subheader("Recent Trades")
    recent_trades = trades_data.get("trades", []) or metrics.get("recent_trades", []) or []

    if recent_trades:
        st.json(recent_trades)
    else:
        st.info("No recent trades")


# =========================================================
# TAB 5: LOGS
# =========================================================

with tab5:
    st.subheader("Logs")

    logs = metrics.get("logs", []) or []
    if len(logs) > show_logs_limit:
        logs = logs[-show_logs_limit:]

    if logs:
        st.code("\n".join(logs), language="text")
    else:
        st.info("No logs")


# =========================================================
# TAB 6: DEBUG
# =========================================================

with tab6:
    st.subheader("Health")
    st.json(health)

    st.subheader("Debug State")
    st.json(debug_data)

    st.subheader("Raw Metrics")
    st.json(metrics)
