from celery import Celery
celery_app = Celery(
    "content_update",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
)

celery_app.autodiscover_tasks(["content_update"])
