""""
Celery Client
"""
from celery import Celery
from ska_utils import AppConfig
from configs import (TA_CELERY_CONFIG)

app_config = AppConfig()

celery_url = app_config.props.get(
    TA_CELERY_CONFIG.env_name,
    TA_CELERY_CONFIG.default_value
)
app = Celery(
    "content_update",
    broker=celery_url,
    backend=celery_url
)