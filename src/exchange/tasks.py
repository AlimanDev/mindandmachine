from src.celery.celery import app
from .models import (
    ImportJob,
    ExportJob,
)


@app.task
def run_import_job(import_job_id):
    import_job = ImportJob.objects.get(id=import_job_id)
    return import_job.run()


@app.task
def run_export_job(export_job_id):
    export_job = ExportJob.objects.get(id=export_job_id)
    return export_job.run()
