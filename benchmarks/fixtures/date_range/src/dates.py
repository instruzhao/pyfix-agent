from datetime import timedelta


def inclusive_dates(start, end):
    result = []
    current = start
    while current < end:
        result.append(current)
        current += timedelta(days=1)
    return result
