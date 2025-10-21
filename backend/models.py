from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models


class UserManager(BaseUserManager):
    """
    Класс для создания пользователями
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Кастомная функция создания и сохранения пользователя с помощью email и пароля
        :param email:
        :param password:
        :param extra_fields:
        """
        if not email:
            raise ValueError('Не указан email')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Модель пользователей
    """
    TYPE_CHOICES = (
        ('buyer', 'Покупатель'),
        ('shop', 'Магазин')
    )

    USERNAME_FIELD = 'email'
    objects = UserManager()

    email = models.EmailField('Адрес электронной почты')
    company = models.CharField('Компания', blank=True, max_length=100)
    username_validator = UnicodeUsernameValidator()
    username = models.CharField('Имя', max_length=150, validators=[username_validator])
    is_active = models.BooleanField('Активация', default=False)
    type = models.CharField('Тип пользователя',default='buyer' , max_length=5, choices=TYPE_CHOICES)

    def __str__(self):
        return f'{self.email}'

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Список пользователей'
        ordering = ('email',)


class Shop(models.Model):
    name = models.CharField('Название магазина', max_length=100)
    url = models.URLField('Ссылка', null=True, blank=True)
    user = models.OneToOneField(User, verbose_name='Пользователи',
                                blank=True, null=True,
                                on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Список магазинов'

    def __str__(self):
        return self.name









