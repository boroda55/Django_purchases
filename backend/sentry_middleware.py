import sentry_sdk
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings


class SentryContextMiddleware(MiddlewareMixin):
    """
    Middleware для добавления контекста в Sentry события
    """

    def process_request(self, request):
        # Добавляем информацию о пользователе в Sentry
        if hasattr(request, 'user') and request.user.is_authenticated:
            sentry_sdk.set_user({
                "id": request.user.id,
                "email": request.user.email,
                "username": request.user.username,
                "type": request.user.type,
                "ip_address": self.get_client_ip(request),
            })
        else:
            sentry_sdk.set_user({
                "ip_address": self.get_client_ip(request),
                "anonymous": True,
            })

        # Добавляем теги для запроса
        sentry_sdk.set_tag("request.path", request.path)
        sentry_sdk.set_tag("request.method", request.method)

        # Добавляем контекст
        sentry_sdk.set_context("request", {
            "url": request.build_absolute_uri(),
            "method": request.method,
            "headers": dict(request.headers),
            "user_agent": request.META.get('HTTP_USER_AGENT', ''),
        })

    def get_client_ip(self, request):
        """
        Получение реального IP адреса клиента
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def process_exception(self, request, exception):
        """
        Обработка исключений для Sentry
        """
        # Логируем дополнительную информацию при исключениях
        sentry_sdk.set_context("request.data", {
            "GET": dict(request.GET),
            "POST": dict(request.POST) if request.method == 'POST' else {},
            "body": request.body.decode('utf-8') if request.body else '',
        })

        # Добавляем тег для исключений
        sentry_sdk.set_tag("exception.type", type(exception).__name__)

        # Продолжаем стандартную обработку исключения
        return None


class SentryPerformanceMiddleware(MiddlewareMixin):
    """
    Middleware для мониторинга производительности
    """

    def process_request(self, request):
        # Начинаем транзакцию для мониторинга производительности
        sentry_sdk.set_tag("view_name", self.get_view_name(request))

    def get_view_name(self, request):
        """
        Получение имени view для транзакции
        """
        if hasattr(request, 'resolver_match'):
            return request.resolver_match.view_name
        return request.path