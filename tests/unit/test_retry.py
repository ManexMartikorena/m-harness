import pytest

from mharness.domain.retry import NO_RETRIES, RetryPolicy


def fixed(value: float) -> RetryPolicy:
    return RetryPolicy(random=lambda: value)


def test_the_waits_double_from_one_second() -> None:
    policy = fixed(0.0)

    assert [policy.delay(attempt) for attempt in (1, 2, 3)] == [1.0, 2.0, 4.0]


def test_chance_adds_up_to_a_quarter() -> None:
    # random() never reaches 1: just under it, just under 25 % more.
    assert fixed(0.5).delay(1) == pytest.approx(1.125)
    assert fixed(0.999).delay(3) == pytest.approx(4 * 1.24975)


def test_no_retry_is_left_after_the_last() -> None:
    policy = fixed(0.0)

    assert policy.delay(4) is None
    assert policy.delay(0) is None


def test_retry_after_wins_without_chance() -> None:
    assert fixed(0.9).delay(1, retry_after=30.0) == 30.0


def test_a_wait_of_more_than_a_minute_is_not_retried() -> None:
    # A quota that comes back tomorrow: waiting would only delay the error
    # (decision of the maintainer, audit of hito 8).
    assert fixed(0.0).delay(1, retry_after=600.0) is None
    assert fixed(0.0).delay(1, retry_after=60.0) == 60.0


def test_a_date_already_past_is_no_wait() -> None:
    assert fixed(0.0).delay(1, retry_after=-5.0) == 0.0


def test_retry_after_does_not_add_retries() -> None:
    assert fixed(0.0).delay(4, retry_after=1.0) is None


def test_no_retries_never_waits() -> None:
    assert NO_RETRIES.delay(1) is None
