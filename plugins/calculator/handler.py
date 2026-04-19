import ast, operator
def calculate(expression: str) -> str:
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod}
    def eval_node(node):
        if isinstance(node, ast.Num): return node.n
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp): return ops[type(node.op)](eval_node(node.operand))
        raise ValueError(f"Unsupported expression: {node}")
    try:
        tree = ast.parse(expression, mode="eval")
        return f"{expression} = {eval_node(tree.body)}"
    except Exception as e:
        return f"計算錯誤: {e}"
