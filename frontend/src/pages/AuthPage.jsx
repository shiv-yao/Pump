import { useState } from "react";
import { login, signup } from "../lib/api";

export default function AuthPage({ onLoginSuccess }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState("");

  async function submit() {
    setError("");
    const result = mode === "login" ? await login(form) : await signup(form);
    if (result.detail) {
      setError(result.detail);
      return;
    }
    if (mode === "signup") {
      const loginResult = await login({ email: form.email, password: form.password });
      if (loginResult.token) onLoginSuccess(loginResult);
      return;
    }
    onLoginSuccess(result);
  }

  return (
    <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="mb-6 text-2xl font-semibold">{mode === "login" ? "Login" : "Create account"}</div>
      <div className="space-y-4">
        {mode === "signup" && (
          <input className="w-full rounded border border-slate-700 bg-slate-950 px-4 py-3" placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        )}
        <input className="w-full rounded border border-slate-700 bg-slate-950 px-4 py-3" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input type="password" className="w-full rounded border border-slate-700 bg-slate-950 px-4 py-3" placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {error ? <div className="text-sm text-red-400">{error}</div> : null}
        <button className="w-full rounded bg-white px-4 py-3 font-medium text-slate-900" onClick={submit}>
          {mode === "login" ? "Login" : "Create account"}
        </button>
        <button className="w-full rounded border border-slate-700 px-4 py-3" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
          {mode === "login" ? "Need an account?" : "Already have an account?"}
        </button>
      </div>
    </div>
  );
}\n