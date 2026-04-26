from adapters.polymarket import PolymarketAdapter
from adapters.simulator import SimulatorAdapter

ADAPTERS = {
    "polymarket": PolymarketAdapter(),
    "sim": SimulatorAdapter(),
}


def get_adapter(name: str | None):
    if not name or name == "auto":
        return ADAPTERS["polymarket"]

    return ADAPTERS.get(name, ADAPTERS["polymarket"])
