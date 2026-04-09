from app.state import engine

def update_runtime_stats():
    engine.stats["open_positions"] = len(engine.positions)
    engine.stats["open_exposure"] = sum(p.get("size", 0) for p in engine.positions)
