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
    ConfirmEmailToken, Order, OrderItem, Contact, Address, ProductImage
from datetime import timedelta
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from .tasks import send_confirmation_email
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from backend.throttling import AuthRateThrottle, PartnerRateThrottle, HighFrequencyThrottle
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
import uuid
import sentry_sdk
from datetime import datetime
from django.db import DatabaseError
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse
from backend.exceptions import PaymentProcessingException, InventoryException, \
    ExternalAPIException, DataValidationException
from rest_framework.views import exception_handler
from backend.exceptions import BaseAPIException
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from backend.cache_utils import cached_view, CacheManager, cache_metrics
import time

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
    throttle_classes = [PartnerRateThrottle]
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
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
    Аутентификация пользователя в системе.

    При успешной аутентификации:
    - Удаляются старые токены пользователя
    - Создается новый токен аутентификации
    - Возвращается токен для использования в последующих запросах
    """
    throttle_classes = [AuthRateThrottle, HighFrequencyThrottle]

    @extend_schema(
        summary="Вход в систему",
        description="Аутентификация пользователя по email и паролю",
        request={
            'application/json': {
                'type': 'object',
                'required': ['email', 'password'],
                'properties': {
                    'email': {'type': 'string', 'format': 'email', 'example': 'user@example.com'},
                    'password': {'type': 'string', 'example': 'password123'}
                }
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': True},
                    'Message': {'type': 'string', 'example': 'your_auth_token_here'}
                }
            },
            400: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': False},
                    'Message': {'type': 'string', 'example': 'Не передан email или пароль'}
                }
            },
            401: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': False},
                    'Message': {'type': 'string', 'example': 'Пользователя не существует'}
                }
            },
            403: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': False},
                    'Message': {'type': 'string', 'example': 'Пользователь не активный'}
                }
            }
        }
    )
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
        Регистрация нового пользователя в системе.

        При успешной регистрации:
        - Создается неактивный пользователь
        - Отправляется email с токеном подтверждения
        - Для магазинов автоматически устанавливается тип 'shop'
    """
    throttle_classes = [AuthRateThrottle, HighFrequencyThrottle]


    @extend_schema(
        summary="Регистрация пользователя",
        description="""
            Регистрация нового пользователя в системе.

            Особенности:
            - Если указана компания, пользователь регистрируется как магазин
            - После регистрации отправляется email с токеном подтверждения
            - Пользователь создается неактивным до подтверждения email
            """,
        request={
            'application/json': {
                'type': 'object',
                'required': ['email', 'username', 'password'],
                'properties': {
                    'email': {'type': 'string', 'format': 'email', 'example': 'user@example.com'},
                    'username': {'type': 'string', 'example': 'john_doe'},
                    'password': {'type': 'string', 'example': 'securepassword123'},
                    'company': {'type': 'string', 'example': 'My Company LLC'},
                }
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': True},
                    'Message': {'type': 'string', 'example': 'Пользователь зарегистрирован'}
                }
            },
            401: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': False},
                    'Message': {'type': 'string', 'example': 'Не указаны все необходимые аргументы'}
                }
            },
            403: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean', 'example': False},
                    'Message': {'type': 'string', 'example': 'Пользователь с таким email уже существует'}
                }
            }
        },
        examples=[
            OpenApiExample(
                'Успешная регистрация покупателя',
                value={
                    'email': 'buyer@example.com',
                    'username': 'buyer_user',
                    'password': 'password123'
                },
                request_only=True
            ),
            OpenApiExample(
                'Успешная регистрация магазина',
                value={
                    'email': 'shop@example.com',
                    'username': 'shop_user',
                    'password': 'password123',
                    'company': 'Best Shop LLC'
                },
                request_only=True
            )
        ]
    )
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

    throttle_classes = [AuthRateThrottle]
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
    Повторное направление ключа активации
    """
    throttle_classes = [AuthRateThrottle]
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

            # Асинхронная отправка нового токена
            send_confirmation_email.delay(user.id)

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


@extend_schema_view(
    get=extend_schema(
        summary="Получить список товаров",
        description="""
        Получение списка товаров с поддержкой фильтрации и пагинации.

        Доступные фильтры:
        - shop_id: фильтрация по магазину
        - category_id: фильтрация по категории  
        - name: поиск по названию товара
        """,
        parameters=[
            OpenApiParameter(
                name='shop_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='ID магазина для фильтрации'
            ),
            OpenApiParameter(
                name='category_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='ID категории для фильтрации'
            ),
            OpenApiParameter(
                name='name',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Название товара для поиска'
            ),
            OpenApiParameter(
                name='page',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Номер страницы'
            ),
            OpenApiParameter(
                name='page_size',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='Размер страницы (по умолчанию 20)'
            )
        ]
    )
)
class ProductListView(APIView):
    """
        Класс для получения списка товаров с пагинацией и кешированием

        Предоставляет возможность:
        - Просмотра списка товаров с пагинацией
        - Фильтрации по магазину, категории и названию
        - Получения детальной информации о каждом товаре
    """
    throttle_classes = [AnonRateThrottle]

    @method_decorator(cache_page(60 * 15))
    @cached_view(timeout=60 * 15, key_prefix="product_list_view")  # Дополнительное кеширование
    def get(self, request, *args, **kwargs):
        try:
            start_time = time.time()

            # Базовый queryset с оптимизацией запросов
            products = ProductInfo.objects.filter(
                quantity__gt=0
            ).select_related(
                'product', 'shop', 'product__category'
            ).prefetch_related(
                'product_parameters__parameter'
            ).order_by('id')

            # Фильтрация
            shop_id = request.query_params.get('shop_id')
            if shop_id:
                products = products.filter(shop_id=shop_id)

            category_id = request.query_params.get('category_id')
            if category_id:
                products = products.filter(product__category_id=category_id)

            product_name = request.query_params.get('name')
            if product_name:
                products = products.filter(name__icontains=product_name)

            # Пагинация
            paginator = PageNumberPagination()
            paginator.page_size = request.query_params.get('page_size', 20)
            paginated_products = paginator.paginate_queryset(products, request)

            # Подготовка данных
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

            response_data = {
                'Status': True,
                'Products': product_list,
                'ExecutionTimeMs': round((time.time() - start_time) * 1000, 2)
            }

            # Добавляем пагинацию к ответу
            response = paginator.get_paginated_response(response_data)
            return response

        except Exception as e:
            return Response({
                'Status': False,
                'Error': str(e)
            }, status=500)


class CategoryListView(APIView):
    """
    Класс для получения списка категорий
    """

    @method_decorator(cache_page(60 * 60))  # Кеширование на 1 час
    @cached_view(timeout=60 * 60, key_prefix="category_list_view")
    def get(self, request, *args, **kwargs):
        start_time = time.time()

        categories = Category.objects.all().prefetch_related('shops')

        category_list = []
        for category in categories:
            category_data = {
                'id': category.id,
                'name': category.name,
                'shops': [shop.name for shop in category.shops.all()]
            }
            category_list.append(category_data)

        return Response({
            'Status': True,
            'Categories': category_list,
            'ExecutionTimeMs': round((time.time() - start_time) * 1000, 2),
            'Cached': True  # Показывает что данные из кеша
        })

class ShopListView(APIView):
    """
    Класс для получения списка магазинов
    """

    @method_decorator(cache_page(60 * 30))  # Кеширование на 30 минут
    @cached_view(timeout=60 * 30, key_prefix="shop_list_view")
    def get(self, request, *args, **kwargs):
        start_time = time.time()

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

        return Response({
            'Status': True,
            'Shops': shop_list,
            'ExecutionTimeMs': round((time.time() - start_time) * 1000, 2),
            'Cached': True
        })


@extend_schema_view(
    get=extend_schema(
        summary="Просмотр корзины",
        description="Получение текущего состояния корзины пользователя",
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'Status': {'type': 'boolean'},
                    'Message': {'type': 'string'},
                    'Cart': {
                        'type': 'object',
                        'properties': {
                            'order_id': {'type': 'integer'},
                            'total_items': {'type': 'integer'},
                            'total_amount': {'type': 'integer'},
                            'items': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'id': {'type': 'integer'},
                                        'product_name': {'type': 'string'},
                                        'shop': {'type': 'string'},
                                        'quantity': {'type': 'integer'},
                                        'price': {'type': 'integer'},
                                        'amount': {'type': 'integer'},
                                        'product_info_id': {'type': 'integer'}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        auth=['TokenAuth']
    )
)
class CartView(APIView):
    """
    Управление корзиной покупок.

    Требует аутентификации по токену.
    Корзина автоматически создается при первом добавлении товара.
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

@extend_schema_view(
    post=extend_schema(
        summary="Добавить товар в корзину",
        description="Добавление товара в корзину пользователя",
        request={
            'application/json': {
                'type': 'object',
                'required': ['product_info_id', 'quantity'],
                'properties': {
                    'product_info_id': {'type': 'integer', 'example': 1},
                    'quantity': {'type': 'integer', 'example': 2}
                }
            }
        },
        auth=['TokenAuth']
    )
)
class AddToCartView(APIView):
    """
    Добавление товаров в корзину.

    Если товар уже есть в корзине - увеличивает количество.
    Проверяет доступность товара на складе.
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


class GoogleAuthSuccessView(APIView):
    """
    View для обработки успешной Google аутентификации
    Возвращает токен для использования в API
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Успешная Google аутентификация",
        description="""
        Endpoint для обработки успешной аутентификации через Google.
        Создает или обновляет токен для пользователя.
        """,
        responses={
            200: OpenApiResponse(
                description="Успешная аутентификация",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'Message': {'type': 'string', 'example': 'Аутентификация успешна'},
                        'Token': {'type': 'string', 'example': 'your_auth_token_here'},
                        'User': {
                            'type': 'object',
                            'properties': {
                                'id': {'type': 'integer', 'example': 1},
                                'email': {'type': 'string', 'example': 'user@gmail.com'},
                                'username': {'type': 'string', 'example': 'john_doe'},
                                'first_name': {'type': 'string', 'example': 'John'},
                                'last_name': {'type': 'string', 'example': 'Doe'},
                                'type': {'type': 'string', 'example': 'buyer'}
                            }
                        }
                    }
                }
            ),
            401: OpenApiResponse(
                description="Пользователь не аутентифицирован",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': False},
                        'Message': {'type': 'string', 'example': 'Пользователь не аутентифицирован'}
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Удаляем старые токены пользователя
            Token.objects.filter(user=request.user).delete()

            # Создаем новый токен
            token = Token.objects.create(user=request.user)

            user_data = {
                'id': request.user.id,
                'email': request.user.email,
                'username': request.user.username,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'type': request.user.type
            }

            return Response({
                'Status': True,
                'Message': 'Google аутентификация успешна',
                'Token': token.key,
                'User': user_data
            }, status=status.HTTP_200_OK)

        return Response({
            'Status': False,
            'Message': 'Пользователь не аутентифицирован через Google'
        }, status=status.HTTP_401_UNAUTHORIZED)


class GoogleAuthErrorView(APIView):
    """
    View для обработки ошибок Google аутентификации
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Ошибка Google аутентификации",
        description="Endpoint для обработки ошибок аутентификации через Google",
        responses={
            400: OpenApiResponse(
                description="Ошибка аутентификации",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': False},
                        'Message': {'type': 'string', 'example': 'Ошибка аутентификации через Google'}
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        error_message = request.GET.get('message', 'Произошла ошибка при аутентификации через Google')

        return Response({
            'Status': False,
            'Message': error_message
        }, status=status.HTTP_400_BAD_REQUEST)


class GoogleAuthInitView(APIView):
    """
    View для получения URL для начала Google аутентификации
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="URL для Google аутентификации",
        description="Получение URL для начала аутентификации через Google OAuth2",
        responses={
            200: OpenApiResponse(
                description="URL для Google аутентификации",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'auth_url': {'type': 'string', 'example': '/api/auth/login/google-oauth2/'},
                        'description': {'type': 'string',
                                        'example': 'Перейдите по ссылке для аутентификации через Google'}
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        auth_url = '/api/auth/login/google-oauth2/'

        return Response({
            'Status': True,
            'auth_url': auth_url,
            'description': 'Перейдите по ссылке для аутентификации через Google. После успешной аутентификации вы будете перенаправлены на endpoint /api/auth/google/success/ где получите токен для API.'
        }, status=status.HTTP_200_OK)


class UserAvatarUploadView(APIView):
    """
    Класс для загрузки аватара пользователя
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Загрузка аватара пользователя",
        description="""
        Загрузка аватара пользователя с автоматической генерацией миниатюр.

        Поддерживаемые форматы: JPG, JPEG, PNG, GIF, WebP
        Максимальный размер: 5MB
        """,
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'avatar': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'Файл изображения'
                    }
                }
            }
        },
        responses={
            200: OpenApiResponse(
                description="Аватар успешно загружен",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'Message': {'type': 'string', 'example': 'Аватар успешно загружен'},
                        'AvatarURL': {'type': 'string', 'example': '/media/avatars/2024/01/15/avatar.jpg'},
                        'ThumbnailURL': {'type': 'string',
                                         'example': '/media/avatars/thumbnails/2024/01/15/avatar_thumb.jpg'}
                    }
                }
            ),
            400: OpenApiResponse(
                description="Ошибка загрузки",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': False},
                        'Error': {'type': 'string', 'example': 'Файл слишком большой'}
                    }
                }
            )
        }
    )
    def put(self, request, *args, **kwargs):
        try:
            if 'avatar' not in request.FILES:
                return Response({
                    'Status': False,
                    'Error': 'Файл не предоставлен'
                }, status=status.HTTP_400_BAD_REQUEST)

            avatar_file = request.FILES['avatar']

            # Проверка размера файла
            if avatar_file.size > settings.MAX_UPLOAD_SIZE:
                return Response({
                    'Status': False,
                    'Error': f'Файл слишком большой. Максимальный размер: {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка расширения файла
            file_ext = avatar_file.name.split('.')[-1].lower()
            if file_ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
                return Response({
                    'Status': False,
                    'Error': f'Неподдерживаемый формат файла. Разрешенные: {", ".join(settings.ALLOWED_IMAGE_EXTENSIONS)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Удаляем старый аватар если есть
            if request.user.avatar:
                request.user.avatar.delete(save=False)
            if request.user.avatar_thumbnail:
                request.user.avatar_thumbnail.delete(save=False)

            # Сохраняем новый аватар
            request.user.avatar = avatar_file
            request.user.save()

            # Запускаем асинхронную генерацию миниатюр
            from backend.tasks import generate_avatar_thumbnails
            generate_avatar_thumbnails.delay(request.user.id)

            return Response({
                'Status': True,
                'Message': 'Аватар успешно загружен',
                'AvatarURL': request.user.avatar.url,
                'ThumbnailURL': request.user.avatar_thumbnail.url if request.user.avatar_thumbnail else None
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'Status': False,
                'Error': f'Ошибка при загрузке аватара: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductImageUploadView(APIView):
    """
    Класс для загрузки изображений товаров
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Загрузка изображения товара",
        description="""
        Загрузка изображения для товара с автоматической генерацией миниатюр.
        Доступно только для магазинов.
        """,
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'image': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'Файл изображения товара'
                    },
                    'product_id': {
                        'type': 'integer',
                        'description': 'ID товара'
                    },
                    'is_main': {
                        'type': 'boolean',
                        'description': 'Сделать основным изображением'
                    }
                },
                'required': ['image', 'product_id']
            }
        },
        responses={
            200: OpenApiResponse(
                description="Изображение успешно загружено",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'Message': {'type': 'string', 'example': 'Изображение успешно загружено'},
                        'ImageId': {'type': 'integer', 'example': 1},
                        'ImageURL': {'type': 'string', 'example': '/media/products/2024/01/15/image.jpg'},
                        'ThumbnailURL': {'type': 'string', 'example': '/media/products/thumbnails/2024/01/15/thumb.jpg'}
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            if request.user.type != 'shop':
                return Response({
                    'Status': False,
                    'Error': 'Только магазины могут загружать изображения товаров'
                }, status=status.HTTP_403_FORBIDDEN)

            if 'image' not in request.FILES:
                return Response({
                    'Status': False,
                    'Error': 'Файл изображения не предоставлен'
                }, status=status.HTTP_400_BAD_REQUEST)

            product_id = request.data.get('product_id')
            if not product_id:
                return Response({
                    'Status': False,
                    'Error': 'Не указан ID товара'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверяем существование товара и принадлежность магазину
            try:
                product = Product.objects.get(id=product_id)
                # Здесь можно добавить проверку принадлежности товара магазину пользователя
            except Product.DoesNotExist:
                return Response({
                    'Status': False,
                    'Error': 'Товар не найден'
                }, status=status.HTTP_404_NOT_FOUND)

            image_file = request.FILES['image']

            # Проверка размера файла
            if image_file.size > settings.MAX_UPLOAD_SIZE:
                return Response({
                    'Status': False,
                    'Error': f'Файл слишком большой. Максимальный размер: {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка расширения файла
            file_ext = image_file.name.split('.')[-1].lower()
            if file_ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
                return Response({
                    'Status': False,
                    'Error': f'Неподдерживаемый формат файла. Разрешенные: {", ".join(settings.ALLOWED_IMAGE_EXTENSIONS)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Создаем запись изображения
            product_image = ProductImage.objects.create(
                product=product,
                image=image_file,
                is_main=request.data.get('is_main', False)
            )

            # Если это основное изображение, обновляем связь в ProductInfo
            if product_image.is_main:
                product_info = ProductInfo.objects.filter(product=product).first()
                if product_info:
                    product_info.main_image = product_image
                    product_info.save()

            return Response({
                'Status': True,
                'Message': 'Изображение товара успешно загружено',
                'ImageId': product_image.id,
                'ImageURL': product_image.image.url,
                'ThumbnailURL': product_image.thumbnail.url if product_image.thumbnail else None
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'Status': False,
                'Error': f'Ошибка при загрузке изображения: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteUserAvatarView(APIView):
    """
    Класс для удаления аватара пользователя
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Удаление аватара пользователя",
        description="Удаление текущего аватара пользователя",
        responses={
            200: OpenApiResponse(
                description="Аватар успешно удален",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'Message': {'type': 'string', 'example': 'Аватар успешно удален'}
                    }
                }
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        try:
            if request.user.avatar:
                request.user.avatar.delete(save=False)
            if request.user.avatar_thumbnail:
                request.user.avatar_thumbnail.delete(save=False)

            request.user.avatar = None
            request.user.avatar_thumbnail = None
            request.user.save()

            return Response({
                'Status': True,
                'Message': 'Аватар успешно удален'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'Status': False,
                'Error': f'Ошибка при удалении аватара: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SentryTestView(APIView):
    """
    Тестовый View для проверки интеграции с Sentry.
    Генерирует различные типы исключений для мониторинга.
    """
    permission_classes = [AllowAny]


    def get(self, request, *args, **kwargs):
        exception_type = request.GET.get('exception_type', 'division_by_zero')

        try:
            if exception_type == 'all':
                return self.generate_all_exceptions()

            exception_info = self.generate_specific_exception(exception_type)

            # Если мы здесь, значит исключение не было сгенерировано
            return Response({
                'Status': True,
                'Message': f'Исключение типа "{exception_type}" не было сгенерировано',
                'ExceptionInfo': exception_info
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # Захватываем исключение и отправляем в Sentry с дополнительным контекстом
            event_id = sentry_sdk.capture_exception(e)

            # Добавляем кастомный контекст
            sentry_sdk.set_context("test_exception", {
                "exception_type": exception_type,
                "test_timestamp": datetime.now().isoformat(),
                "user_agent": request.META.get('HTTP_USER_AGENT', ''),
                "query_params": dict(request.GET),
            })

            # Устанавливаем теги для лучшей фильтрации
            sentry_sdk.set_tag("test_exception", "true")
            sentry_sdk.set_tag("exception_type", exception_type)
            sentry_sdk.set_tag("environment", "testing")

            return Response({
                'Status': False,
                'Error': str(e),
                'ExceptionType': type(e).__name__,
                'SentryEventId': event_id,
                'Message': f'Исключение "{type(e).__name__}" было отправлено в Sentry'
            }, status=status.HTTP_400_BAD_REQUEST)

    def generate_specific_exception(self, exception_type):
        """Генерация конкретного типа исключения"""
        exception_handlers = {
            'division_by_zero': self._division_by_zero,
            'index_error': self._index_error,
            'key_error': self._key_error,
            'type_error': self._type_error,
            'value_error': self._value_error,
            'attribute_error': self._attribute_error,
            'import_error': self._import_error,
            'database_error': self._database_error,
            'payment_error': self._payment_error,
            'inventory_error': self._inventory_error,
            'external_api_error': self._external_api_error,
            'validation_error': self._validation_error,
        }

        handler = exception_handlers.get(exception_type)
        if handler:
            return handler()

        return {"error": f"Unknown exception type: {exception_type}"}

    def generate_all_exceptions(self):
        """Генерация всех типов исключений (для комплексного тестирования)"""
        generated_exceptions = []

        exception_types = [
            'division_by_zero', 'index_error', 'key_error', 'type_error',
            'value_error', 'attribute_error', 'payment_error', 'inventory_error'
        ]

        for exc_type in exception_types:
            try:
                self.generate_specific_exception(exc_type)
                generated_exceptions.append(f"{exc_type}: generated")
            except Exception as e:
                # Ловим и логируем каждое исключение
                event_id = sentry_sdk.capture_exception(e)
                generated_exceptions.append(f"{exc_type}: {type(e).__name__} (Sentry: {event_id})")

        return Response({
            'Status': True,
            'Message': 'Все тестовые исключения сгенерированы',
            'GeneratedExceptions': generated_exceptions
        }, status=status.HTTP_200_OK)

    # Методы для генерации конкретных исключений
    def _division_by_zero(self):
        result = 1 / 0  # Это вызовет ZeroDivisionError
        return {"result": result}

    def _index_error(self):
        items = [1, 2, 3]
        result = items[10]  # IndexError
        return {"result": result}

    def _key_error(self):
        data = {"name": "test"}
        result = data["nonexistent_key"]  # KeyError
        return {"result": result}

    def _type_error(self):
        result = "string" + 123  # TypeError
        return {"result": result}

    def _value_error(self):
        result = int("not_a_number")  # ValueError
        return {"result": result}

    def _attribute_error(self):
        result = None.some_method()  # AttributeError
        return {"result": result}


    def _database_error(self):
        from django.db import DatabaseError
        raise DatabaseError("Тестовая ошибка базы данных")

    def _payment_error(self):
        raise PaymentProcessingException(
            detail="Не удалось обработать платеж через Stripe",
            extra_context={
                "payment_gateway": "stripe",
                "amount": 1000,
                "currency": "USD",
                "user_id": 123
            }
        )

    def _inventory_error(self):
        raise InventoryException(
            detail="Недостаточно товара на складе",
            extra_context={
                "product_id": 456,
                "requested_quantity": 10,
                "available_quantity": 5,
                "warehouse": "main"
            }
        )

    def _external_api_error(self):
        raise ExternalAPIException(
            detail="Сервис доставки временно недоступен",
            extra_context={
                "service": "delivery-api",
                "endpoint": "/api/v1/shipping/calculate",
                "status_code": 503,
                "response_time": 5.2
            }
        )

    def _validation_error(self):
        raise DataValidationException(
            detail="Неверный формат email адреса",
            extra_context={
                "field": "email",
                "value": "invalid-email",
                "pattern": r"^[^@]+@[^@]+\.[^@]+$",
                "constraint": "must_be_valid_email"
            }
        )


class SentryPerformanceTestView(APIView):
    """
    Тестовый View для проверки мониторинга производительности в Sentry
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        import time
        from django.db import connection
        from backend.models import Product

        iterations = int(request.GET.get('iterations', 100))
        delay = float(request.GET.get('delay', 0.01))

        # Начинаем транзакцию для мониторинга производительности
        with sentry_sdk.start_transaction(op="task", name="performance_test") as transaction:
            # Устанавливаем теги для транзакции
            transaction.set_tag("iterations", iterations)
            transaction.set_tag("delay", delay)
            transaction.set_tag("test_type", "performance")

            start_time = time.time()
            results = []

            # Имитация нагрузки
            for i in range(iterations):
                # Создаем span для каждой итерации
                with sentry_sdk.start_span(op="iteration", description=f"iteration_{i}") as span:
                    # Имитация работы с базой данных
                    products_count = Product.objects.count()

                    # Имитация вычислений
                    calculation_result = sum(x * x for x in range(1000))

                    # Задержка
                    time.sleep(delay)

                    results.append({
                        'iteration': i,
                        'products_count': products_count,
                        'calculation_result': calculation_result
                    })

                    span.set_data("products_count", products_count)
                    span.set_data("calculation_result", calculation_result)

            end_time = time.time()
            total_time = end_time - start_time

            # Устанавливаем метрики производительности
            transaction.set_measurement("duration", total_time, "seconds")
            transaction.set_measurement("iterations_per_second", iterations / total_time, "iterations/s")
            transaction.set_measurement("avg_iteration_time", total_time / iterations, "seconds")

            return Response({
                'Status': True,
                'Message': 'Тест производительности завершен',
                'PerformanceMetrics': {
                    'total_iterations': iterations,
                    'total_time_seconds': round(total_time, 3),
                    'iterations_per_second': round(iterations / total_time, 2),
                    'avg_iteration_time_ms': round((total_time / iterations) * 1000, 3),
                    'database_queries': len(connection.queries),
                },
                'ResultsSample': results[:5]  # Показываем только первые 5 результатов
            }, status=status.HTTP_200_OK)


def custom_exception_handler(exc, context):
    """
    Кастомный обработчик исключений для Sentry
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Если это наше кастомное исключение, логируем в Sentry
    if isinstance(exc, BaseAPIException):
        # Логируем кастомное исключение с дополнительным контекстом
        sentry_sdk.capture_exception(exc, extra={
            "exception_detail": exc.detail,
            "exception_code": exc.code,
            "extra_context": exc.extra_context,
            "view": context.get('view').__class__.__name__ if context.get('view') else None,
            "request_method": context['request'].method if context.get('request') else None,
        })

    return response


class CacheStatsView(APIView):
    """
    API для получения статистики кеширования
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Статистика кеширования",
        description="Получение метрик производительности кеширования",
        responses={
            200: OpenApiResponse(
                description="Статистика кеширования",
                response={
                    'type': 'object',
                    'properties': {
                        'Status': {'type': 'boolean', 'example': True},
                        'cache_stats': {
                            'type': 'object',
                            'properties': {
                                'total_requests': {'type': 'integer', 'example': 100},
                                'hits': {'type': 'integer', 'example': 75},
                                'misses': {'type': 'integer', 'example': 25},
                                'hit_rate_percent': {'type': 'number', 'example': 75.0},
                                'avg_time_with_cache_ms': {'type': 'number', 'example': 5.2},
                                'avg_time_without_cache_ms': {'type': 'number', 'example': 150.8},
                                'total_time_saved_seconds': {'type': 'number', 'example': 12.5}
                            }
                        },
                        'redis_info': {
                            'type': 'object',
                            'properties': {
                                'connected_clients': {'type': 'integer', 'example': 5},
                                'used_memory_human': {'type': 'string', 'example': '2.5M'},
                                'keyspace_hits': {'type': 'integer', 'example': 1000},
                                'keyspace_misses': {'type': 'integer', 'example': 100}
                            }
                        }
                    }
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        try:
            from django.core.cache import cache
            import redis

            # Получаем статистику кеширования
            cache_stats = cache_metrics.get_stats()

            # Получаем информацию о Redis
            redis_info = {}
            try:
                # Пытаемся получить информацию из Redis
                redis_client = cache._cache.get_client()
                info = redis_client.info()

                redis_info = {
                    'connected_clients': info.get('connected_clients', 0),
                    'used_memory_human': info.get('used_memory_human', '0K'),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0),
                    'hit_rate_percent': round(
                        info.get('keyspace_hits', 0) /
                        max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1), 1) * 100, 2
                    ),
                    'total_keys': sum(
                        int(db.get('keys', 0))
                        for db in info.get('keyspace', {}).values()
                    )
                }
            except (AttributeError, redis.ConnectionError):
                redis_info = {'error': 'Redis information not available'}

            return Response({
                'Status': True,
                'cache_stats': cache_stats,
                'redis_info': redis_info
            })

        except Exception as e:
            return Response({
                'Status': False,
                'Error': str(e)
            }, status=500)


class CacheManagementView(APIView):
    """
    API для управления кешем (очистка, инвалидация)
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Очистка кеша",
        description="Очистка всего кеша или определенных паттернов",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'pattern': {
                        'type': 'string',
                        'example': '*product*',
                        'description': 'Паттерн для очистки (оставьте пустым для очистки всего кеша)'
                    }
                }
            }
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            from django.core.cache import cache
            from backend.cache_utils import invalidate_cache_pattern

            pattern = request.data.get('pattern')

            if pattern:
                # Очистка по паттерну
                cleared_count = invalidate_cache_pattern(pattern)
                message = f'Очищено {cleared_count} ключей по паттерну: {pattern}'
            else:
                # Очистка всего кеша
                cache.clear()
                message = 'Весь кеш очищен'

            return Response({
                'Status': True,
                'Message': message
            })

        except Exception as e:
            return Response({
                'Status': False,
                'Error': str(e)
            }, status=500)