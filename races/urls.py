from django.urls import path

from . import views

app_name = 'races'

urlpatterns = [
    path('', views.home, name='home'),
    path('ping/', views.ping, name='ping'),
    path('series/<int:pk>/', views.series_results, name='series_results'),
    path('series/<int:pk>/history/', views.series_history, name='series_history'),
    path('races/<int:pk>/finishes/', views.finish_entry, name='finish_entry'),
    path(
        'races/<int:race_pk>/finishes/<int:entry_pk>/',
        views.save_finish,
        name='save_finish',
    ),
]
