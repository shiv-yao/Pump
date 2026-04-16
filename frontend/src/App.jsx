import { useState } from "react";
import "./index.css";
import Navbar from "./components/Navbar";
import LandingPage from "./pages/LandingPage";
import AuthPage from "./pages/AuthPage";
import AppDashboard from "./pages/AppDashboard";

export default function App() {
  const [authPayload, setAuthPayload] = useState(null);
  const [showAuth, setShowAuth] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Navbar token={authPayload?.token} onLogout={() => setAuthPayload(null)} />
      {!authPayload ? (
        !showAuth ? <LandingPage onShowAuth={() => setShowAuth(true)} /> : <div className="px-6 py-16"><AuthPage onLoginSuccess={setAuthPayload} /></div>
      ) : (
        <AppDashboard token={authPayload.token} authPayload={authPayload} />
      )}
    </div>
  );
}\n