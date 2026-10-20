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
