from datetime import datetime, timedelta
import logging

from src.celery.celery import app
from .models import (
    ImportJob,
    ExportJob,
)

import_logger = logging.getLogger('import_jobs')
export_logger = logging.getLogger('export_jobs')

def retry(task, job, e):
    retries = job.retries
    if retries:
        task.retry(
            max_retries=max(map(int, retries.keys())),
            eta=datetime.now() + timedelta(seconds=retries.get(str(task.request.retries + 1)) or 3600),
            exc=e,
        )
    else:
        raise e

@app.task(bind=True)
def run_import_job(self, import_job_id):
    import_job = ImportJob.objects.get(id=import_job_id)
    try:
        return import_job.run()
    except Exception as e:
        import_logger.exception(f'import_job_id={import_job_id}.')
        retry(self, import_job, e)


@app.task(bind=True)
def run_export_job(self, export_job_id):
    export_job = ExportJob.objects.get(id=export_job_id)
    try:
        return export_job.run()
    except Exception as e:
        export_logger.exception(f'export_job_id={export_job_id}.')
        retry(self, export_job, e)
