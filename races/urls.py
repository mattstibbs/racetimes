from django.urls import path

from django.contrib.auth import views as auth_views

from . import member_views, views

app_name = 'races'

urlpatterns = [
    path('', views.home, name='home'),
    path('ping/', views.ping, name='ping'),
    path('accounts/signup/', member_views.signup, name='signup'),
    path('accounts/login/', member_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('my/boats/', member_views.my_boats, name='my_boats'),
    path('my/boats/register/', member_views.register_boat, name='register_boat'),
    path('my/boats/<int:pk>/claim/', member_views.claim_boat, name='claim_boat'),
    path('my/boats/<int:pk>/change/', member_views.change_boat, name='change_boat'),
    path('my/boats/<int:pk>/enter/', member_views.enter_series, name='enter_series'),
    path('my/requests/<str:kind>/<int:pk>/withdraw/', member_views.withdraw_request, name='withdraw_request'),
    path('requests/', views.requests_page, name='requests'),
    path('requests/<str:kind>/<int:pk>/', views.decide_request, name='decide_request'),
    path('series/<int:pk>/', views.series_results, name='series_results'),
    path('series/<int:pk>/history/', views.series_history, name='series_history'),
    path('races/<int:pk>/finishes/', views.finish_entry, name='finish_entry'),
    path(
        'races/<int:race_pk>/finishes/<int:entry_pk>/',
        views.save_finish,
        name='save_finish',
    ),
]
