from src.booking.service import bookings_overlap


def overlaps(first_start, first_end, second_start, second_end):
    return bookings_overlap(first_start, first_end, second_start, second_end)
