import json

from app.settings import PLUGINS_DIR, REGISTRY_FILE


async def ensure_builtin_plugins():
    builtins = {
        "calculator": {
            "plugin_json": {
                "id": "calculator",
                "name": "calculator",
                "description": "數學計算工具",
                "version": "1.0.0",
                "enabled": True,
                "category": "utility",
                "price": 0,
                "author": "system",
                "tools": [{
                    "name": "calculate",
                    "description": "執行數學運算",
                    "input_schema": {
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"]
                    }
                }]
            },
            "handler": '''import ast
import operator

def calculate(expression: str) -> str:
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }

    def eval_node(node):
        if isinstance(node, ast.Num):
            return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            return ops[type(node.op)](eval_node(node.operand))
        raise ValueError(f"Unsupported expression: {node}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = eval_node(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"計算錯誤: {e}"
'''
        }
    }

    for plugin_id, data in builtins.items():
        pdir = PLUGINS_DIR / plugin_id
        pdir.mkdir(parents=True, exist_ok=True)

        plugin_json_path = pdir / "plugin.json"
        handler_path = pdir / "handler.py"

        if not plugin_json_path.exists():
            with open(plugin_json_path, "w", encoding="utf-8") as f:
                json.dump(data["plugin_json"], f, ensure_ascii=False, indent=2)

        if not handler_path.exists():
            with open(handler_path, "w", encoding="utf-8") as f:
                f.write(data["handler"])

    if not REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
