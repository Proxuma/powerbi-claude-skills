import time
from server.rate_limiter import RateLimiter


def test_allows_calls_under_limit():
    rl = RateLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        allowed, wait = rl.check()
        assert allowed is True
        assert wait == 0


def test_blocks_calls_over_limit():
    rl = RateLimiter(max_calls=2, window_seconds=60)
    rl.check()
    rl.check()
    allowed, wait = rl.check()
    assert allowed is False
    assert wait > 0


def test_window_slides():
    rl = RateLimiter(max_calls=1, window_seconds=0.1)
    rl.check()
    allowed, _ = rl.check()
    assert allowed is False
    time.sleep(0.15)
    allowed, _ = rl.check()
    assert allowed is True


def test_remaining_reports_correctly():
    rl = RateLimiter(max_calls=5, window_seconds=60)
    rl.check()
    rl.check()
    assert rl.remaining() == 3


def test_status_dict():
    rl = RateLimiter(max_calls=10, window_seconds=300)
    rl.check()
    status = rl.status()
    assert status["max_calls"] == 10
    assert status["window_seconds"] == 300
    assert status["remaining"] == 9
