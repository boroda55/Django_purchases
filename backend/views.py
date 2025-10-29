from django.contrib.auth import authenticate
from django.core.validators import URLValidator
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ujson import loads as load_json
from yaml import load as load_yaml, Loader
from requests import get
from django.conf import settings
from rest_framework.authtoken.models import Token
from backend.models import Shop, Category, ProductInfo, Product, ProductParameter, Parameter, User, new_user_registered, \
    ConfirmEmailToken
from datetime import timedelta
from django.utils import timezone


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

