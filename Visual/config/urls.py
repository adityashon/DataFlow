

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # All routes for our "core" app are defined in core/urls.py
    # This keeps things modular — core app owns its own URLs
    path("", include("core.urls")),
] + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)