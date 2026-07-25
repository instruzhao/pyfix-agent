from src.calendar.intervals import half_open_overlap


def overlaps(first_start, first_end, second_start, second_end):
    return half_open_overlap(first_start, first_end, second_start, second_end)
