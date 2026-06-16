"""Root URL configuration."""
from django.contrib import admin
from django.urls import path, include

from apps.api.views import RouteOptimizeView
 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('routes/', RouteOptimizeView.as_view(), name='routes'),
]
