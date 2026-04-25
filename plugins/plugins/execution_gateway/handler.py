import os
import base64
import secrets
import httpx

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.system_program import transfer, TransferParams
from solders.message import MessageV0
from solders.transaction import VersionedTransaction

from app.utils.loader import call

# =========================
# CONFIG
# =========================

RPC_URL = os.getenv("SOLANA_RPC", os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com"))
JUP_ORDER_URL = os.getenv("JUP_ORDER_URL", "https://api.jup.ag/swap/v2/order")
JUP_EXECUTE_URL = os.getenv("JUP_EXECUTE_URL", "https://api.jup.ag/swap/v2/execute")

USE_JITO = os.getenv("USE_JITO", "false").lower() == "true"
JITO_BASE_URL = os.getenv("JITO_BASE_URL", "https://mainnet.block-engine.jito.wtf")
JITO_BUNDLE_URL = f"{JITO_BASE_URL}/api/v1/bundles"
JITO_TX_URL = f"{JITO_BASE_URL}/api/v1/transactions"
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "2000"))

PRIVATE_KEY_B64 = os.getenv("SOLANA_PRIVATE_KEY", os.getenv("PRIVATE_KEY", "")).strip()
REAL_TRADING = os.getenv("REAL_TRADING", "false").lower() == "true"
MANUAL_CONFIRM = os.getenv("MANUAL_CONFIRM", "true").lower() == "true"
MAX_ORDER_SIZE = float(os.getenv("MAX_ORDER_SIZE", os.getenv("MAX_POSITION", "25")))

USDC_MINT = os.getenv(
    "USDC_MINT",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGk9n9Hh4v"
)
SOL_MINT = os.getenv(
    "SOL_MINT",
    "So11111111111111111111111111111111111111112"
)


# =========================
# HELPERS
# =========================

def _rpc_body(method: str, params=None, req_id: int = 1):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or []
    }


def _f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def load_keypair() -> Keypair:
    if not PRIVATE_KEY_B64:
        raise Exception("Missing SOLANA_PRIVATE_KEY")

    raw = base64.b64decode(PRIVATE_KEY_B64)
    return Keypair.from_bytes(raw)


async def rpc_get_latest_blockhash() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            RPC_URL,
            headers={"Content-Type": "application/json"},
            json=_rpc_body("getLatestBlockhash", [{"commitment": "processed"}]),
        )
        data = res.json()

    if "error" in data:
        raise Exception(f"getLatestBlockhash error: {data['error']}")

    return data["result"]["value"]["blockhash"]


# =========================
# JUPITER
# =========================

async def jupiter_order(input_mint: str, output_mint: str, amount: float, slippage_bps: int = 80):
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            JUP_ORDER_URL,
            json={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": int(amount),
                "slippageBps": int(slippage_bps)
            }
        )
        return res.json()


async def jupiter_execute(signed_tx_base64: str, request_id: str | None):
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            JUP_EXECUTE_URL,
            json={
                "signedTransaction": signed_tx_base64,
                "requestId": request_id
            }
        )
        return res.json()


def sign_jupiter_tx(tx_base64: str) -> str:
    kp = load_keypair()

    tx_bytes = base64.b64decode(tx_base64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    tx.sign([kp])

    return base64.b64encode(bytes(tx)).decode()


# =========================
# JITO
# =========================

async def get_jito_tip_accounts() -> list[str]:
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            JITO_BUNDLE_URL,
            headers={"Content-Type": "application/json"},
            json=_rpc_body("getTipAccounts"),
        )
        data = res.json()

    if "error" in data:
        raise Exception(f"getTipAccounts error: {data['error']}")

    accounts = data.get("result", [])
    if not accounts:
        raise Exception("No Jito tip accounts returned")

    return accounts


async def build_tip_tx_base64(tip_lamports: int | None = None) -> str:
    lamports = int(tip_lamports or JITO_TIP_LAMPORTS)
    if lamports < 1000:
        lamports = 1000

    kp = load_keypair()
    payer = kp.pubkey()

    tip_accounts = await get_jito_tip_accounts()
    tip_account = Pubkey.from_string(tip_accounts[0])

    blockhash_str = await rpc_get_latest_blockhash()
    recent_blockhash = Hash.from_string(blockhash_str)

    ix = transfer(
        TransferParams(
            from_pubkey=payer,
            to_pubkey=tip_account,
            lamports=lamports
        )
    )

    msg = MessageV0.try_compile(
        payer=payer,
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=recent_blockhash,
    )

    tx = VersionedTransaction(msg, [kp])
    return base64.b64encode(bytes(tx)).decode()


async def send_jito_bundle(signed_txs_base64: list[str]):
    payload = _rpc_body(
        "sendBundle",
        [signed_txs_base64, {"encoding": "base64"}],
        req_id=1
    )

    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            JITO_BUNDLE_URL,
            headers={"Content-Type": "application/json"},
            json=payload
        )
        data = res.json()

    if "error" in data:
        return {"error": f"jito_bundle_error: {data['error']}"}

    return {
        "ok": True,
        "bundle_id": data.get("result"),
        "raw": data
    }


async def send_jito_transaction(signed_tx_base64: str):
    payload = _rpc_body(
        "sendTransaction",
        [signed_tx_base64, {"encoding": "base64"}],
        req_id=1
    )

    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            f"{JITO_TX_URL}?bundleOnly=true",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        data = res.json()

    if "error" in data:
        return {"error": f"jito_tx_error: {data['error']}"}

    return {
        "ok": True,
        "signature": data.get("result"),
        "raw": data
    }


# =========================
# TOKEN RESOLUTION
# =========================

async def resolve_symbol_to_mint(symbol: str):
    if not symbol:
        return {"error": "missing_symbol"}

    # already mint-like
    if len(symbol) > 30:
        return {
            "symbol": symbol,
            "mint": symbol,
            "source": "direct"
        }

    if symbol.upper() == "SOL":
        return {
            "symbol": "SOL",
            "mint": SOL_MINT,
            "source": "builtin"
        }

    token = await call("resolve_token", {"symbol": symbol})
    if isinstance(token, dict) and "error" not in token:
        return token

    return {"error": f"token_resolve_failed: {symbol}"}


# =========================
# EXECUTION
# =========================

async def trade_order(symbol=None, side="buy", size=0.0, slippage_bps=80, confirm=False, reason=None, **kwargs):
    """
    Unified real execution:
      1. resolve token
      2. Jupiter order
      3. sign
      4. Jito bundle (optional)
      5. Jito tx fallback
      6. Jupiter execute fallback
    """
    try:
        if not symbol:
            return {"error": "missing_symbol"}

        side = str(side or "buy").lower().strip()
        if side not in {"buy", "sell"}:
            return {"error": f"invalid_side: {side}"}

        amount = _f(size, 0.0)
        if amount <= 0:
            return {"error": "invalid_size"}
        if amount > MAX_ORDER_SIZE:
            return {"error": "risk_blocked_max_order_size", "max_order_size": MAX_ORDER_SIZE, "requested": amount}

        if not REAL_TRADING:
            token_preview = await resolve_symbol_to_mint(symbol)
            return {
                "filled": False,
                "paper": True,
                "via": "paper_guard",
                "message": "REAL_TRADING=false; no on-chain transaction was sent",
                "symbol": symbol,
                "side": side,
                "size": amount,
                "token": token_preview,
                "reason": reason,
            }

        if MANUAL_CONFIRM and not confirm:
            return {
                "error": "manual_confirm_required",
                "message": "Set confirm=true in request or MANUAL_CONFIRM=false to allow live execution",
            }

        token = await resolve_symbol_to_mint(symbol)
        if isinstance(token, dict) and "error" in token:
            return token

        mint = token["mint"]

        if side == "buy":
            input_mint = USDC_MINT
            output_mint = mint
        else:
            input_mint = mint
            output_mint = USDC_MINT

        order = await jupiter_order(
            input_mint=input_mint,
            output_mint=output_mint,
            amount=amount,
            slippage_bps=int(slippage_bps),
        )

        tx_base64 = order.get("transaction")
        request_id = order.get("requestId") or secrets.token_hex(8)

        if not tx_base64:
            return {"error": "no_transaction", "raw": order}

        signed_swap_tx = sign_jupiter_tx(tx_base64)

        # ===== JITO PATH =====
        if USE_JITO:
            bundle_error = None

            try:
                signed_tip_tx = await build_tip_tx_base64(JITO_TIP_LAMPORTS)
                bundle_res = await send_jito_bundle([signed_swap_tx, signed_tip_tx])

                if "error" not in bundle_res:
                    return {
                        "filled": True,
                        "via": "jito_bundle",
                        "bundle_id": bundle_res.get("bundle_id"),
                        "symbol": symbol,
                        "mint": mint,
                        "size": amount,
                        "raw": bundle_res
                    }

                bundle_error = bundle_res
            except Exception as e:
                bundle_error = {"error": f"bundle_build_or_send_failed: {str(e)}"}

            # fallback 1: Jito single tx
            jito_tx_res = await send_jito_transaction(signed_swap_tx)
            if "error" not in jito_tx_res:
                return {
                    "filled": True,
                    "via": "jito_tx",
                    "tx": jito_tx_res.get("signature"),
                    "symbol": symbol,
                    "mint": mint,
                    "size": amount,
                    "raw": jito_tx_res
                }

            # fallback 2: Jupiter execute
            execute_res = await jupiter_execute(signed_swap_tx, request_id)
            return {
                "filled": True,
                "via": "jup_execute_fallback",
                "tx": execute_res.get("txid"),
                "symbol": symbol,
                "mint": mint,
                "size": amount,
                "raw": {
                    "bundle_error": bundle_error,
                    "jito_tx_error": jito_tx_res,
                    "execute": execute_res
                }
            }

        # ===== DEFAULT JUPITER PATH =====
        execute_res = await jupiter_execute(signed_swap_tx, request_id)
        return {
            "filled": True,
            "via": "jupiter",
            "tx": execute_res.get("txid"),
            "symbol": symbol,
            "mint": mint,
            "size": amount,
            "raw": execute_res
        }

    except Exception as e:
        return {"error": str(e)}
