

# todo: fix this tresh func!!!
def time2int(tm, minute_step=15, start_h=6):
    diff_h = tm.hour - start_h
    if diff_h < 0:
        diff_h += 24
    return int(tm * 60 + tm.minute) // minute_step