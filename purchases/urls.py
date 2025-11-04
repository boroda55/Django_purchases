from django.contrib import admin

from django.urls import path

from backend.views import UpdatePrice, UserLogin, UserRegister, UserActivation, ProductListView, CategoryListView, \
    ShopListView, CartView, AddToCartView, RemoveFromCartView, UpdateCartItemView, ClearCartView, ContactListView, \
    AddContactView, UpdateContactView, DeleteContactView, SetDefaultContactView, ConfirmOrderView, OrderListView, \
    OrderDetailView, CancelOrderView

app_name = 'backend'
urlpatterns = [
    path('admin/', admin.site.urls),
    path('partner/update/', UpdatePrice.as_view(), name='partner_update'),
    path('login/', UserLogin.as_view(), name='user_login'),
    path('register/', UserRegister.as_view(), name='user_register'),
    path('useractivation/', UserActivation.as_view(), name='user_activation'),
    path('products/', ProductListView.as_view(), name='products'),
    path('categories/', CategoryListView.as_view(), name='categories'),
    path('shops/', ShopListView.as_view(), name='shops'),
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/add/', AddToCartView.as_view(), name='add-to-cart'),
    path('cart/remove/', RemoveFromCartView.as_view(), name='remove-from-cart'),
    path('cart/update/', UpdateCartItemView.as_view(), name='update-cart-item'),
    path('cart/clear/', ClearCartView.as_view(), name='clear-cart'),
    path('contacts/', ContactListView.as_view(), name='contacts'),
    path('contacts/add/', AddContactView.as_view(), name='add-contact'),
    path('contacts/update/', UpdateContactView.as_view(), name='update-contact'),
    path('contacts/delete/', DeleteContactView.as_view(), name='delete-contact'),
    path('contacts/set-default/', SetDefaultContactView.as_view(), name='set-default-contact'),
    path('order/confirm/', ConfirmOrderView.as_view(), name='confirm-order'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('order/<int:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('order/cancel/', CancelOrderView.as_view(), name='cancel-order'),
]
