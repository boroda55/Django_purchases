from django.contrib import admin

from django.urls import path

from backend.views import UpdatePrice, UserLogin

app_name = 'backend'
urlpatterns = [
    path('admin/', admin.site.urls),
    path('partner/update/', UpdatePrice.as_view(), name='partner-update'),
    path('login/', UserLogin.as_view(), name='user_login'),
]
