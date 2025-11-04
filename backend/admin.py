from django.contrib import admin
from backend.models import (
    User, Shop, Category, Product, ProductInfo,
    Parameter, ProductParameter, Address, Contact,
    Order, OrderItem, ConfirmEmailToken
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'username', 'company', 'type', 'is_active', 'is_staff']
    list_filter = ['type', 'is_active', 'is_staff']
    search_fields = ['email', 'username', 'company']
    ordering = ['email']


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ['name', 'url', 'user']
    list_filter = ['user']
    search_fields = ['name', 'url']
    raw_id_fields = ['user']


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    filter_horizontal = ['shops']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category']
    list_filter = ['category']
    search_fields = ['name']
    raw_id_fields = ['category']


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ['name', 'product', 'shop', 'price', 'quantity', 'external_id']
    list_filter = ['shop', 'product__category']
    search_fields = ['name', 'model']
    raw_id_fields = ['product', 'shop']


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ['product_info', 'parameter', 'value']
    list_filter = ['parameter']
    search_fields = ['product_info__name', 'parameter__name', 'value']
    raw_id_fields = ['product_info', 'parameter']


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['city', 'street', 'house', 'apartment']
    search_fields = ['city', 'street', 'house']
    list_filter = ['city']


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'get_address']
    list_filter = ['user']
    search_fields = ['user__email', 'phone', 'address__city', 'address__street']
    raw_id_fields = ['user', 'address']

    def get_address(self, obj):
        return f"{obj.address.city}, {obj.address.street}, {obj.address.house}"

    get_address.short_description = 'Адрес'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'dt', 'state', 'contact']
    list_filter = ['state', 'dt']
    search_fields = ['user__email', 'contact__phone']
    raw_id_fields = ['user', 'contact']
    date_hierarchy = 'dt'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product_info', 'quantity']
    list_filter = ['order__state']
    search_fields = ['order__user__email', 'product_info__name']
    raw_id_fields = ['order', 'product_info']


@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'key', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email', 'key']
    readonly_fields = ['created_at']
    raw_id_fields = ['user']