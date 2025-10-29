from django.contrib import admin

from django.urls import path

from backend.views import UpdatePrice, UserLogin, UserRegister, UserActivation

app_name = 'backend'
urlpatterns = [
    path('admin/', admin.site.urls),
    path('partner/update/', UpdatePrice.as_view(), name='partner_update'),
    path('login/', UserLogin.as_view(), name='user_login'),
    path('register/', UserRegister.as_view(), name='user_register'),
    path('useractivation/', UserActivation.as_view(), name='user_activation'),
]
