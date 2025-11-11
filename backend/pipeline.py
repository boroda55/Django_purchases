from django.contrib.auth import get_user_model

User = get_user_model()


def set_user_type(strategy, details, user=None, *args, **kwargs):
    """
    Кастомный pipeline для установки типа пользователя при социальной аутентификации
    """
    if user and not user.type:
        user.type = 'buyer'  # по умолчанию покупатель
        user.is_active = True  # автоматически активируем аккаунт при Google auth
        user.save()

    return {'user': user}