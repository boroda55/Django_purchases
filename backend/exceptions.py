class BaseAPIException(Exception):
    """Базовое исключение для API"""
    default_detail = "Произошла ошибка"
    default_code = "error"

    def __init__(self, detail=None, code=None, extra_context=None):
        self.detail = detail or self.default_detail
        self.code = code or self.default_code
        self.extra_context = extra_context or {}
        super().__init__(self.detail)


class PaymentProcessingException(BaseAPIException):
    """Исключение для ошибок обработки платежей"""
    default_detail = "Ошибка обработки платежа"
    default_code = "payment_error"


class InventoryException(BaseAPIException):
    """Исключение для ошибок управления запасами"""
    default_detail = "Ошибка управления запасами"
    default_code = "inventory_error"


class ExternalAPIException(BaseAPIException):
    """Исключение для ошибок внешних API"""
    default_detail = "Ошибка внешнего сервиса"
    default_code = "external_api_error"


class DataValidationException(BaseAPIException):
    """Исключение для ошибок валидации данных"""
    default_detail = "Ошибка валидации данных"
    default_code = "validation_error"