from rest_framework.throttling import UserRateThrottle, AnonRateThrottle, ScopedRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    Throttle для кратковременных всплесков активности
    """
    scope = 'burst'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class SustainedRateThrottle(UserRateThrottle):
    """
    Throttle для длительной sustained активности
    """
    scope = 'sustained'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.pk
        else:
            ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class AuthRateThrottle(AnonRateThrottle):
    """
    Специальный throttle для endpoints аутентификации
    """
    scope = 'auth'


class PartnerRateThrottle(UserRateThrottle):
    """
    Throttle для партнерских endpoints (обновление прайсов)
    """
    scope = 'partner'

    def allow_request(self, request, view):
        # Проверяем, является ли пользователь партнером (магазином)
        if request.user.is_authenticated and request.user.type == 'shop':
            return super().allow_request(request, view)
        # Для непартнеров этот throttle не применяется
        return True


class HighFrequencyThrottle(AnonRateThrottle):
    """
    Throttle для защиты от высокочастотных атак
    """
    scope = 'high_frequency'

    def allow_request(self, request, view):
        # Дополнительная логика для обнаружения подозрительной активности
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Блокируем запросы с пустым User-Agent
        if not user_agent:
            return False

        return super().allow_request(request, view)