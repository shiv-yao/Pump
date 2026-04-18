from __future__ import annotations

from app.models.schemas import PluginRecord
from app.core.state import engine


PLUGIN_CATALOG: list[PluginRecord] = [
    PluginRecord(id=1, name="Momentum Alpha", slug="momentum-alpha", monthly_price_usd=29, description="Short-term momentum scanner"),
    PluginRecord(id=2, name="Rug Guard", slug="rug-guard", monthly_price_usd=19, description="Basic risk gating plugin"),
    PluginRecord(id=3, name="Execution Pro", slug="execution-pro", monthly_price_usd=49, description="Advanced execution adapter slot"),
]


def list_plugins() -> list[PluginRecord]:
    enabled = engine.plugins_enabled
    out: list[PluginRecord] = []
    for plugin in PLUGIN_CATALOG:
        out.append(plugin.model_copy(update={"enabled": enabled.get(plugin.slug, False)}))
    return out


def enable_plugin(slug: str) -> PluginRecord | None:
    for plugin in PLUGIN_CATALOG:
        if plugin.slug == slug:
            engine.plugins_enabled[slug] = True
            engine.log(f"plugin enabled: {slug}")
            return plugin.model_copy(update={"enabled": True})
    return None


def disable_plugin(slug: str) -> PluginRecord | None:
    for plugin in PLUGIN_CATALOG:
        if plugin.slug == slug:
            engine.plugins_enabled[slug] = False
            engine.log(f"plugin disabled: {slug}")
            return plugin.model_copy(update={"enabled": False})
    return None
