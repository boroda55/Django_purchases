from django.dispatch import receiver
from .models import new_user_registered
from .tasks import send_confirmation_email

@receiver(new_user_registered)
def handle_new_user_registration(sender, user_id, **kwargs):
    """
    Обработчик сигнала новой регистрации - запускает асинхронную задачу
    """
    # Асинхронная отправка email
    send_confirmation_email.delay(user_id)