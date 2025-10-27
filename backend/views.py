from django.core.validators import URLValidator
from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ujson import loads as load_json
from yaml import load as load_yaml, Loader
from requests import get

from backend.models import Shop, Category, ProductInfo, Product, ProductParameter, Parameter


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
        # if not request.user.is_authenticated:
        #     return JsonResponse(status_response(False,
        #                                         'Требуется войти в систему'), status=403)
        # if request.user.type != 'shop':
        #     return JsonResponse(status_response(False,
        #                                         'Вход только для магазинов'),status=403)

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
                    category_object = Category.objects.get_or_create(id=category['id'], name=category['name'])
                    category_object.shops.add(shop.id)
                    category_object.save()
                ProductInfo.objects.filter(shop_id=shop.id).delete()
                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])

                    product_info = ProductInfo.objects.create(product_id=product.id,
                                                              external_id=item['id'],
                                                              model=item['model'],
                                                              price=item['price'],
                                                              price_rrc=item['price_rrc'],
                                                              quantity=item['quantity'],
                                                              shop_id=shop.id)
                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name,)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)

                return JsonResponse(status_response(True))
        return JsonResponse(status_response(False,'Не указаны все необходимые аргументы'))



