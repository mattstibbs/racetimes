from django.urls import path

from . import views

app_name = 'races'

urlpatterns = [
    path('', views.home, name='home'),
    path('ping/', views.ping, name='ping'),
]
