import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from model_bakery import baker
from backend.models import ConfirmEmailToken

User = get_user_model()


class TestUserLogin:
    @pytest.mark.django_db
    def test_login_success(self, api_client, buyer_user):
        """Тест успешного входа пользователя"""
        data = {
            'email': 'buyer@test.com',
            'password': 'testpass123'
        }
        response = api_client.post('/login/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert 'Message' in response.json()

    @pytest.mark.django_db
    def test_login_wrong_password(self, api_client, buyer_user):
        """Тест входа с неправильным паролем"""
        data = {
            'email': 'buyer@test.com',
            'password': 'wrongpassword'
        }
        response = api_client.post('/login/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_login_missing_credentials(self, api_client):
        """Тест входа без обязательных полей"""
        data = {'email': 'test@test.com'}
        response = api_client.post('/login/', data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()['Status'] == False


class TestUserRegister:
    @pytest.mark.django_db
    def test_register_success(self, api_client):
        """Тест успешной регистрации пользователя"""
        data = {
            'email': 'newuser@test.com',
            'username': 'newuser',
            'password': 'testpass123'
        }
        response = api_client.post('/register/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert User.objects.filter(email='newuser@test.com').exists()

    @pytest.mark.django_db
    def test_register_duplicate_email(self, api_client, buyer_user):
        """Тест регистрации с существующим email"""
        data = {
            'email': 'buyer@test.com',
            'username': 'newuser2',
            'password': 'testpass123'
        }
        response = api_client.post('/register/', data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_register_missing_fields(self, api_client):
        """Тест регистрации без обязательных полей"""
        data = {
            'email': 'test@test.com',
            'password': 'testpass123'
        }
        response = api_client.post('/register/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_register_shop_with_company(self, api_client):
        """Тест регистрации магазина с указанием компании"""
        data = {
            'email': 'shop2@test.com',
            'username': 'shop2',
            'password': 'testpass123',
            'company': 'Test Company'
        }
        response = api_client.post('/register/', data)
        assert response.status_code == status.HTTP_200_OK
        user = User.objects.get(email='shop2@test.com')
        assert user.type == 'shop'
        assert user.company == 'Test Company'


class TestUserActivation:
    @pytest.mark.django_db
    def test_activation_success(self, api_client, buyer_user):
        """Тест успешной активации пользователя"""
        # Сначала деактивируем пользователя
        buyer_user.is_active = False
        buyer_user.save()

        token = baker.make(ConfirmEmailToken, user=buyer_user)

        data = {
            'email': 'buyer@test.com',
            'key': token.key
        }
        response = api_client.post('/useractivation/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

        buyer_user.refresh_from_db()
        assert buyer_user.is_active == True

    @pytest.mark.django_db
    def test_activation_wrong_token(self, api_client, buyer_user):
        """Тест активации с неправильным токеном"""
        # Сначала деактивируем пользователя
        buyer_user.is_active = False
        buyer_user.save()

        data = {
            'email': 'buyer@test.com',
            'key': 'wrong_token'
        }
        response = api_client.post('/useractivation/', data)
        # Исправляем ожидаемый статус код на 404
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False

    @pytest.mark.django_db
    def test_activation_missing_fields(self, api_client):
        """Тест активации без обязательных полей"""
        data = {'email': 'test@test.com'}
        response = api_client.post('/useractivation/', data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()['Status'] == False