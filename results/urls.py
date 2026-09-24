from django.urls import path

from . import views

app_name = 'results'

urlpatterns = [
    path('', views.home, name='home'),
    path('series/<int:pk>/', views.series, name='series'),
    path('boats/<int:pk>/', views.boat, name='boat'),
]
