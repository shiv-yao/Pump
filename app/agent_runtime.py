import logging
from typing import Optional

try:
    import anthropic
except Exception:
    anthropic = None

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None

from app.plugin_manager import execute_tool, get_active_tools
from app.provider_status import is_fallback_error
from app.settings import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_GPT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    ENABLE_CLAUDE,
    ENABLE_OPENAI,
)

log = logging.getLogger(__name__)

agent_sessions: dict[str, "AgentSession"] = {}


def flatten_history_to_text(history: Optional[list]) -> str:
    if not history:
        return ""
    lines = []
    for item in history:
        role = item.get("role", "unknown")
        content = item.get("content", "")
        if isinstance(content, list):
            import json
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


class AgentSession:
    def __init__(self):
        import os

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        self.claude_client = anthropic.AsyncAnthropic(api_key=anthropic_key) if (anthropic and ENABLE_CLAUDE and anthropic_key) else None
        self.openai_client = AsyncOpenAI(api_key=openai_key) if (AsyncOpenAI and ENABLE_OPENAI and openai_key) else None

        self.claude_model = DEFAULT_CLAUDE_MODEL
        self.gpt_model = DEFAULT_GPT_MODEL
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    async def _run_with_claude(self, user_message: str, history: Optional[list] = None) -> dict:
        messages = list(history) if history else []
        messages.append({"role": "user", "content": user_message})

        tools = get_active_tools()
        steps = []
        max_iterations = 8

        for _ in range(max_iterations):
            kwargs = {
                "model": self.claude_model,
                "max_tokens": 2048,
                "system": self.system_prompt,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools

            response = await self.claude_client.messages.create(**kwargs)
            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            text_blocks = [b for b in response.content if getattr(b, "type", None) == "text"]

            for tb in text_blocks:
                text = getattr(tb, "text", "")
                if text.strip():
                    steps.append({"type": "text", "content": text})

            if response.stop_reason == "end_turn" or not tool_uses:
                break

            tool_results = []
            for tool_use in tool_uses:
                steps.append({
                    "type": "tool_call",
                    "tool": tool_use.name,
                    "input": tool_use.input,
                })
                result = await execute_tool(tool_use.name, tool_use.input)
                steps.append({
                    "type": "tool_result",
                    "tool": tool_use.name,
                    "result": result,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        final_text = ""
        for step in reversed(steps):
            if step["type"] == "text" and step["content"].strip():
                final_text = step["content"]
                break

        return {
            "response": final_text or "Claude 已完成，但沒有文字回應。",
            "steps": steps,
            "messages": messages,
            "provider": "claude",
        }

    async def _run_with_gpt(self, user_message: str, history: Optional[list] = None, reason: str = "") -> dict:
        history_text = flatten_history_to_text(history)
        prompt = f"{self.system_prompt}\n\n使用者訊息：{user_message}"
        if history_text:
            prompt = f"{self.system_prompt}\n\n先前對話：\n{history_text}\n\n使用者訊息：{user_message}"

        resp = await self.openai_client.responses.create(
            model=self.gpt_model,
            input=prompt,
        )

        steps = []
        if reason:
            steps.append({"type": "fallback", "content": "Claude unavailable, switched to GPT"})

        return {
            "response": getattr(resp, "output_text", "") or "GPT 已接手，但沒有文字回應。",
            "steps": steps,
            "messages": history or [],
            "provider": "gpt",
        }

    async def _run_local_fallback(self, user_message: str, history: Optional[list] = None):
        lowered = user_message.strip()
        if any(ch.isdigit() for ch in lowered) and any(op in lowered for op in ["+", "-", "*", "/", "%"]):
            result = await execute_tool("calculate", {"expression": lowered})
            return {
                "response": f"雲端模型暫時不可用，已改用本地 calculator：\n{result}",
                "steps": [{"type": "tool_result", "tool": "calculate", "result": result}],
                "messages": history or [],
                "provider": "local",
            }
        return None

    async def run(self, user_message: str, history: Optional[list] = None) -> dict:
        history = list(history) if history else []

        if self.claude_client:
            try:
                return await self._run_with_claude(user_message, history)
            except Exception as e:
                log.error(f"Claude failed: {e}")

                if self.openai_client and is_fallback_error(str(e)):
                    try:
                        return await self._run_with_gpt(user_message, history, reason=str(e))
                    except Exception as gpt_err:
                        log.error(f"GPT fallback failed: {gpt_err}")

        if self.openai_client:
            try:
                return await self._run_with_gpt(user_message, history, reason="Claude unavailable")
            except Exception as e:
                log.error(f"GPT failed: {e}")

        local = await self._run_local_fallback(user_message, history)
        if local:
            return local

        return {
            "response": "目前沒有可用的雲端模型，請檢查 API keys。",
            "steps": [],
            "messages": history,
            "error": "no_model_available",
            "provider": "none",
        }


def get_session(session_id: str = "default") -> AgentSession:
    if session_id not in agent_sessions:
        agent_sessions[session_id] = AgentSession()
    return agent_sessions[session_id]
