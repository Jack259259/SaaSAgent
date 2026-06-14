"""底层数值工具(虚构示例,无真实业务口径)。"""


def safe_div(numerator, denominator):
    """除零保护:分母为 0 返回 0.0。被 calculator 多处调用。"""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def clamp(value, low, high):
    return max(low, min(high, value))
