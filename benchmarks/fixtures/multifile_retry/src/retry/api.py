from src.retry.scheduler import retry_delay


def next_delay(attempt, base_seconds, max_seconds):
    """Return a capped delay for a one-based attempt and positive delay bounds."""
    return retry_delay(attempt, base_seconds, max_seconds)
