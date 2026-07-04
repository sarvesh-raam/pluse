from app.engine.retry import compute_delay_sec
from app.models.enums import RetryStrategy


def test_fixed_strategy_delay_is_constant():
    assert compute_delay_sec(RetryStrategy.fixed, attempt=1, base_delay_sec=5, max_delay_sec=100) == 5
    assert compute_delay_sec(RetryStrategy.fixed, attempt=5, base_delay_sec=5, max_delay_sec=100) == 5


def test_linear_strategy_delay_scales_with_attempt():
    assert compute_delay_sec(RetryStrategy.linear, attempt=1, base_delay_sec=5, max_delay_sec=100) == 5
    assert compute_delay_sec(RetryStrategy.linear, attempt=2, base_delay_sec=5, max_delay_sec=100) == 10
    assert compute_delay_sec(RetryStrategy.linear, attempt=4, base_delay_sec=5, max_delay_sec=100) == 20


def test_exponential_strategy_delay_doubles_each_attempt():
    assert compute_delay_sec(RetryStrategy.exponential, attempt=1, base_delay_sec=2, max_delay_sec=1000) == 2
    assert compute_delay_sec(RetryStrategy.exponential, attempt=2, base_delay_sec=2, max_delay_sec=1000) == 4
    assert compute_delay_sec(RetryStrategy.exponential, attempt=3, base_delay_sec=2, max_delay_sec=1000) == 8
    assert compute_delay_sec(RetryStrategy.exponential, attempt=4, base_delay_sec=2, max_delay_sec=1000) == 16


def test_exponential_strategy_is_capped_by_max_delay():
    # 2 * 2^9 = 1024, but capped at 50
    assert compute_delay_sec(RetryStrategy.exponential, attempt=10, base_delay_sec=2, max_delay_sec=50) == 50


def test_all_strategies_respect_max_delay_cap():
    for strategy in RetryStrategy:
        delay = compute_delay_sec(strategy, attempt=20, base_delay_sec=5, max_delay_sec=30)
        assert delay <= 30


def test_jitter_stays_within_expected_bounds():
    base = 10.0
    jitter_pct = 0.2
    delays = [
        compute_delay_sec(RetryStrategy.fixed, attempt=1, base_delay_sec=base, max_delay_sec=100, jitter_pct=jitter_pct)
        for _ in range(200)
    ]
    assert all(base * 0.8 <= d <= base * 1.2 for d in delays)
    # with real randomness across 200 samples, they shouldn't all be identical
    assert len(set(delays)) > 1


def test_zero_jitter_is_deterministic():
    delay = compute_delay_sec(RetryStrategy.fixed, attempt=1, base_delay_sec=7, max_delay_sec=100, jitter_pct=0.0)
    assert delay == 7


def test_delay_is_never_negative():
    delay = compute_delay_sec(RetryStrategy.fixed, attempt=1, base_delay_sec=1, max_delay_sec=100, jitter_pct=1.0)
    assert delay >= 0.0
