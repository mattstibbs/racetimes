from django.urls import path, reverse_lazy

from django.contrib.auth import views as auth_views

from . import member_views, views

app_name = 'races'

urlpatterns = [
    path('ping/', views.ping, name='ping'),
    path('accounts/signup/', member_views.signup, name='signup'),
    path('accounts/login/', member_views.LoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    # Django's own password reset: a signed, time-limited link by email.
    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(
        email_template_name='emails/password_reset.txt',
        subject_template_name='emails/password_reset_subject.txt',
        success_url=reverse_lazy('races:password_reset_done'),
    ), name='password_reset'),
    path('accounts/password-reset/sent/', auth_views.PasswordResetDoneView.as_view(),
         name='password_reset_done'),
    path('accounts/password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        success_url=reverse_lazy('races:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('accounts/password-reset/done/', auth_views.PasswordResetCompleteView.as_view(),
         name='password_reset_complete'),
    path('my/boats/', member_views.my_boats, name='my_boats'),
    path('my/boats/register/', member_views.register_boat, name='register_boat'),
    path('my/boats/<int:pk>/claim/', member_views.claim_boat, name='claim_boat'),
    path('my/boats/<int:pk>/change/', member_views.change_boat, name='change_boat'),
    path('my/boats/<int:pk>/enter/', member_views.enter_series, name='enter_series'),
    path('my/requests/<str:kind>/<int:pk>/withdraw/', member_views.withdraw_request, name='withdraw_request'),
    path('races/<int:pk>/publish/', views.publish_results, name='publish_results'),
    path('requests/', views.requests_page, name='requests'),
    path('requests/<str:kind>/<int:pk>/', views.decide_request, name='decide_request'),
    path('series/<int:pk>/history/', views.series_history, name='series_history'),
    path('races/<int:pk>/finishes/', views.finish_entry, name='finish_entry'),
    path(
        'races/<int:race_pk>/finishes/<int:entry_pk>/',
        views.save_finish,
        name='save_finish',
    ),
]
