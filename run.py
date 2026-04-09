import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent

def main():
    env = os.environ.copy()
    api = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "app.api:app",
        "--host", "0.0.0.0", "--port", os.getenv("PORT_API", "8000")
    ], cwd=ROOT, env=env)
    ui = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", "app/dashboard.py",
        "--server.address", "0.0.0.0",
        "--server.port", os.getenv("PORT_UI", "8501"),
        "--browser.gatherUsageStats", "false",
    ], cwd=ROOT, env=env)
    try:
        api.wait()
        ui.wait()
    except KeyboardInterrupt:
        api.terminate()
        ui.terminate()

if __name__ == "__main__":
    main()
