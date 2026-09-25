from django.urls import path

from . import views

app_name = 'results'

urlpatterns = [
    path('', views.home, name='home'),
    path('series/<int:pk>/', views.series, name='series'),
    path('series/<int:pk>/results.csv', views.series_csv, name='series_csv'),
    path('boats/<int:pk>/', views.boat, name='boat'),
]
