from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import User, ConfirmEmailToken, ProductImage
from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.images import ImageFile
import os


@shared_task(bind=True, max_retries=3)
def send_confirmation_email(self, user_id):
    """
    Асинхронная задача для отправки email подтверждения
    """
    try:
        user = User.objects.get(id=user_id)

        # Удаляем старые токены пользователя
        ConfirmEmailToken.objects.filter(user=user).delete()

        # Создаем новый токен
        token = ConfirmEmailToken.objects.create(user=user)

        subject = 'Подтверждение регистрации'
        message = f'''
        Здравствуйте, {user.username}!

        Благодарим за регистрацию в нашем магазине!
        Ваш токен для подтверждения email: {token.key}

        Для активации аккаунта используйте этот токен в разделе подтверждения email.
        Токен действует 2 часа.

        С уважением,
        Команда магазина
        '''

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return f"Email отправлен пользователю {user.email}"

    except User.DoesNotExist:
        self.retry(countdown=60, max_retries=3)
        return f"Пользователь с ID {user_id} не найден, повторная попытка..."
    except Exception as e:
        self.retry(countdown=60, max_retries=3)
        return f"Ошибка при отправке email: {str(e)}"


@shared_task
def cleanup_expired_tokens():
    """
    Задача для очистки просроченных токенов
    """
    expired_time = timezone.now() - timedelta(hours=2)
    expired_tokens = ConfirmEmailToken.objects.filter(created_at__lt=expired_time)
    count = expired_tokens.count()
    expired_tokens.delete()
    return f"Удалено {count} просроченных токенов"


@shared_task(bind=True, max_retries=3)
def generate_avatar_thumbnails(self, user_id):
    """
    Асинхронная задача для генерации миниатюр аватара
    """
    try:
        user = User.objects.get(id=user_id)

        if not user.avatar:
            return f"Пользователь {user_id} не имеет аватара"

        # Генерация миниатюры
        from io import BytesIO
        from PIL import Image

        # Открываем оригинальное изображение
        img = Image.open(user.avatar.path)

        # Создаем миниатюру 50x50
        img.thumbnail((50, 50), Image.Resampling.LANCZOS)

        # Конвертируем в RGB если нужно
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Сохраняем в памяти
        thumb_io = BytesIO()
        img.save(thumb_io, format='JPEG', quality=70)

        # Сохраняем миниатюру
        thumb_file = ImageFile(thumb_io, name=f'avatar_thumb_{user.id}.jpg')
        user.avatar_thumbnail.save(thumb_file.name, thumb_file, save=True)

        return f"Миниатюра аватара сгенерирована для пользователя {user.email}"

    except User.DoesNotExist:
        self.retry(countdown=60, max_retries=3)
        return f"Пользователь с ID {user_id} не найден"
    except Exception as e:
        self.retry(countdown=60, max_retries=3)
        return f"Ошибка при генерации миниатюры аватара: {str(e)}"


@shared_task(bind=True, max_retries=3)
def generate_product_thumbnail(self, product_image_id):
    """
    Асинхронная задача для генерации миниатюр изображений товаров
    """
    try:
        product_image = ProductImage.objects.get(id=product_image_id)

        if not product_image.image:
            return f"Изображение товара {product_image_id} не найдено"

        # Открываем оригинальное изображение
        img = Image.open(product_image.image.path)

        # Создаем миниатюру 150x150 с обрезкой
        thumbnail_size = (150, 150)

        # Вычисляем размеры для обрезки
        width, height = img.size
        if width > height:
            # Горизонтальное изображение
            new_height = height
            new_width = int(height * thumbnail_size[0] / thumbnail_size[1])
        else:
            # Вертикальное изображение
            new_width = width
            new_height = int(width * thumbnail_size[1] / thumbnail_size[0])

        # Обрезаем и изменяем размер
        img = ImageOps.fit(img, thumbnail_size, Image.Resampling.LANCZOS)

        # Конвертируем в RGB если нужно
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background

        # Сохраняем в памяти
        thumb_io = BytesIO()
        img.save(thumb_io, format='JPEG', quality=75)

        # Сохраняем миниатюру
        thumb_file = ImageFile(thumb_io, name=f'product_thumb_{product_image.id}.jpg')
        product_image.thumbnail.save(thumb_file.name, thumb_file, save=True)

        return f"Миниатюра сгенерирована для изображения товара {product_image_id}"

    except ProductImage.DoesNotExist:
        self.retry(countdown=60, max_retries=3)
        return f"Изображение товара с ID {product_image_id} не найдено"
    except Exception as e:
        self.retry(countdown=60, max_retries=3)
        return f"Ошибка при генерации миниатюры товара: {str(e)}"


@shared_task
def optimize_product_image(product_image_id):
    """
    Задача для оптимизации изображений товаров
    """
    try:
        product_image = ProductImage.objects.get(id=product_image_id)

        if not product_image.image:
            return f"Изображение товара {product_image_id} не найдено"

        # Открываем изображение
        img = Image.open(product_image.image.path)

        # Оптимизируем (уменьшаем качество если нужно)
        if img.size[0] > 1200 or img.size[1] > 1200:
            img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)

        # Сохраняем с оптимизацией
        img.save(product_image.image.path, format='JPEG', quality=85, optimize=True)

        return f"Изображение товара {product_image_id} оптимизировано"

    except Exception as e:
        return f"Ошибка при оптимизации изображения: {str(e)}"


@shared_task
def cleanup_orphaned_images():
    """
    Задача для очистки orphaned изображений
    """
    try:
        from django.utils import timezone
        from datetime import timedelta

        # Находим изображения без привязки к товарам старше 1 дня
        cutoff_date = timezone.now() - timedelta(days=1)
        orphaned_images = ProductImage.objects.filter(
            product__isnull=True,
            created_at__lt=cutoff_date
        )

        count = orphaned_images.count()

        # Удаляем файлы и записи
        for image in orphaned_images:
            if image.image:
                image.image.delete(save=False)
            if image.thumbnail:
                image.thumbnail.delete(save=False)
            image.delete()

        return f"Удалено {count} orphaned изображений"

    except Exception as e:
        return f"Ошибка при очистке изображений: {str(e)}"