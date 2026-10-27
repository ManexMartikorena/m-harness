"""Small helpers for numbers."""


def clamp(value: float, low: float, high: float) -> float:
    """The value, kept between low and high."""
    return max(low, min(value, high))


def is_odd(n: int) -> bool:
    """Whether n is odd."""
    return n % 2 == 1
