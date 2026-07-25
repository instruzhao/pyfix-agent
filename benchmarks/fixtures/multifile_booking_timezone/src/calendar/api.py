from src.calendar.service import overlaps


def conflicts(first_start, first_end, second_start, second_end):
    return overlaps(first_start, first_end, second_start, second_end)
