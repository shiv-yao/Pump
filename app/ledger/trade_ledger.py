import time
from typing import Dict, Any, List


class TradeLedger:
    def __init__(self):
        self.rows: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []

    def add_fill(
        self,
        *,
        side: str,
        mint: str,
        size_sol: float,
        price: float,
        expected_out: float = 0.0,
        actual_out: float = 0.0,
        fee_sol: float = 0.0,
        gas_sol: float = 0.0,
        source: str = "unknown",
        strategy: str = "unknown",
        tx_sig: str = "",
        meta: Dict[str, Any] | None = None,
    ):
        slip = 0.0
        if expected_out > 0 and actual_out > 0:
            slip = (actual_out - expected_out) / expected_out

        self.rows.append({
            "ts": time.time(),
            "side": side,
            "mint": mint,
            "size_sol": size_sol,
            "price": price,
            "expected_out": expected_out,
            "actual_out": actual_out,
            "fee_sol": fee_sol,
            "gas_sol": gas_sol,
            "slippage": slip,
            "source": source,
            "strategy": strategy,
            "tx_sig": tx_sig,
            "meta": meta or {},
        })
        self.rows = self.rows[-3000:]

    def add_equity_point(self, equity: float, cash: float):
        self.equity_curve.append({
            "ts": time.time(),
            "equity": equity,
            "cash": cash,
        })
        self.equity_curve = self.equity_curve[-5000:]

    def summary(self) -> Dict[str, Any]:
        realized = 0.0
        total_fee = 0.0
        total_gas = 0.0
        for r in self.rows:
            total_fee += float(r.get("fee_sol", 0.0))
            total_gas += float(r.get("gas_sol", 0.0))

        return {
            "fills": len(self.rows),
            "total_fee_sol": total_fee,
            "total_gas_sol": total_gas,
            "equity_points": len(self.equity_curve),
        }
