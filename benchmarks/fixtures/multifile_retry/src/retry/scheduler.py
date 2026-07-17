from src.retry.backoff import exponential_delay


def retry_delay(attempt, base_seconds, max_seconds):
    return exponential_delay(attempt, base_seconds, max_seconds)
