from typing import Dict

def estimate_slippage(size: float, liquidity: float, volatility: float = 0.02):
    """
    更接近真實的滑點模型：
    - size / liquidity → impact
    - volatility → 放大波動滑點
    """

    if liquidity <= 0:
        return 1.0

    base_impact = size / liquidity

    # 非線性（關鍵）
    impact = base_impact ** 0.6

    # 波動放大
    impact *= (1 + volatility * 5)

    return min(impact, 1.0)


def execution_score(price_impact: float, fee: float = 0.0007):
    """
    execution quality score
    """
    cost = price_impact + fee
    return max(0.0, 1 - cost)
