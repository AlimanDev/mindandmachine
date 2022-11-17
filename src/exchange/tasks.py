from datetime import datetime, timedelta, date
import logging
from typing import Optional, Union

from src.celery.celery import app
from django.conf import settings
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
def run_import_job(
    self,
    import_job_id,
    date_from: Optional[Union[date, str]] = None,
    date_to: Optional[Union[date, str]] = None,
):
    import_job = ImportJob.objects.get(id=import_job_id)

    kwrgs = {}
    if (date_from is not None) and (date_to is not None):
        to_upd = {'date_from': date_from, 'date_to': date_to}
        for k, v in to_upd.items():
            if isinstance(v, str):
                to_upd[k] = datetime.strptime(v, settings.QOS_DATE_FORMAT).date()
        kwrgs.update(to_upd)
    
    try:
        return import_job.run(**kwrgs)
    except Exception as e:
        import_logger.exception(f'import data exception, import_job_id={import_job_id}.')
        retry(self, import_job, e)


@app.task(bind=True)
def run_export_job(self, export_job_id):
    export_job = ExportJob.objects.get(id=export_job_id)
    try:
        return export_job.run()
    except Exception as e:
        export_logger.exception(f'export_job_id={export_job_id}.')
        retry(self, export_job, e)
