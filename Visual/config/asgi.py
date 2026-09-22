import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount

from fastapi_service.main import app as fastapi_app


django_app = get_asgi_application()

application = Starlette(
    routes=[
        Mount("/api", app=fastapi_app),
        Mount("/", app=django_app),
    ]
)