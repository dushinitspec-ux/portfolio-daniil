from app.ratelimit import SlidingWindowLimiter


def test_limit_per_window() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(limit=3, window_s=60, clock=lambda: now[0])
    assert [limiter.allow(1) for _ in range(4)] == [True, True, True, False]
    assert limiter.allow(2) is True  # other guests are not affected
    now[0] = 60.0
    assert limiter.allow(1) is True  # the window has moved on
