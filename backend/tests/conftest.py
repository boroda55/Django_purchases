import pytest
import django
from django.conf import settings

# Настройка Django
if not settings.configured:
    django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from model_bakery import baker
from backend.models import Shop, Category, Product, ProductInfo  # Добавьте импорт моделей

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def buyer_user():
    # Создаем пользователя с правильным паролем
    user = User.objects.create_user(
        email='buyer@test.com',
        username='buyer',
        password='testpass123',
        is_active=True,
        type='buyer'
    )
    return user

@pytest.fixture
def shop_user():
    user = User.objects.create_user(
        email='shop@test.com',
        username='shop',
        password='testpass123',
        is_active=True,
        type='shop'
    )
    return user

@pytest.fixture
def shop(shop_user):
    return baker.make(Shop, name='Test Shop', user=shop_user)

@pytest.fixture
def category():
    return baker.make(Category, name='Test Category')

@pytest.fixture
def product(category):
    return baker.make(Product, name='Test Product', category=category)

@pytest.fixture
def product_info(shop, product):
    return baker.make(
        ProductInfo,
        product=product,
        shop=shop,
        name='Test Product Info',
        price=1000,
        quantity=10,
        external_id=1
    )

@pytest.fixture
def authenticated_buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client

@pytest.fixture
def authenticated_shop_client(shop_user):
    client = APIClient()
    client.force_authenticate(user=shop_user)
    return client