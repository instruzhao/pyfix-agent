def half_open_overlap(first_start, first_end, second_start, second_end):
    return first_start <= second_end and second_start <= first_end
