"""Retry logic for Avatar Engine."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 30.0
    backoff_multiplier: float = 2.0
    retryable_errors: tuple = (
        asyncio.TimeoutError,
        ConnectionError,
        OSError,
    )


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        config: Retry configuration
        on_retry: Optional callback called on each retry (attempt_num, exception)
        **kwargs: Keyword arguments for func

    Returns:
        The result of func on success

    Raises:
        The last exception if all retries fail
    """
    if config is None:
        config = RetryConfig()

    last_exc: Optional[Exception] = None
    backoff = config.backoff_base

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_errors as exc:
            last_exc = exc
            if attempt == config.max_attempts:
                logger.warning(f"All {config.max_attempts} attempts failed: {exc}")
                raise

            logger.debug(f"Attempt {attempt} failed: {exc}, retrying in {backoff:.1f}s")
            if on_retry:
                on_retry(attempt, exc)

            await asyncio.sleep(backoff)
            backoff = min(backoff * config.backoff_multiplier, config.backoff_max)
        except Exception:
            # Non-retryable error, re-raise immediately
            raise

    # Should not reach here, but just in case
    if last_exc:
        raise last_exc
    raise RuntimeError("Retry logic error")


def retry_sync(
    func: Callable[..., T],
    *args: Any,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any,
) -> T:
    """
    Retry a sync function with exponential backoff.

    Args:
        func: Function to retry
        *args: Positional arguments for func
        config: Retry configuration
        on_retry: Optional callback called on each retry (attempt_num, exception)
        **kwargs: Keyword arguments for func

    Returns:
        The result of func on success

    Raises:
        The last exception if all retries fail
    """
    import time

    if config is None:
        config = RetryConfig()

    last_exc: Optional[Exception] = None
    backoff = config.backoff_base

    for attempt in range(1, config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except config.retryable_errors as exc:
            last_exc = exc
            if attempt == config.max_attempts:
                logger.warning(f"All {config.max_attempts} attempts failed: {exc}")
                raise

            logger.debug(f"Attempt {attempt} failed: {exc}, retrying in {backoff:.1f}s")
            if on_retry:
                on_retry(attempt, exc)

            time.sleep(backoff)
            backoff = min(backoff * config.backoff_multiplier, config.backoff_max)
        except Exception:
            # Non-retryable error, re-raise immediately
            raise

    # Should not reach here, but just in case
    if last_exc:
        raise last_exc
    raise RuntimeError("Retry logic error")
