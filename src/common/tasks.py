from src.adapters.celery.celery import app
from src.common import images
from django.apps import apps

@app.task
def compress_images(app_label: str, model_name: str, **kwargs) -> dict:
    Model = apps.get_model(app_label, model_name)
    queryset = Model.objects.filter(**kwargs)
    return images.compress_images_on_queryset(queryset)
