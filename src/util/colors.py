from collections import namedtuple
from functools import lru_cache

from PIL import ImageColor

RGBColor = namedtuple('RGBColor', field_names=('R', 'G', 'B'))


@lru_cache()
def get_contrast_color(html_color: str):
    rgb_tuple = ImageColor.getcolor(html_color, "RGB")
    rgb_color = RGBColor(*rgb_tuple)

    luminance = (0.299 * rgb_color.R + 0.587 * rgb_color.G + 0.114 * rgb_color.B) / 255

    if luminance > 0.5:
        d = 0
    else:
        d = 255

    return '#%02x%02x%02x' % (d, d, d)
