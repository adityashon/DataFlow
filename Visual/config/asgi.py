import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")

from django.core.asgi import get_asgi_application
from fastapi_service.main import app as fastapi_app
from starlette.routing import Mount
from starlette.applications import Starlette

django_app = get_asgi_application()

application = Starlette(
    routes=[
        Mount("/process", app=fastapi_app),
        Mount("/", app=django_app),
    ]
)