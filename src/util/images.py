
from PIL import Image, UnidentifiedImageError
from django.db.models import QuerySet

import logging
logger = logging.getLogger('django')

def compress_images_on_queryset(queryset: QuerySet) -> dict:
    result = {'compressed': 0, 'failed': 0, 'skipped': 0}
    for instance in queryset:
        res = instance.compress_image()
        if res:
            result['compressed'] += 1
        elif res is False:
            result['failed'] += 1
        else: #None
            result['skipped'] += 1
    return result

def compress_image(path: str, quality: int) -> bool:
    """Try to compress an image. Quality: 0-100"""
    try:
        img = Image.open(path)
        img.save(path, quality=quality, optimize=True)
        return True
    except (FileNotFoundError, ValueError, OSError, UnidentifiedImageError) as e:
        logger.warning('Image compression failed', exc_info=e)
        return False
