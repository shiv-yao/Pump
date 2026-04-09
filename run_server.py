
import os
import uvicorn

def get_port():
    try:
        return int(os.environ.get("PORT", "8000"))
    except Exception:
        return 8000

if __name__ == "__main__":
    port = get_port()
    print("🚀 RUN SERVER")
    print("PORT =", port)
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, log_level="info", access_log=True)
