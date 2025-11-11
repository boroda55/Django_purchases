
import pytest
from rest_framework import status
from model_bakery import baker
from backend.models import Order, Contact, Address, OrderItem, ProductInfo, Shop, Category, Product


class TestOrderListView:
    @pytest.mark.django_db
    def test_get_orders_empty(self, authenticated_buyer_client):
        """Тест получения пустого списка заказов"""
        response = authenticated_buyer_client.get('/orders/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert len(response.json()['Orders']) == 0

    @pytest.mark.django_db
    def test_get_orders_with_data(self, authenticated_buyer_client):
        """Тест получения списка заказов с данными"""
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

        # Создаем завершенный заказ
        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')
        order = baker.make(
            Order,
            user=user,
            state='new',
            contact=contact
        )
        baker.make(OrderItem, order=order, product_info=product_info, quantity=1)

        response = authenticated_buyer_client.get('/orders/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert len(response.json()['Orders']) == 1


class TestConfirmOrderView:
    @pytest.mark.django_db
    def test_confirm_order_success(self, authenticated_buyer_client):
        """Тест успешного подтверждения заказа"""
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

        # Создаем корзину и контакт
        cart = baker.make(Order, user=user, state='basket')
        baker.make(OrderItem, order=cart, product_info=product_info, quantity=1)

        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')

        data = {'contact_id': contact.id}
        response = authenticated_buyer_client.post('/order/confirm/', data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

        # Проверяем что статус заказа изменился
        cart.refresh_from_db()
        assert cart.state == 'new'

    @pytest.mark.django_db
    def test_confirm_order_empty_cart(self, authenticated_buyer_client):
        """Тест подтверждения пустой корзины"""
        user = authenticated_buyer_client.handler._force_user

        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')

        data = {'contact_id': contact.id}
        response = authenticated_buyer_client.post('/order/confirm/', data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False


class TestOrderDetailView:
    @pytest.mark.django_db
    def test_order_detail_success(self, authenticated_buyer_client):
        """Тест успешного получения деталей заказа"""
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

        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')
        order = baker.make(
            Order,
            user=user,
            state='new',
            contact=contact
        )
        baker.make(OrderItem, order=order, product_info=product_info, quantity=2)

        response = authenticated_buyer_client.get(f'/order/{order.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert 'Order' in response.json()

    @pytest.mark.django_db
    def test_order_detail_not_found(self, authenticated_buyer_client):
        """Тест получения несуществующего заказа"""
        response = authenticated_buyer_client.get('/order/999/')
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False


class TestCancelOrderView:
    @pytest.mark.django_db
    def test_cancel_order_success(self, authenticated_buyer_client):
        """Тест успешной отмены заказа"""
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

        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')
        order = baker.make(
            Order,
            user=user,
            state='new',
            contact=contact
        )
        baker.make(OrderItem, order=order, product_info=product_info, quantity=1)

        initial_quantity = product_info.quantity

        data = {'order_id': order.id}
        response = authenticated_buyer_client.post('/order/cancel/', data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

        order.refresh_from_db()
        assert order.state == 'canceled'

        # Проверяем что товары вернулись на склад
        product_info.refresh_from_db()
        assert product_info.quantity == initial_quantity + 1

    @pytest.mark.django_db
    def test_cancel_order_not_found(self, authenticated_buyer_client):
        """Тест отмены несуществующего заказа"""
        data = {'order_id': 999}
        response = authenticated_buyer_client.post('/order/cancel/', data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_cancel_order_already_canceled(self, authenticated_buyer_client):
        """Тест отмены уже отмененного заказа"""
        user = authenticated_buyer_client.handler._force_user

        address = baker.make(Address, city='Test City', street='Test Street')
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')
        order = baker.make(
            Order,
            user=user,
            state='canceled',
            contact=contact
        )

        data = {'order_id': order.id}
        response = authenticated_buyer_client.post('/order/cancel/', data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()['Status'] == False