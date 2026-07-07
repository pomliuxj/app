"""api_automation_test URL Configuration"""
from django.urls import re_path as url
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from api_test import urls
from api_test.api.ApiDoc import MockRequest
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)


class PublicSchemaView(SpectacularAPIView):
    """无需认证的 Schema 端点，方便导入 Swagger 时自引用。"""
    authentication_classes = ()
    permission_classes = ()


urlpatterns = [
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    # Swagger / OpenAPI schema（无需认证，供 LeadSwagger 导入使用）
    path('api/schema/', PublicSchemaView.as_view(), name='schema'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('admin/', admin.site.urls),
    url(r'^$', TemplateView.as_view(template_name="index.html")),
    url(r'^api/', include(urls)),
    path('mock/<path:apiAdr>', MockRequest.as_view()),
]
