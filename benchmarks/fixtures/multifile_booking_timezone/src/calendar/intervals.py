def half_open_overlap(first_start, first_end, second_start, second_end):
    if first_end <= first_start or second_end <= second_start:
        raise ValueError("end must follow start")
    return first_start <= second_end and second_start <= first_end
