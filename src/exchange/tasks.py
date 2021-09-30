import logging

from src.celery.celery import app
from .models import (
    ImportJob,
    ExportJob,
)

import_logger = logging.getLogger('import_jobs')
export_logger = logging.getLogger('export_jobs')


@app.task
def run_import_job(import_job_id):
    import_job = ImportJob.objects.get(id=import_job_id)
    try:
        return import_job.run()
    except Exception as e:
        import_logger.exception(f'import_job_id={import_job_id}.')
        raise e


@app.task
def run_export_job(export_job_id):
    export_job = ExportJob.objects.get(id=export_job_id)
    try:
        return export_job.run()
    except Exception as e:
        export_logger.exception(f'export_job_id={export_job_id}.')
        raise e
