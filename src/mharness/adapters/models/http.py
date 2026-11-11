"""What every model adapter over HTTP shares (spec hito 9, §1.9): the
timeouts, the `Retry-After` header, the body as text, the provider's text
made safe to show and the cost a provider reports.

Adapters never import each other: what two of them need lives here.
"""

import codecs
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from mharness import __version__
from mharness.domain.errors import (
    ModelAuthError,
    ModelError,
    ModelRateLimitError,
    ModelRequestError,
    ModelResponseError,
    ModelUnavailableError,
)
from mharness.domain.money import SMALLEST

USER_AGENT = f"maha/{__version__} (+https://github.com/ManexMartikorena/m-harness)"
# `read` is the longest silence between two chunks, not the time of the whole
# answer: a long answer that keeps arriving is never cut (spec hito 3, §1.8).
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
# The longest wait for the next event with data. Comments (`: keep-alive`)
# and pings reset `read` but are no progress: a stream that only sends them
# stayed open five minutes in the evals (spec hito 8, §12).
STALL_SECONDS = 120.0
# The provider's error message is shown to the user, cut to this length.
MAX_PROVIDER_MESSAGE = 300


def retry_after(value: str | None, now: datetime) -> float | None:
    """The seconds a `Retry-After` header asks to wait: a whole number of
    seconds, or an HTTP date (RFC 9110, §10.2.3); 0 if the date is past,
    None if it says neither."""
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if when.tzinfo is None:
        # An HTTP date is always in GMT, even if it does not say so.
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def safe(detail: str | None, api_key: str | None) -> str | None:
    """A provider's text, ready to show: without the key, and cut."""
    if not detail:
        return None
    if api_key:
        # Never show the key, even if the provider echoes it back. Before
        # cutting, or a cut key would slip through.
        detail = detail.replace(api_key, "[redacted]")
    return detail[:MAX_PROVIDER_MESSAGE]


def error_message(error: Any) -> str | None:
    """The message of an `error` value: an object with `message`, or text."""
    message = error.get("message") if isinstance(error, dict) else error
    if not isinstance(message, str) or not message.strip():
        return None
    return message.strip()


def provider_message(response: httpx.Response) -> str | None:
    """The `error.message` of an error body, if there is one: OpenAI and
    Anthropic both put it there."""
    try:
        body = response.json()
    except ValueError:
        return None
    return error_message(body.get("error") if isinstance(body, dict) else None)


async def text(response: httpx.Response) -> AsyncIterator[str]:
    """The body as text. The incremental decoder never cuts a character split
    between two network chunks, and drops a leading BOM."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="replace")
    async for chunk in response.aiter_bytes():
        if decoded := decoder.decode(chunk):
            yield decoded
    if decoded := decoder.decode(b"", final=True):
        yield decoded


def provider_cost(opencode: Any, cost: Any) -> Decimal | None:
    """What the provider says the call cost, in USD; None if it does not
    say. OpenCode first: what counts against the plan's limit, then the list
    price; then the plain `cost` of OpenRouter and others (spec hito 7,
    §1.5). Any shape: only an object is read for OpenCode's."""
    fields = opencode if isinstance(opencode, dict) else {}
    for value in (fields.get("allowance"), fields.get("list_cost"), cost):
        if (amount := _amount(value)) is not None:
            return amount
    return None


# More than this for one call is not a cost: a provider's bug.
_MAX_CALL_COST = Decimal(1_000_000)


def _amount(value: object) -> Decimal | None:
    """A number of USD, or None if it is not one, is negative or absurd."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        # str(): the float 6.225e-05 as written, not its binary value.
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or not 0 <= amount <= _MAX_CALL_COST:
        return None
    # Less than any amount (audit after hito 9, S4): free.
    return Decimal(0) if amount < SMALLEST else amount


def whole(value: Any) -> int | None:
    """A whole number the provider sent; anything else, `true` too, is not
    one."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def count(tokens: Any) -> int:
    """A count the provider sent; missing, null, negative or not a whole
    number is 0. One for both formats (audit after hito 10, M5)."""
    return max(whole(tokens) or 0, 0)


def status_error(response: httpx.Response, api_key: str | None) -> ModelError:
    """The error of a response that is not a success: what to tell the
    person, and whether and when it can be tried again."""
    status = response.status_code
    detail = safe(provider_message(response), api_key)
    message = f"HTTP {status}: {detail}" if detail else f"HTTP {status}"
    if status in (401, 403):
        return ModelAuthError(message)
    # When the provider can answer again; 429, 503 and 529 often say it.
    wait = retry_after(response.headers.get("retry-after"), datetime.now(UTC))
    if status == 429:
        return ModelRateLimitError(message, retry_after=wait)
    # 408: the server gave up waiting for the request; it can pass (deep
    # audit after hito 9, M8).
    if status >= 500 or status == 408:
        return ModelUnavailableError(message, retry_after=wait)
    return ModelRequestError(message)


async def check_streaming(response: httpx.Response, api_key: str | None) -> None:
    """Fail if a 200 answer is not an event stream."""
    content_type = response.headers.get("content-type", "").lower()
    if content_type.startswith("text/event-stream"):
        return
    detail = None
    if content_type.startswith("application/json"):
        await response.aread()
        detail = safe(provider_message(response), api_key)
    raise ModelResponseError(detail or "the provider did not stream")
