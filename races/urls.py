from django.urls import path, reverse_lazy

from django.contrib.auth import views as auth_views

from . import member_views, membership_views, views

app_name = 'races'

urlpatterns = [
    path('ping/', views.ping, name='ping'),
    path('accounts/signup/', member_views.signup, name='signup'),
    path('accounts/login/', member_views.LoginView.as_view(), name='login'),
    path('accounts/confirm/<uidb64>/<token>/', membership_views.confirm_email, name='confirm_email'),
    path('accounts/confirm/again/', membership_views.resend_confirmation, name='resend_confirmation'),
    path('join/', membership_views.join_club, name='join_club'),
    path('members/', membership_views.members_page, name='members'),
    path('members/<int:pk>/', membership_views.decide_membership, name='decide_membership'),
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
    path('series/<int:pk>/final/', views.final_page, name='final'),
    path('series/<int:pk>/final/declare/', views.declare_final, name='declare_final'),
    path('series/<int:pk>/final/reopen/', views.reopen_series, name='reopen_series'),
    path('series/<int:pk>/final/send/', views.send_final, name='send_final'),
    path('races/<int:pk>/', views.race_day_page, name='race_day'),
    # The slice 6 and slice 1 addresses, redirecting to the race day page.
    path('races/<int:pk>/entries/', views.start_sheet_page, name='start_sheet'),
    path('races/<int:pk>/finishes/', views.finish_entry, name='finish_entry'),
    path(
        'races/<int:race_pk>/entries/<int:entry_pk>/',
        views.save_start_sheet_row,
        name='save_start_sheet_row',
    ),
    path(
        'races/<int:race_pk>/finishes/<int:entry_pk>/',
        views.save_finish,
        name='save_finish',
    ),
    path('races/<int:race_pk>/finishes/<int:entry_pk>/tap/', views.tap_finish, name='tap_finish'),
    path('races/<int:race_pk>/finishes/<int:entry_pk>/undo/', views.undo_finish, name='undo_finish'),
]
