"""A retry policy for the tests of a single failure."""

from mharness.domain.retry import RetryPolicy

# Fails at once: one failure is one failure.
NO_RETRIES = RetryPolicy(max_retries=0)
