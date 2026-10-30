"""Errors of a model call, independent of HTTP (spec hito 2, §1.7).

Adapters translate their transport errors into these, so the core and the
terminal react to them without knowing what is underneath.
"""


class ModelError(Exception):
    """A call to the model failed."""


class ModelAuthError(ModelError):
    """The provider rejected the credentials (HTTP 401 or 403)."""


class RetryableModelError(ModelError):
    """A failure that may pass if the call is repeated later (spec hito 8,
    §1.14). `retry_after`: the seconds the provider asked to wait, if it
    said (`Retry-After`)."""

    def __init__(self, message: str = "", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ModelRateLimitError(RetryableModelError):
    """The provider asked to slow down (HTTP 429)."""


class ModelRequestError(ModelError):
    """The provider rejected the request (another 4xx, such as an unknown model)."""


class ModelUnavailableError(RetryableModelError):
    """The provider could not answer (5xx, timeout or network failure)."""


class ModelResponseError(ModelError):
    """The provider answered 200 with a body that cannot be understood."""
