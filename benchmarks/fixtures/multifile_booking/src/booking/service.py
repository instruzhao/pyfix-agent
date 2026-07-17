from src.booking.intervals import half_open_overlap


def bookings_overlap(first_start, first_end, second_start, second_end):
    return half_open_overlap(first_start, first_end, second_start, second_end)
