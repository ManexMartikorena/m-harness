import pytest

from mharness.domain import errors


@pytest.mark.parametrize(
    "error",
    [
        errors.ModelAuthError,
        errors.ModelRateLimitError,
        errors.ModelRequestError,
        errors.ModelUnavailableError,
        errors.ModelResponseError,
    ],
)
def test_every_model_error_is_a_model_error(error: type[Exception]) -> None:
    assert issubclass(error, errors.ModelError)


@pytest.mark.parametrize(
    "error", [errors.ModelRateLimitError, errors.ModelUnavailableError]
)
def test_what_may_pass_later_is_retryable_and_says_how_long(
    error: type[errors.RetryableModelError],
) -> None:
    assert issubclass(error, errors.RetryableModelError)
    assert error("HTTP 429").retry_after is None
    assert error("HTTP 429", retry_after=3.0).retry_after == 3.0


@pytest.mark.parametrize(
    "error",
    [errors.ModelAuthError, errors.ModelRequestError, errors.ModelResponseError],
)
def test_what_repeating_does_not_fix_is_not_retryable(error: type[Exception]) -> None:
    assert not issubclass(error, errors.RetryableModelError)
