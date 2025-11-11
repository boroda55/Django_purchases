from django.core.cache import cache
from django.conf import settings
from functools import wraps
import time
import hashlib
import json
from typing import Any, Callable, Optional


class CacheMetrics:
    """Класс для сбора метрик кеширования"""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.total_time_with_cache = 0
        self.total_time_without_cache = 0

    def add_hit(self, time_saved: float):
        self.hits += 1
        self.total_time_with_cache += time_saved

    def add_miss(self, time_penalty: float):
        self.misses += 1
        self.total_time_without_cache += time_penalty

    def get_stats(self) -> dict:
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        avg_time_with_cache = (self.total_time_with_cache / self.hits) if self.hits > 0 else 0
        avg_time_without_cache = (self.total_time_without_cache / self.misses) if self.misses > 0 else 0

        return {
            'total_requests': total_requests,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate_percent': round(hit_rate, 2),
            'avg_time_with_cache_ms': round(avg_time_with_cache * 1000, 2),
            'avg_time_without_cache_ms': round(avg_time_without_cache * 1000, 2),
            'total_time_saved_seconds': round(self.total_time_with_cache, 3),
        }


# Глобальный объект для метрик
cache_metrics = CacheMetrics()


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Генерация уникального ключа кеша на основе аргументов
    """
    key_parts = [prefix]

    # Добавляем аргументы
    for arg in args:
        key_parts.append(str(arg))

    # Добавляем ключевые аргументы
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    # Создаем хеш для длинных ключей
    key_string = ":".join(key_parts)
    if len(key_string) > 200:
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix}:{key_hash}"

    return key_string


def cached_view(timeout: int = None, key_prefix: str = None):
    """
    Декоратор для кеширования результатов view функций
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if timeout is None:
                cache_timeout = settings.CACHE_TTL['MEDIUM']
            else:
                cache_timeout = timeout

            # Генерация ключа кеша
            if key_prefix:
                cache_key_prefix = key_prefix
            else:
                cache_key_prefix = f"view:{view_func.__module__}.{view_func.__name__}"

            # Включаем параметры запроса в ключ
            query_params = request.GET.urlencode()
            user_id = request.user.id if request.user.is_authenticated else 'anonymous'

            cache_key = generate_cache_key(
                cache_key_prefix,
                user_id,
                query_params,
                *args,
                **kwargs
            )

            # Пытаемся получить данные из кеша
            start_time = time.time()
            cached_data = cache.get(cache_key)

            if cached_data is not None:
                # Кеш найден
                cache_time = time.time() - start_time
                cache_metrics.add_hit(cache_time)
                return cached_data

            # Кеш не найден, выполняем view функцию
            response = view_func(request, *args, **kwargs)

            # Сохраняем результат в кеш (только для успешных ответов)
            if response.status_code == 200:
                cache.set(cache_key, response, cache_timeout)
                miss_time = time.time() - start_time
                cache_metrics.add_miss(miss_time)

            return response

        return _wrapped_view

    return decorator


def cached_function(timeout: int = None, key_prefix: str = None):
    """
    Декоратор для кеширования результатов обычных функций
    """

    def decorator(func):
        @wraps(func)
        def _wrapped_function(*args, **kwargs):
            if timeout is None:
                cache_timeout = settings.CACHE_TTL['MEDIUM']
            else:
                cache_timeout = timeout

            if key_prefix:
                cache_key_prefix = key_prefix
            else:
                cache_key_prefix = f"func:{func.__module__}.{func.__name__}"

            cache_key = generate_cache_key(cache_key_prefix, *args, **kwargs)

            # Пытаемся получить данные из кеша
            start_time = time.time()
            cached_result = cache.get(cache_key)

            if cached_result is not None:
                cache_time = time.time() - start_time
                cache_metrics.add_hit(cache_time)
                return cached_result

            # Выполняем функцию и сохраняем результат
            result = func(*args, **kwargs)
            cache.set(cache_key, result, cache_timeout)

            miss_time = time.time() - start_time
            cache_metrics.add_miss(miss_time)

            return result

        return _wrapped_function

    return decorator


def invalidate_cache_pattern(pattern: str):
    """
    Инвалидация кеша по паттерну
    """
    keys = cache.keys(pattern)
    if keys:
        cache.delete_many(keys)
        return len(keys)
    return 0


def clear_model_cache(model_class):
    """
    Очистка кеша для конкретной модели
    """
    pattern = f"*{model_class.__name__.lower()}*"
    return invalidate_cache_pattern(pattern)


class CacheManager:
    """
    Менеджер для работы с кешем
    """

    @staticmethod
    def get_user_products_cache_key(user_id: int, filters: dict = None) -> str:
        """Ключ для кеша продуктов пользователя"""
        filters_str = json.dumps(filters, sort_keys=True) if filters else "default"
        return generate_cache_key("user_products", user_id, filters_str)

    @staticmethod
    def get_product_list_cache_key(filters: dict = None) -> str:
        """Ключ для кеша списка продуктов"""
        filters_str = json.dumps(filters, sort_keys=True) if filters else "default"
        return generate_cache_key("product_list", filters_str)

    @staticmethod
    def get_category_cache_key() -> str:
        """Ключ для кеша категорий"""
        return "categories:all"

    @staticmethod
    def get_shop_cache_key() -> str:
        """Ключ для кеша магазинов"""
        return "shops:all"

    @staticmethod
    def invalidate_product_caches():
        """Инвалидация всех кешей связанных с продуктами"""
        patterns = [
            "*product_list*",
            "*user_products*",
            "*product*",
            "*category*",
            "*shop*"
        ]

        total_invalidated = 0
        for pattern in patterns:
            total_invalidated += invalidate_cache_pattern(pattern)

        return total_invalidated