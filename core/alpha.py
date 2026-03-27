
def compute_alpha(strength, liq, impact):
    return (
        strength * 4000 +
        min(liq / 100000, 3) * 30 -
        impact * 120
    )

def position_size(alpha):
    if alpha > 180:
        return 0.025
    elif alpha > 140:
        return 0.015
    elif alpha > 120:
        return 0.008
    return 0
