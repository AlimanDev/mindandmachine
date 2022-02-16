from datetime import datetime, timedelta
import logging

from src.celery.celery import app
from .models import (
    ImportJob,
    ExportJob,
)

import_logger = logging.getLogger('import_jobs')
export_logger = logging.getLogger('export_jobs')

def retry(task, job, attempt):
    retries = job.retries
    if retries and attempt <= max(map(int, retries.keys())):
        task.apply_async(
            args=[job.id], 
            kwargs={'attempt': attempt + 1}, 
            eta=datetime.now() + timedelta(seconds=retries.get(str(attempt)) or 3600),
        )

@app.task
def run_import_job(import_job_id, attempt=1):
    import_job = ImportJob.objects.get(id=import_job_id)
    try:
        return import_job.run()
    except Exception as e:
        import_logger.exception(f'import_job_id={import_job_id}.')
        retry(run_import_job, import_job, attempt)
        raise e


@app.task
def run_export_job(export_job_id, attempt=1):
    export_job = ExportJob.objects.get(id=export_job_id)
    try:
        return export_job.run()
    except Exception as e:
        export_logger.exception(f'export_job_id={export_job_id}.')
        retry(run_export_job, export_job, attempt)
        raise e
