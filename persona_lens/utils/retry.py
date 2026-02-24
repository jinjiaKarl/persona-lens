import time
from typing import Any, Callable

from openai import RateLimitError


def llm_call_with_retry(fn: Callable[..., Any], *args: Any, max_retries: int = 4, **kwargs: Any) -> Any:
    """Call an OpenAI API function with exponential backoff on RateLimitError.

    Waits 5, 10, 20, 40 seconds between retries.
    """
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = 5 * (2 ** attempt)
            time.sleep(wait)
