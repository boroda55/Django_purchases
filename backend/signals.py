from venv import create

from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import User, ConfirmEmailToken

# Импортируйте ваш сигнал (если он определен в models.py)
from backend.models import new_user_registered

@receiver(new_user_registered)
def send_confirmation_email(sender, user_id, **kwargs):
    user = User.objects.get(id=user_id)
    token, created = ConfirmEmailToken.objects.get_or_create(user=user)
    if created:
        send_mail(
            'Подтверждение регистрации',
            f'''Здравствуйте, {user.username}!
                Благодарим за регистрацию в нашем магазине!
                Ваш токен для подтверждения email: {token.key}
                Для активации аккаунта используйте этот токен.
                Токен действует 2 часа''',
            settings.EMAIL_HOST_USER,
            [user.email],
            fail_silently=False,
        )

