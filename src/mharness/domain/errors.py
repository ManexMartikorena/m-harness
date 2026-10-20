"""Errors of a model call, independent of HTTP (spec hito 2, §1.7).

Adapters translate their transport errors into these, so the core and the
terminal react to them without knowing what is underneath.
"""


class ModelError(Exception):
    """A call to the model failed."""


class ModelAuthError(ModelError):
    """The provider rejected the credentials (HTTP 401 or 403)."""


class ModelRateLimitError(ModelError):
    """The provider asked to slow down (HTTP 429)."""


class ModelRequestError(ModelError):
    """The provider rejected the request (another 4xx, such as an unknown model)."""


class ModelUnavailableError(ModelError):
    """The provider could not answer (5xx, timeout or network failure)."""


class ModelResponseError(ModelError):
    """The provider answered 200 with a body that cannot be understood."""
