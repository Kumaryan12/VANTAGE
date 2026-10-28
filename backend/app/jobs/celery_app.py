from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

app = Celery("vantage", broker=settings().redis_url, include=["app.jobs.tasks"])
app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_enable_remote_control=False,
    task_time_limit=950,
    task_soft_time_limit=940,
    worker_max_tasks_per_child=10,
    worker_max_memory_per_child=1024 * 1024,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={
        "visibility_timeout": 1200,
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    },
    task_publish_retry=False,
    worker_hijack_root_logger=False,
    task_send_sent_event=False,
    worker_send_task_events=False,
    task_default_queue="research",
    enable_utc=True,
)


@worker_process_init.connect
def dispose_inherited_connections(**kwargs):
    from app.database.session import engine

    engine.dispose(close=False)
