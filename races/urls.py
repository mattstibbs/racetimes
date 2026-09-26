from django.urls import path, reverse_lazy

from django.contrib.auth import views as auth_views

from . import account_views, invitations, member_views, membership_views, operator_views, views
from .forms import ClubPasswordResetForm

app_name = 'races'

def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path('ping/', views.ping, name='ping'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('accounts/signup/', member_views.signup, name='signup'),
    path('accounts/login/', member_views.LoginView.as_view(), name='login'),
    path('accounts/confirm/<uidb64>/<token>/', membership_views.confirm_email, name='confirm_email'),
    path('accounts/confirm/again/', membership_views.resend_confirmation, name='resend_confirmation'),
    path('join/', membership_views.join_club, name='join_club'),
    path('account/', account_views.account, name='account'),
    path('account/data.json', account_views.download_my_data, name='download_my_data'),
    path('account/delete/', account_views.delete_my_account, name='delete_account'),
    path('members/', membership_views.members_page, name='members'),
    path('members/<int:pk>/', membership_views.decide_membership, name='decide_membership'),
    path('members/export.zip', membership_views.export_club_data, name='export_club_data'),
    path('invitation/<str:token>/', invitations.accept_invitation, name='accept_invitation'),
    # The operator's pages, on the service's own address only (slice 11 part 3).
    path('operator/', operator_views.clubs, name='operator_clubs'),
    path('operator/clubs/new/', operator_views.create_club, name='operator_create_club'),
    path('operator/clubs/<int:pk>/', operator_views.club_page, name='operator_club'),
    path('operator/clubs/<int:pk>/invite/', operator_views.invite, name='operator_invite'),
    path('operator/clubs/<int:pk>/status/', operator_views.change_status, name='operator_club_status'),
    path('operator/clubs/<int:pk>/export.zip', operator_views.export_club, name='operator_export_club'),
    path('operator/clubs/<int:pk>/delete/', operator_views.delete_club, name='operator_delete_club'),
    path('operator/clubs/<int:pk>/members/<int:membership_pk>/', operator_views.decide_joining,
         name='operator_decide_joining'),
    path('operator/log/', operator_views.operator_log, name='operator_log'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    # Django's own password reset: a signed, time-limited link by email.
    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(
        form_class=ClubPasswordResetForm,
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
    path('sentry-debug/', trigger_error),
]
