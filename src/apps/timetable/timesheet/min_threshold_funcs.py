def default_get_min_threshold(norm_hours):
    return round(max(1, 4 * norm_hours/100))
