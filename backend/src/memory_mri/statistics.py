import math


def wilson_score_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("successes must be between 0 and total")
    if total == 0:
        return (0.0, 0.0)
    phat = successes / total
    denominator = 1 + (z**2 / total)
    center = (phat + (z**2 / (2 * total))) / denominator
    margin = (z / denominator) * math.sqrt((phat * (1 - phat) / total) + (z**2 / (4 * total**2)))
    return (max(0.0, center - margin), min(1.0, center + margin))
