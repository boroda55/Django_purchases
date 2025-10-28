from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import User

# Импортируйте ваш сигнал (если он определен в models.py)
from models import new_user_registered

@receiver(new_user_registered)
def send_confirmation_email(sender, user_id, **kwargs):
    user = User.objects.get(id=user_id)
    send_mail(
        'Добро пожаловать в наш магазин!',
        f'Здравствуйте, {user.username}! Добро пожаловать в наш магазин.',
        settings.EMAIL_HOST_USER,  # От кого
        [user.email],  # Кому
        fail_silently=False,
    )