def exponential_delay(attempt, base_seconds, max_seconds):
    return base_seconds * (2 ** attempt)
