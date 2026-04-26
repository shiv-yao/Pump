from pathlib import Path

ENV_PATH = Path("latest.env")


def apply_env(params: dict):
    if not ENV_PATH.exists():
        ENV_PATH.write_text("")

    lines = ENV_PATH.read_text().splitlines()
    env = {}

    for l in lines:
        if "=" in l:
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip()

    # 覆蓋參數
    for k, v in params.items():
        env[k] = str(round(v, 6))

    # 重寫
    new_text = "\n".join(f"{k}={v}" for k, v in env.items())
    ENV_PATH.write_text(new_text)

    return {"status": "applied", "params": params}
