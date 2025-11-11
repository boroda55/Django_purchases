import pytest
from rest_framework import status
from model_bakery import baker
from backend.models import Order, OrderItem, ProductInfo, Shop, Category, Product


class TestCartView:
    @pytest.mark.django_db
    def test_get_empty_cart(self, authenticated_buyer_client):
        """Тест получения пустой корзины"""
        response = authenticated_buyer_client.get('/cart/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

    @pytest.mark.django_db
    def test_get_cart_with_items(self, authenticated_buyer_client):
        """Тест получения корзины с товарами"""
        user = authenticated_buyer_client.handler._force_user

        # Создаем тестовые данные
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=10,
            price=1000
        )

        # Создаем корзину с товаром
        cart = baker.make(Order, user=user, state='basket')
        baker.make(OrderItem, order=cart, product_info=product_info, quantity=2)

        response = authenticated_buyer_client.get('/cart/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert 'Cart' in response.json()


class TestAddToCartView:
    @pytest.mark.django_db
    def test_add_to_cart_success(self, authenticated_buyer_client):
        """Тест успешного добавления товара в корзину"""
        # Создаем тестовые данные
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=10,
            price=1000
        )

        data = {
            'product_info_id': product_info.id,
            'quantity': 1
        }
        response = authenticated_buyer_client.post('/cart/add/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

    @pytest.mark.django_db
    def test_add_to_cart_missing_fields(self, authenticated_buyer_client):
        """Тест добавления в корзину без обязательных полей"""
        data = {'product_info_id': 1}
        response = authenticated_buyer_client.post('/cart/add/', data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_add_to_cart_insufficient_stock(self, authenticated_buyer_client):
        """Тест добавления в корзину при недостаточном количестве"""
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=1,
            price=1000
        )

        data = {
            'product_info_id': product_info.id,
            'quantity': 5
        }
        response = authenticated_buyer_client.post('/cart/add/', data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False


class TestRemoveFromCartView:
    @pytest.mark.django_db
    def test_remove_from_cart_success(self, authenticated_buyer_client):
        """Тест успешного удаления товара из корзины"""
        user = authenticated_buyer_client.handler._force_user

        # Создаем тестовые данные
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=10,
            price=1000
        )

        # Создаем корзину с товаром
        cart = baker.make(Order, user=user, state='basket')
        order_item = baker.make(OrderItem, order=cart, product_info=product_info, quantity=1)

        data = {'item_id': order_item.id}
        response = authenticated_buyer_client.delete('/cart/remove/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

    @pytest.mark.django_db
    def test_remove_from_cart_missing_item_id(self, authenticated_buyer_client):
        """Тест удаления из корзины без указания item_id"""
        response = authenticated_buyer_client.delete('/cart/remove/', {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()['Status'] == False


class TestUpdateCartItemView:
    @pytest.mark.django_db
    def test_update_cart_item_success(self, authenticated_buyer_client):
        """Тест успешного обновления количества товара"""
        user = authenticated_buyer_client.handler._force_user

        # Создаем тестовые данные
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=10,
            price=1000
        )

        # Создаем корзину с товаром
        cart = baker.make(Order, user=user, state='basket')
        order_item = baker.make(OrderItem, order=cart, product_info=product_info, quantity=1)

        data = {
            'item_id': order_item.id,
            'quantity': 3
        }
        response = authenticated_buyer_client.put('/cart/update/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True


class TestClearCartView:
    @pytest.mark.django_db
    def test_clear_cart_success(self, authenticated_buyer_client):
        """Тест успешной очистки корзины"""
        user = authenticated_buyer_client.handler._force_user

        # Создаем тестовые данные
        shop = baker.make(Shop, name='Test Shop')
        category = baker.make(Category, name='Test Category')
        product = baker.make(Product, name='Test Product', category=category)
        product_info = baker.make(
            ProductInfo,
            product=product,
            shop=shop,
            quantity=10,
            price=1000
        )

        # Создаем корзину с товаром
        cart = baker.make(Order, user=user, state='basket')
        baker.make(OrderItem, order=cart, product_info=product_info, quantity=2)

        response = authenticated_buyer_client.delete('/cart/clear/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True