from celery import Celery
from celery.schedules import crontab

app = Celery('purchases')

app.conf.beat_schedule = {
    'cleanup-expired-tokens-daily': {
        'task': 'backend.tasks.cleanup_expired_tokens',
        'schedule': crontab(hour=3, minute=0),  # Ежедневно в 3:00
    },
    'cleanup-orphaned-images-weekly': {
        'task': 'backend.tasks.cleanup_orphaned_images',
        'schedule': crontab(hour=4, minute=0, day_of_week=1),  # Каждый понедельник в 4:00
    },
}