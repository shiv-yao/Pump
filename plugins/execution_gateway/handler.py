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

RPC_URL = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
JUP_ORDER = os.getenv("JUP_ORDER_URL", "https://api.jup.ag/swap/v2/order")
JUP_EXECUTE = os.getenv("JUP_EXECUTE_URL", "https://api.jup.ag/swap/v2/execute")

USE_JITO = os.getenv("USE_JITO", "false").lower() == "true"
JITO_BASE_URL = os.getenv("JITO_BASE_URL", "https://mainnet.block-engine.jito.wtf")
JITO_BUNDLE_URL = f"{JITO_BASE_URL}/api/v1/bundles"
JITO_TX_URL = f"{JITO_BASE_URL}/api/v1/transactions"
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "2000"))

PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "").strip()


def _rpc_body(method: str, params=None, req_id: int = 1):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or []
    }


def load_keypair() -> Keypair:
    if not PRIVATE_KEY:
        raise Exception("Missing SOLANA_PRIVATE_KEY")

    raw = base64.b64decode(PRIVATE_KEY)
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


async def jupiter_order(input_mint: str, output_mint: str, amount: float):
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            JUP_ORDER,
            json={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": int(amount),
                "slippageBps": 80
            }
        )
        return res.json()


async def jupiter_execute(signed_tx_base64: str, request_id: str | None):
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            JUP_EXECUTE,
            json={
                "signedTransaction": signed_tx_base64,
                "requestId": request_id
            }
        )
        return res.json()


def sign_jupiter_tx(tx_base64: str) -> str:
    """
    簽 Jupiter 回來的 versioned tx
    """
    kp = load_keypair()

    tx_bytes = base64.b64decode(tx_base64)
    tx = VersionedTransaction.from_bytes(tx_bytes)
    tx.sign([kp])

    return base64.b64encode(bytes(tx)).decode()


async def get_jito_tip_accounts() -> list[str]:
    """
    Jito getTipAccounts: JSON-RPC 到 /api/v1/bundles
    """
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
    """
    建一筆獨立 SOL transfer tip tx，作為 bundle 第 2 筆交易。
    """
    lamports = int(tip_lamports or JITO_TIP_LAMPORTS)
    if lamports < 1000:
        lamports = 1000  # Jito 文件提到 bundle 最低 tip 1000 lamports

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
    """
    sendBundle: params = [[tx1, tx2, ...], {"encoding": "base64"}]
    """
    payload = _rpc_body(
        "sendBundle",
        [signed_txs_base64, {"encoding": "base64"}],
        req_id=1
    )

    async with httpx.AsyncClient(timeout=15) as client:
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
    """
    sendTransaction 到 Jito transaction endpoint。
    Jito 文件說這是 validator-forwarded path，且可用 bundleOnly=true 作 revert protection。
    """
    payload = _rpc_body(
        "sendTransaction",
        [signed_tx_base64, {"encoding": "base64"}],
        req_id=1
    )

    async with httpx.AsyncClient(timeout=15) as client:
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


async def trade_order(symbol=None, side="buy", size=0.0, **kwargs):
    """
    這裡沿用你現有 symbol->mint 簡化方式。
    真實版最好再接 token resolver。
    """
    try:
        if symbol == "SOL":
            input_mint = "So11111111111111111111111111111111111111112"
            output_mint = "USDC"
        else:
            input_mint = "USDC"
            output_mint = symbol

        if side == "sell":
            input_mint, output_mint = output_mint, input_mint

        order = await jupiter_order(input_mint, output_mint, size)
        tx_base64 = order.get("transaction")
        request_id = order.get("requestId") or secrets.token_hex(8)

        if not tx_base64:
            return {"error": "no_transaction", "raw": order}

        signed_swap_tx = sign_jupiter_tx(tx_base64)

        # ===== Jito path =====
        if USE_JITO:
            try:
                signed_tip_tx = await build_tip_tx_base64(JITO_TIP_LAMPORTS)
                bundle_res = await send_jito_bundle([signed_swap_tx, signed_tip_tx])

                if "error" not in bundle_res:
                    return {
                        "filled": True,
                        "via": "jito_bundle",
                        "bundle_id": bundle_res.get("bundle_id"),
                        "raw": bundle_res
                    }
            except Exception as e:
                # 先記住錯，再 fallback
                bundle_res = {"error": f"bundle_build_or_send_failed: {str(e)}"}

            # fallback 1: Jito 單筆
            jito_tx_res = await send_jito_transaction(signed_swap_tx)
            if "error" not in jito_tx_res:
                return {
                    "filled": True,
                    "via": "jito_tx",
                    "tx": jito_tx_res.get("signature"),
                    "raw": jito_tx_res
                }

            # fallback 2: Jupiter execute
            execute_res = await jupiter_execute(signed_swap_tx, request_id)
            return {
                "filled": True,
                "via": "jup_execute_fallback",
                "tx": execute_res.get("txid"),
                "raw": {
                    "bundle_error": bundle_res,
                    "jito_tx_error": jito_tx_res,
                    "execute": execute_res
                }
            }

        # ===== Default Jupiter path =====
        execute_res = await jupiter_execute(signed_swap_tx, request_id)
        return {
            "filled": True,
            "via": "jupiter",
            "tx": execute_res.get("txid"),
            "raw": execute_res
        }

    except Exception as e:
        return {"error": str(e)}
