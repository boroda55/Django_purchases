from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django_rest_passwordreset.tokens import get_token_generator

STATE_CHOICES = (
    ('basket', 'Статус корзины'),
    ('new', 'Новый'),
    ('confirmed', 'Подтвержден'),
    ('assembled', 'Собран'),
    ('sent', 'Отправлен'),
    ('delivered', 'Доставлен'),
    ('canceled', 'Отменен'),
)

USER_TYPE_CHOICES = (
    ('shop', 'Магазин'),
    ('buyer', 'Покупатель'),

)

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
    """
    Модель Магазинов
    """
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

    class Category(models.Model):
        """
        Модель Категорий
        """
        name = models.CharField('Название', max_length=100)
        shops = models.ManyToManyField(Shop, verbose_name='Магазины', related_name='shop_categories', blank=True)

        class Meta:
            verbose_name = 'Категория'
            verbose_name_plural = 'Список категорий'

        def __str__(self):
            return self.name


class Product(models.Model):
    """
    Модель Продуктов
    """
    name = models.CharField(max_length=80, verbose_name='Название')
    category = models.ForeignKey(Category, verbose_name='Категория', related_name='products', blank=True,
                                 on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = "Список продуктов"
        ordering = ('-name',)

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    """
    Модель Информации о продуктах
    """

    external_id = models.PositiveIntegerField(verbose_name='Внешний ИД магазина')
    shop = models.ForeignKey(Shop, verbose_name='Магазин',
                             related_name='shop_product_infos', on_delete=models.CASCADE)

    name = models.CharField(max_length=80,
                            verbose_name='Название продукта в магазине')
    model = models.CharField(max_length=80,verbose_name='Модель',blank=True)
    quantity = models.PositiveIntegerField(verbose_name='Количество')
    price = models.PositiveIntegerField(verbose_name='Цена')

    class Meta:
        verbose_name = 'Информация о продукте'
        verbose_name_plural = "Информационный список о продуктах"
        constraints = [
            models.UniqueConstraint(
                fields=['shop', 'external_id'],
                name='unique_shop_product'
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.shop.name})"


class Parameter(models.Model):
    """
    Модель параметров
    """
    name = models.CharField(max_length=40, verbose_name='Название')

    class Meta:
        verbose_name = 'Имя параметра'
        verbose_name_plural = "Список имен параметров"
        ordering = ('-name',)

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    """
    Модель информации о продуктах
    """
    product_info = models.ForeignKey(ProductInfo, verbose_name='Информация о продукте',
                                     related_name='product_parameters', blank=True,
                                     on_delete=models.CASCADE)
    parameter = models.ForeignKey(Parameter, verbose_name='Параметр', related_name='product_parameters', blank=True,
                                  on_delete=models.CASCADE)
    value = models.CharField(verbose_name='Значение', max_length=100)

    class Meta:
        verbose_name = 'Параметр'
        verbose_name_plural = "Список параметров"
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'parameter'], name='unique_product_parameter'),
        ]


class Address(models.Model):
    """
    Модель адресов пользователей
    """
    city = models.CharField(max_length=50, verbose_name='Город')
    street = models.CharField(max_length=100, verbose_name='Улица')
    house = models.CharField(max_length=15, verbose_name='Дом', blank=True)
    structure = models.CharField(max_length=15, verbose_name='Корпус', blank=True)
    building = models.CharField(max_length=15, verbose_name='Строение', blank=True)
    apartment = models.CharField(max_length=15, verbose_name='Квартира', blank=True)

    class Meta:
        verbose_name = 'Адрес'
        verbose_name_plural = 'Список адресов'

    def __str__(self):
        return f'{self.city} {self.street} {self.house} {self.structure} {self.building}'

class Contact(models.Model):
    """
    Модель контакты пользователей
    """
    user = models.ForeignKey(User, verbose_name='Пользователь',
                             related_name='contacts', blank=True,
                             on_delete=models.CASCADE)
    address = models.ForeignKey(Address, verbose_name='Адрес',
                                related_name='address_contacts', on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, verbose_name='Телефон')

    class Meta:
        verbose_name = 'Контакты пользователя'
        verbose_name_plural = "Список контактов пользователя"

    def __str__(self):
        return f'{self.user.email} - {self.phone}'



class Order(models.Model):
    """
    Модель заказов
    """
    user = models.ForeignKey(User, verbose_name='Пользователь',
                             related_name='orders', blank=True,
                             on_delete=models.CASCADE)
    dt = models.DateTimeField(auto_now_add=True)
    state = models.CharField(verbose_name='Статус', choices=STATE_CHOICES, max_length=15)
    contact = models.ForeignKey(Contact, verbose_name='Контакт',
                                blank=True, null=True,
                                on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = "Список заказ"
        ordering = ('-dt',)

    def __str__(self):
        return str(self.dt)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name='Заказ', related_name='ordered_items', blank=True,
                              on_delete=models.CASCADE)

    product_info = models.ForeignKey(ProductInfo, verbose_name='Информация о продукте',
                                     related_name='ordered_items',
                                     blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(verbose_name='Количество')

    class Meta:
        verbose_name = 'Заказанная позиция'
        verbose_name_plural = "Список заказанных позиций"
        constraints = [
            models.UniqueConstraint(fields=['order_id', 'product_info'], name='unique_order_item'),
        ]


class ConfirmEmailToken(models.Model):
    """
    Модель Токены для Email
    """
    class Meta:
        verbose_name = 'Токен подтверждения Email'
        verbose_name_plural = 'Токены подтверждения Email'

    @staticmethod
    def generate_key():
        return get_token_generator().generate_token()

    user = models.ForeignKey(User, related_name='confirm_email_tokens',
                             on_delete=models.CASCADE, verbose_name="Пользователь, связанный с токеном")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата генерации токена")

    # Key field, though it is not the primary key of the model
    key = models.CharField("Key", max_length=64, db_index=True,unique=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return f"Токен для сброса пароля пользователя {self.user}"







