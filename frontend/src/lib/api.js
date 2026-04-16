const API_BASE = "http://localhost:8000/api";

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parse(res) {
  return res.json();
}

export async function signup(payload) {
  return parse(await fetch(`${API_BASE}/signup`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  }));
}

export async function login(payload) {
  return parse(await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  }));
}

export async function getDashboard(token) {
  return parse(await fetch(`${API_BASE}/dashboard`, { headers: authHeaders(token) }));
}

export async function getTradingStatus(token) {
  return parse(await fetch(`${API_BASE}/trading/status`, { headers: authHeaders(token) }));
}

export async function updateTradingConfig(token, payload) {
  return parse(await fetch(`${API_BASE}/trading/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  }));
}

export async function startTrading(token) {
  return parse(await fetch(`${API_BASE}/trading/start`, { method: "POST", headers: authHeaders(token) }));
}

export async function stopTrading(token) {
  return parse(await fetch(`${API_BASE}/trading/stop`, { method: "POST", headers: authHeaders(token) }));
}

export async function simulateTrade(token) {
  return parse(await fetch(`${API_BASE}/trading/simulate`, { method: "POST", headers: authHeaders(token) }));
}

export async function getReport(token, period) {
  return parse(await fetch(`${API_BASE}/reports/${period}`, { headers: authHeaders(token) }));
}

export async function getInvestorOverview(token) {
  return parse(await fetch(`${API_BASE}/investor/overview`, { headers: authHeaders(token) }));
}

export async function checkout(token, plan) {
  return parse(await fetch(`${API_BASE}/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ plan })
  }));
}\n