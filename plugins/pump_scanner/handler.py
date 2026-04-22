import httpx

PUMP_API = "https://frontend-api.pump.fun/coins/latest"


async def pump_latest():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(PUMP_API)
            data = r.json()

            tokens = []
            for t in data[:20]:
                tokens.append({
                    "mint": t.get("mint"),
                    "symbol": t.get("symbol"),
                    "name": t.get("name"),
                    "created": t.get("created_timestamp")
                })

            return {"tokens": tokens}

    except Exception as e:
        return {"error": str(e)}
