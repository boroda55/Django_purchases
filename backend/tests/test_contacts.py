import pytest
from rest_framework import status
from model_bakery import baker
from backend.models import Contact, Address


class TestContactListView:
    @pytest.mark.django_db
    def test_get_contacts_empty(self, authenticated_buyer_client):
        """Тест получения пустого списка контактов"""
        response = authenticated_buyer_client.get('/contacts/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert len(response.json()['Contacts']) == 0

    @pytest.mark.django_db
    def test_get_contacts_with_data(self, authenticated_buyer_client):
        """Тест получения списка контактов с данными"""
        user = authenticated_buyer_client.handler._force_user
        address = baker.make(Address, city='Test City', street='Test Street')
        baker.make(
            Contact,
            user=user,
            address=address,
            phone='+79999999999'
        )

        response = authenticated_buyer_client.get('/contacts/')
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert len(response.json()['Contacts']) == 1


class TestAddContactView:
    @pytest.mark.django_db
    def test_add_contact_success(self, authenticated_buyer_client):
        """Тест успешного добавления контакта"""
        data = {
            'phone': '+79999999999',
            'city': 'Test City',
            'street': 'Test Street',
            'house': '10'
        }
        response = authenticated_buyer_client.post('/contacts/add/', data)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert Contact.objects.filter(user=authenticated_buyer_client.handler._force_user).exists()

    @pytest.mark.django_db
    def test_add_contact_missing_required_fields(self, authenticated_buyer_client):
        """Тест добавления контакта без обязательных полей"""
        data = {
            'phone': '+79999999999'
            # missing city and street
        }
        response = authenticated_buyer_client.post('/contacts/add/', data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()['Status'] == False


class TestUpdateContactView:
    @pytest.mark.django_db
    def test_update_contact_success(self, authenticated_buyer_client):
        """Тест успешного обновления контакта"""
        user = authenticated_buyer_client.handler._force_user
        address = baker.make(Address, city='Old City', street='Old Street')
        contact = baker.make(
            Contact,
            user=user,
            address=address,
            phone='+79999999999'
        )

        data = {
            'contact_id': contact.id,
            'city': 'New City',
            'street': 'New Street',
            'phone': '+78888888888'
        }
        response = authenticated_buyer_client.put('/contacts/update/', data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

        contact.refresh_from_db()
        address.refresh_from_db()

        assert address.city == 'New City'
        assert address.street == 'New Street'
        assert contact.phone == '+78888888888'

    @pytest.mark.django_db
    def test_update_contact_not_found(self, authenticated_buyer_client):
        """Тест обновления несуществующего контакта"""
        data = {
            'contact_id': 999,
            'city': 'New City'
        }
        response = authenticated_buyer_client.put('/contacts/update/', data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False


class TestDeleteContactView:
    @pytest.mark.django_db
    def test_delete_contact_success(self, authenticated_buyer_client):
        """Тест успешного удаления контакта"""
        user = authenticated_buyer_client.handler._force_user
        address = baker.make(Address)
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')

        data = {'contact_id': contact.id}
        response = authenticated_buyer_client.delete('/contacts/delete/', data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True
        assert not Contact.objects.filter(id=contact.id).exists()

    @pytest.mark.django_db
    def test_delete_contact_not_found(self, authenticated_buyer_client):
        """Тест удаления несуществующего контакта"""
        data = {'contact_id': 999}
        response = authenticated_buyer_client.delete('/contacts/delete/', data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False


class TestSetDefaultContactView:
    @pytest.mark.django_db
    def test_set_default_contact_success(self, authenticated_buyer_client):
        """Тест успешной установки контакта по умолчанию"""
        user = authenticated_buyer_client.handler._force_user
        address = baker.make(Address)
        contact = baker.make(Contact, user=user, address=address, phone='+79999999999')

        data = {'contact_id': contact.id}
        response = authenticated_buyer_client.post('/contacts/set-default/', data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()['Status'] == True

    @pytest.mark.django_db
    def test_set_default_contact_not_found(self, authenticated_buyer_client):
        """Тест установки несуществующего контакта по умолчанию"""
        data = {'contact_id': 999}
        response = authenticated_buyer_client.post('/contacts/set-default/', data)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()['Status'] == False