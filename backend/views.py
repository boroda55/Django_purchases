from django.contrib.auth import authenticate
from django.core.validators import URLValidator
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ujson import loads as load_json
from yaml import load as load_yaml, Loader
from requests import get
from django.conf import settings
from rest_framework.authtoken.models import Token
from backend.models import Shop, Category, ProductInfo, Product, ProductParameter, Parameter, User, new_user_registered, \
    ConfirmEmailToken, Order, OrderItem, Contact, Address
from datetime import timedelta
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated

def status_response(status: bool, message: str = ""):
    """
    Создает стандартизированный JSON ответ

    Args:
        status: Статус операции (True/False)
        message: Сообщение (опционально)
    """
    response = {'Status': status}
    if message:  # Добавляем сообщение только если оно не пустое
        response['Message'] = message
    return response



class UpdatePrice(APIView):
    """
    Класс для обновления прайса от поставщика
    """
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(status_response(False,
                                                'Требуется войти в систему'), status=403)
        if request.user.type != 'shop':
            return JsonResponse(status_response(False,
                                                'Вход только для магазинов'),status=403)

        url = request.data.get('url')
        if url:
            validate_url = URLValidator()
            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse(status_response(False, str(e)))
            else:
                stream = get(url).content
                data = load_yaml(stream, Loader=Loader)
                shop, _ = Shop.objects.get_or_create(name=data['shop'], user_id=request.user.id)
                for category in data['categories']:
                    category_object, created = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                ProductInfo.objects.filter(shop_id=shop.id).delete()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])
                    product_info = ProductInfo.objects.create(product=product,
                                                              external_id=item['id'],
                                                              name=item['name'],
                                                              model=item.get('model', ''),
                                                              price=item['price'],
                                                              price_rrc=item.get('price_rrc'),
                                                              quantity=item['quantity'],
                                                              shop=shop
                                                              )
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name,)
                        ProductParameter.objects.create(product_info=product_info,
                                                        parameter=parameter_object,
                                                        value=value)

                return JsonResponse(status_response(True))
        return JsonResponse(status_response(False,'Не указаны все необходимые аргументы')
                            )

class UserLogin(APIView):
    """
    Класс для входа пользователя
    """
    def post(self, request, *args, **kwargs):
        if 'email' in request.data and 'password' in request.data:
            user = authenticate(request,
                                username=request.data['email'],
                                password=request.data['password']
                                )
            if user is not None:
                if user.is_active:
                    Token.objects.filter(user=user).delete()
                    token, _ = Token.objects.get_or_create(user=user)
                    return JsonResponse(status_response(True, token.key), status=200)
                else:
                    return JsonResponse(status_response(False, 'Пользователь не активный'), status=403)
            else:
                return JsonResponse(status_response(False, 'Пользователя не существует'), status=401)
        return JsonResponse(status_response(False, 'Не передан email или пароль'), status=400)

class UserRegister(APIView):
    """
       Класс для Регистрации пользователя
    """
    def post(self, request, *args, **kwargs):
        if not {'email', 'username', 'password'}.issubset(request.data):
            return JsonResponse(status_response(False, 'Не указаны все необходимые аргументы'),
                                status=401)
        else:
            if User.objects.filter(email=request.data['email']).exists():
                return JsonResponse(status_response(False, 'Пользователь с таким email уже существует'),
                                    status=403)
            else:
                user_data = {
                    'email': request.data['email'],
                    'password': request.data['password'],
                    'username': request.data['username'],
                    'company': request.data.get('company', '')
                }
                if 'company' in request.data and request.data['company']:
                    user_data['type'] = 'shop'
                else:
                    user_data['type'] = 'buyer'
                user = User.objects.create_user(**user_data)
                new_user_registered.send(sender=self.__class__, user_id=user.id)
                return JsonResponse(status_response(True, 'Пользователь зарегистрирован'), status=200)


class UserActivation(APIView):
    """
        Класс для подтверждения email по ключу с проверкой срока действия
    """
    def post(self, request, *args, **kwargs):
        if not {'email', 'key'}.issubset(request.data):
            return JsonResponse(status_response(False, 'Не указаны все необходимые аргументы'),
                                status=401)

        try:
            user = User.objects.get(email=request.data['email'])
            key = ConfirmEmailToken.objects.get(user=user)


            if (timezone.now() - key.created_at) > timedelta(hours=2):
                key.delete()
                return JsonResponse(
                    status_response(False, 'Ключ просрочен. Запросите новый.'),
                    status=400)

            # Проверка токена
            if key.key != request.data['key']:
                return JsonResponse(
                    status_response(False, f'Неверный ключ для {user.email}'),
                    status=401)

            # Активация пользователя
            user.is_active = True
            user.save()
            key.delete()

            return JsonResponse(
                status_response(True, 'Email подтвержден! Теперь можно войти в систему.'),
                status=200)

        except (User.DoesNotExist, ConfirmEmailToken.DoesNotExist):
            return JsonResponse(
                status_response(False, 'Неверный email или токен'),
                status=404)
        except Exception as e:
            return JsonResponse(
                status_response(False, f'Ошибка: {str(e)}'),
                status=500)

# Нужно добавить класс по запросу нового key
class GettingKeyAgain(APIView):
    """
    Повторное направления ключа активации
    """
    def post(self, request, *args, **kwargs):
        if not {'email', 'password'}.issubset(request.data):
            return JsonResponse(status_response(False, 'Не указаны все необходимые аргументы'),
                                status=401)
        try:
            user = User.objects.get(email=request.data['email'])
            if not user.check_password(request.data['password']):
                return JsonResponse(
                    status_response(False, 'Неверный пароль'),
                    status=401
                )
            if user.is_active:
                return JsonResponse(
                    status_response(False, 'Пользователь уже активирован'),
                    status=400
                )
            ConfirmEmailToken.objects.filter(user=user).delete()
            new_user_registered.send(sender=self.__class__, user_id=user.id)
            return JsonResponse(
                status_response(True, 'На почту направлен новый ключ активации'),
                status=200
            )

        except User.DoesNotExist:
            return JsonResponse(
                status_response(False, 'Пользователь с таким email не найден'),
                status=404
            )
        except Exception as e:
            return JsonResponse(
                status_response(False, f'Ошибка: {str(e)}'),
                status=500
            )


class ProductListView(APIView):
    """
    Класс для получения списка товаров с пагинацией
    """

    def get(self, request, *args, **kwargs):
        try:
            # Базовый queryset с оптимизацией запросов
            products = ProductInfo.objects.filter(
                quantity__gt=0  # только товары в наличии
            ).select_related(
                'product', 'shop', 'product__category'
            ).prefetch_related(
                'product_parameters__parameter'
            ).order_by('id')  # сортировка для стабильной пагинации

            # Фильтрация по магазину
            shop_id = request.query_params.get('shop_id')
            if shop_id:
                products = products.filter(shop_id=shop_id)

            # Фильтрация по категории
            category_id = request.query_params.get('category_id')
            if category_id:
                products = products.filter(product__category_id=category_id)

            # Фильтрация по названию товара (поиск)
            product_name = request.query_params.get('name')
            if product_name:
                products = products.filter(name__icontains=product_name)

            # Пагинация
            paginator = PageNumberPagination()
            paginator.page_size = request.query_params.get('page_size',
                                                           20)  # размер страницы из параметра или 20 по умолчанию
            paginated_products = paginator.paginate_queryset(products, request)

            # Подготовка данных для текущей страницы
            product_list = []
            for product_info in paginated_products:
                product_data = {
                    'id': product_info.id,
                    'external_id': product_info.external_id,
                    'product_id': product_info.product.id if product_info.product else None,
                    'name': product_info.name,
                    'model': product_info.model,
                    'price': product_info.price,
                    'price_rrc': product_info.price_rrc,
                    'quantity': product_info.quantity,
                    'shop': {
                        'id': product_info.shop.id,
                        'name': product_info.shop.name
                    },
                    'category': {
                        'id': product_info.product.category.id if product_info.product and product_info.product.category else None,
                        'name': product_info.product.category.name if product_info.product and product_info.product.category else None
                    },
                    'parameters': [
                        {
                            'id': param.parameter.id,
                            'name': param.parameter.name,
                            'value': param.value
                        } for param in product_info.product_parameters.all()
                    ]
                }
                product_list.append(product_data)

            # Возврат с пагинацией
            return paginator.get_paginated_response({
                'Status': True,
                'Products': product_list
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class CategoryListView(APIView):
    """
    Класс для получения списка категорий
    """
    def get(self, request, *args, **kwargs):
        categories = Category.objects.all().prefetch_related('shops')

        category_list = []
        for category in categories:
            category_data = {
                'id': category.id,
                'name': category.name,
                'shops': [shop.name for shop in category.shops.all()]
            }
            category_list.append(category_data)

        return JsonResponse({'Status': True, 'Categories': category_list})


class ShopListView(APIView):
    """
    Класс для получения списка магазинов
    """
    def get(self, request, *args, **kwargs):
        shops = Shop.objects.filter(user__is_active=True)

        shop_list = []
        for shop in shops:
            shop_data = {
                'id': shop.id,
                'name': shop.name,
                'url': shop.url,
                'user_email': shop.user.email if shop.user else None
            }
            shop_list.append(shop_data)

        return JsonResponse({'Status': True, 'Shops': shop_list})


class CartView(APIView):
    """
    Класс для просмотра корзины
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            # Находим корзину пользователя (статус 'basket')
            cart = Order.objects.filter(
                user=request.user,
                state='basket'
            ).prefetch_related(
                'ordered_items__product_info__shop',
                'ordered_items__product_info__product__category'
            ).first()

            if not cart:
                return JsonResponse({
                    'Status': True,
                    'Message': 'Корзина пуста',
                    'Cart': {}
                })

            # Собираем данные корзины
            cart_data = {
                'order_id': cart.id,
                'total_items': cart.ordered_items.count(),
                'total_amount': 0,
                'items': []
            }

            total_amount = 0
            for item in cart.ordered_items.all():
                item_amount = item.product_info.price * item.quantity
                total_amount += item_amount

                item_data = {
                    'id': item.id,
                    'product_name': item.product_info.name,
                    'shop': item.product_info.shop.name,
                    'quantity': item.quantity,
                    'price': item.product_info.price,
                    'amount': item_amount,
                    'product_info_id': item.product_info.id
                }
                cart_data['items'].append(item_data)

            cart_data['total_amount'] = total_amount

            return JsonResponse({
                'Status': True,
                'Cart': cart_data
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class AddToCartView(APIView):
    """
    Класс для добавления товара в корзину
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            if not {'product_info_id', 'quantity'}.issubset(request.data):
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указаны product_info_id или quantity'
                }, status=400)

            product_info_id = request.data['product_info_id']
            quantity = int(request.data['quantity'])

            # Проверяем существование товара
            try:
                product_info = ProductInfo.objects.get(id=product_info_id, quantity__gte=quantity)
            except ProductInfo.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Товар не найден или недостаточно на складе'
                }, status=404)

            # Находим или создаем корзину пользователя
            cart, created = Order.objects.get_or_create(
                user=request.user,
                state='basket',
                defaults={'contact': None}
            )

            # Добавляем товар в корзину
            order_item, created = OrderItem.objects.get_or_create(
                order=cart,
                product_info=product_info,
                defaults={'quantity': quantity}
            )

            if not created:
                order_item.quantity += quantity
                order_item.save()

            return JsonResponse({
                'Status': True,
                'Message': f'Товар добавлен в корзину. Всего: {order_item.quantity} шт.'
            })

        except ValueError:
            return JsonResponse({
                'Status': False,
                'Error': 'Неверный формат quantity'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class RemoveFromCartView(APIView):
    """
    Класс для удаления товара из корзины
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        try:
            item_id = request.data.get('item_id')

            if not item_id:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан item_id'
                }, status=400)

            # Находим корзину пользователя
            cart = Order.objects.filter(user=request.user, state='basket').first()
            if not cart:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Корзина не найдена'
                }, status=404)

            # Удаляем товар из корзины
            try:
                order_item = OrderItem.objects.get(id=item_id, order=cart)
                order_item.delete()

                return JsonResponse({
                    'Status': True,
                    'Message': 'Товар удален из корзины'
                })

            except OrderItem.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Товар не найден в корзине'
                }, status=404)

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class UpdateCartItemView(APIView):
    """
    Класс для обновления количества товара в корзине
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        try:
            if not {'item_id', 'quantity'}.issubset(request.data):
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указаны item_id или quantity'
                }, status=400)

            item_id = request.data['item_id']
            quantity = int(request.data['quantity'])

            if quantity <= 0:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Количество должно быть больше 0'
                }, status=400)

            # Находим корзину пользователя
            cart = Order.objects.filter(user=request.user, state='basket').first()
            if not cart:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Корзина не найдена'
                }, status=404)

            # Обновляем количество товара
            try:
                order_item = OrderItem.objects.get(id=item_id, order=cart)

                # Проверяем доступное количество на складе
                if order_item.product_info.quantity < quantity:
                    return JsonResponse({
                        'Status': False,
                        'Error': f'Недостаточно товара на складе. Доступно: {order_item.product_info.quantity}'
                    }, status=400)

                order_item.quantity = quantity
                order_item.save()

                return JsonResponse({
                    'Status': True,
                    'Message': f'Количество обновлено: {quantity} шт.'
                })

            except OrderItem.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Товар не найден в корзине'
                }, status=404)

        except ValueError:
            return JsonResponse({
                'Status': False,
                'Error': 'Неверный формат quantity'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class ClearCartView(APIView):
    """
    Класс для очистки всей корзины
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        try:
            # Находим корзину пользователя
            cart = Order.objects.filter(user=request.user, state='basket').first()
            if not cart:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Корзина не найдена'
                }, status=404)

            # Удаляем все товары из корзины
            cart.ordered_items.all().delete()

            return JsonResponse({
                'Status': True,
                'Message': 'Корзина очищена'
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class ContactListView(APIView):
    """
    Класс для просмотра контактов пользователя
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            contacts = Contact.objects.filter(
                user=request.user
            ).select_related('address')

            contact_list = []
            for contact in contacts:
                contact_data = {
                    'id': contact.id,
                    'phone': contact.phone,
                    'address': {
                        'id': contact.address.id,
                        'city': contact.address.city,
                        'street': contact.address.street,
                        'house': contact.address.house,
                        'structure': contact.address.structure,
                        'building': contact.address.building,
                        'apartment': contact.address.apartment
                    }
                }
                contact_list.append(contact_data)

            return JsonResponse({
                'Status': True,
                'Contacts': contact_list
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class AddContactView(APIView):
    """
    Класс для добавления контакта
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            required_fields = {'phone', 'city', 'street'}
            if not required_fields.issubset(request.data):
                return JsonResponse({
                    'Status': False,
                    'Error': f'Не указаны все необходимые аргументы: {", ".join(required_fields)}'
                }, status=400)

            # Создаем адрес
            address = Address.objects.create(
                city=request.data['city'],
                street=request.data['street'],
                house=request.data.get('house', ''),
                structure=request.data.get('structure', ''),
                building=request.data.get('building', ''),
                apartment=request.data.get('apartment', '')
            )

            # Создаем контакт
            contact = Contact.objects.create(
                user=request.user,
                address=address,
                phone=request.data['phone']
            )

            return JsonResponse({
                'Status': True,
                'Message': 'Контакт успешно добавлен',
                'ContactId': contact.id
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class UpdateContactView(APIView):
    """
    Класс для обновления контакта
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        try:
            if not {'contact_id'}.issubset(request.data):
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан contact_id'
                }, status=400)

            contact_id = request.data['contact_id']

            # Проверяем что контакт принадлежит пользователю
            try:
                contact = Contact.objects.get(id=contact_id, user=request.user)
            except Contact.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Контакт не найден'
                }, status=404)

            # Обновляем адрес если переданы данные
            if any(field in request.data for field in
                   ['city', 'street', 'house', 'structure', 'building', 'apartment']):
                address = contact.address
                if 'city' in request.data:
                    address.city = request.data['city']
                if 'street' in request.data:
                    address.street = request.data['street']
                if 'house' in request.data:
                    address.house = request.data.get('house', '')
                if 'structure' in request.data:
                    address.structure = request.data.get('structure', '')
                if 'building' in request.data:
                    address.building = request.data.get('building', '')
                if 'apartment' in request.data:
                    address.apartment = request.data.get('apartment', '')
                address.save()

            # Обновляем телефон если передан
            if 'phone' in request.data:
                contact.phone = request.data['phone']
                contact.save()

            return JsonResponse({
                'Status': True,
                'Message': 'Контакт успешно обновлен'
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class DeleteContactView(APIView):
    """
    Класс для удаления контакта
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        try:
            contact_id = request.data.get('contact_id')

            if not contact_id:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан contact_id'
                }, status=400)

            # Проверяем что контакт принадлежит пользователю
            try:
                contact = Contact.objects.get(id=contact_id, user=request.user)
            except Contact.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Контакт не найден'
                }, status=404)

            # Удаляем контакт и связанный адрес
            address_id = contact.address.id
            contact.delete()

            # Удаляем адрес если на него нет других ссылок
            if not Contact.objects.filter(address_id=address_id).exists():
                Address.objects.filter(id=address_id).delete()

            return JsonResponse({
                'Status': True,
                'Message': 'Контакт успешно удален'
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class SetDefaultContactView(APIView):
    """
    Класс для установки контакта по умолчанию
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            contact_id = request.data.get('contact_id')

            if not contact_id:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан contact_id'
                }, status=400)

            # Проверяем что контакт принадлежит пользователю
            try:
                contact = Contact.objects.get(id=contact_id, user=request.user)
            except Contact.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Контакт не найден'
                }, status=404)

            # Здесь можно добавить логику для установки контакта по умолчанию
            # Например, сохранить ID контакта в профиле пользователя
            # request.user.default_contact = contact
            # request.user.save()

            return JsonResponse({
                'Status': True,
                'Message': 'Контакт установлен по умолчанию'
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class ConfirmOrderView(APIView):
    """
    Класс для подтверждения заказа
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            if not {'contact_id'}.issubset(request.data):
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан contact_id'
                }, status=400)

            contact_id = request.data['contact_id']

            # Находим корзину пользователя
            cart = Order.objects.filter(
                user=request.user,
                state='basket'
            ).prefetch_related('ordered_items').first()

            if not cart:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Корзина пуста'
                }, status=404)

            # Проверяем что контакт принадлежит пользователю
            try:
                contact = Contact.objects.get(id=contact_id, user=request.user)
            except Contact.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Контакт не найден'
                }, status=404)

            # Проверяем что в корзине есть товары
            if not cart.ordered_items.exists():
                return JsonResponse({
                    'Status': False,
                    'Error': 'Корзина пуста'
                }, status=400)

            # Проверяем доступность товаров
            unavailable_items = []
            for item in cart.ordered_items.all():
                if item.product_info.quantity < item.quantity:
                    unavailable_items.append({
                        'product': item.product_info.name,
                        'available': item.product_info.quantity,
                        'requested': item.quantity
                    })

            if unavailable_items:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Недостаточно товаров на складе',
                    'UnavailableItems': unavailable_items
                }, status=400)

            # Обновляем заказ
            cart.contact = contact
            cart.state = 'new'  # меняем статус на "новый"
            cart.save()

            # Резервируем товары (уменьшаем количество на складе)
            for item in cart.ordered_items.all():
                product_info = item.product_info
                product_info.quantity -= item.quantity
                product_info.save()

            return JsonResponse({
                'Status': True,
                'Message': 'Заказ успешно подтвержден',
                'OrderId': cart.id,
                'OrderState': cart.state
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class OrderListView(APIView):
    """
    Класс для просмотра заказов пользователя
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            orders = Order.objects.filter(
                user=request.user
            ).exclude(state='basket').prefetch_related(
                'ordered_items__product_info__shop',
                'contact__address'
            ).order_by('-dt')

            order_list = []
            for order in orders:
                order_data = {
                    'id': order.id,
                    'dt': order.dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'state': order.state,
                    'state_display': order.get_state_display(),
                    'contact': {
                        'phone': order.contact.phone if order.contact else None,
                        'address': {
                            'city': order.contact.address.city if order.contact else None,
                            'street': order.contact.address.street if order.contact else None,
                            'house': order.contact.address.house if order.contact else None,
                            'apartment': order.contact.address.apartment if order.contact else None
                        } if order.contact and order.contact.address else None
                    },
                    'items': [],
                    'total_amount': 0
                }

                total_amount = 0
                for item in order.ordered_items.all():
                    item_amount = item.product_info.price * item.quantity
                    total_amount += item_amount

                    item_data = {
                        'id': item.id,
                        'product_name': item.product_info.name,
                        'shop': item.product_info.shop.name,
                        'quantity': item.quantity,
                        'price': item.product_info.price,
                        'amount': item_amount
                    }
                    order_data['items'].append(item_data)

                order_data['total_amount'] = total_amount
                order_list.append(order_data)

            return JsonResponse({
                'Status': True,
                'Orders': order_list
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class OrderDetailView(APIView):
    """
    Класс для просмотра деталей конкретного заказа
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        try:
            order_id = kwargs.get('order_id')

            if not order_id:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан order_id'
                }, status=400)

            # Проверяем что заказ принадлежит пользователю
            try:
                order = Order.objects.get(
                    id=order_id,
                    user=request.user
                )
            except Order.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Заказ не найден'
                }, status=404)

            order_data = {
                'id': order.id,
                'dt': order.dt.strftime('%Y-%m-%d %H:%M:%S'),
                'state': order.state,
                'state_display': order.get_state_display(),
                'contact': {
                    'phone': order.contact.phone if order.contact else None,
                    'address': {
                        'city': order.contact.address.city if order.contact else None,
                        'street': order.contact.address.street if order.contact else None,
                        'house': order.contact.address.house if order.contact else None,
                        'structure': order.contact.address.structure if order.contact else None,
                        'building': order.contact.address.building if order.contact else None,
                        'apartment': order.contact.address.apartment if order.contact else None
                    } if order.contact and order.contact.address else None
                },
                'items': [],
                'total_amount': 0
            }

            total_amount = 0
            for item in order.ordered_items.all():
                item_amount = item.product_info.price * item.quantity
                total_amount += item_amount

                item_data = {
                    'id': item.id,
                    'product_name': item.product_info.name,
                    'shop': item.product_info.shop.name,
                    'quantity': item.quantity,
                    'price': item.product_info.price,
                    'amount': item_amount,
                    'parameters': [
                        {
                            'name': param.parameter.name,
                            'value': param.value
                        } for param in item.product_info.product_parameters.all()
                    ]
                }
                order_data['items'].append(item_data)

            order_data['total_amount'] = total_amount

            return JsonResponse({
                'Status': True,
                'Order': order_data
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)


class CancelOrderView(APIView):
    """
    Класс для отмены заказа
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            order_id = request.data.get('order_id')

            if not order_id:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Не указан order_id'
                }, status=400)

            # Проверяем что заказ принадлежит пользователю
            try:
                order = Order.objects.get(
                    id=order_id,
                    user=request.user
                )
            except Order.DoesNotExist:
                return JsonResponse({
                    'Status': False,
                    'Error': 'Заказ не найден'
                }, status=404)

            # Проверяем что заказ можно отменить
            if order.state in ['delivered', 'canceled']:
                return JsonResponse({
                    'Status': False,
                    'Error': f'Невозможно отменить заказ в статусе "{order.get_state_display()}"'
                }, status=400)

            # Возвращаем товары на склад
            if order.state != 'basket':
                for item in order.ordered_items.all():
                    product_info = item.product_info
                    product_info.quantity += item.quantity
                    product_info.save()

            # Меняем статус заказа
            order.state = 'canceled'
            order.save()

            return JsonResponse({
                'Status': True,
                'Message': 'Заказ успешно отменен'
            })

        except Exception as e:
            return JsonResponse({
                'Status': False,
                'Error': str(e)
            }, status=500)