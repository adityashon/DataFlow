

from django.urls import path
from core import views

urlpatterns = [
    path("",views.index,name="index"),
    path("upload/",views.upload,name="upload"),
    path("dashboard/",views.dashboard, name="dashboard"),
    path("download/",views.download_dashboard, name="download"),
]