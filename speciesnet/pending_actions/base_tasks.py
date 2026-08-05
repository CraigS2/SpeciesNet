from celery import Task


class RetriableTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 3

    # Keep queue names explicit so a future sync queue can be introduced cleanly.
    queue = 'emails'
