"""People and clubs (slice 11 part 2): confirming an email, joining a club, and
the club administrator's Members page.

One account can belong to many clubs, with a role at each. Signing up at a
club's address creates the account, which can log in once its email address
is confirmed, and asks to join that club. Someone with an account already
uses **Join this club** instead. Either way, it's the club's administrators
who approve them, on the Members page.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST

from . import notifications
from .models import ClubMembership
from .roles import club_administrator_required, forget_memberships, membership

Role, Status = ClubMembership.Role, ClubMembership.Status


class EmailConfirmationTokenGenerator(PasswordResetTokenGenerator):
    """Django's signed, time-limited password reset tokens, salted differently.

    So a confirmation link can't reset a password, or the other way round.
    Like a reset link, it lasts PASSWORD_RESET_TIMEOUT (three days), and
    stops working once the account has logged in.
    """

    key_salt = "races.membership_views.EmailConfirmationTokenGenerator"


confirmation_tokens = EmailConfirmationTokenGenerator()


def send_confirmation(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    link = request.build_absolute_uri(
        reverse("races:confirm_email", args=[uid, confirmation_tokens.make_token(user)])
    )
    notifications.confirm_email(user, request.club, request, link)


def confirm_email(request, uidb64, token):
    """The link from the confirmation email: the account can log in from now on."""
    User = get_user_model()
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not confirmation_tokens.check_token(user, token):
        return render(request, "registration/confirm_email.html", {"valid": False}, status=400)
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    return render(request, "registration/confirm_email.html", {"valid": True})


RESEND_SENT = (
    "If that email address has an account that isn't confirmed yet, we've sent the link again. "
    "Check your inbox, and your spam folder."
)


@require_POST
def resend_confirmation(request):
    """Send the confirmation link again. Says the same whether or not the account exists."""
    email = request.POST.get("email", "").strip().lower()
    user = get_user_model().objects.filter(username=email, is_active=False, last_login__isnull=True).first()
    if user is not None:
        send_confirmation(user, request)
    messages.info(request, RESEND_SENT)
    return redirect("races:login")


@login_required
@require_POST
def join_club(request):
    """Ask to join this club: a waiting membership for its administrators to decide."""
    found = membership(request.user, request.club)
    if found is not None and found.status in (Status.APPROVED, Status.WAITING):
        return redirect("races:my_boats")
    if found is None:
        ClubMembership.objects.create(user=request.user, club=request.club)
    else:  # removed before: asking again
        found.status, found.role = Status.WAITING, Role.MEMBER
        found.decided_by_name, found.decided_at = "", None
        found.save()
    forget_memberships(request.user)
    messages.success(request, f"Asked to join {request.club}. You'll get an email when the club's administrator decides.")
    return redirect("races:my_boats")


# --- The club administrator's Members page -------------------------------------------------


@club_administrator_required
def members_page(request):
    memberships = request.club.memberships.select_related("user")
    return render(request, "races/members.html", {
        "waiting": [m for m in memberships if m.status == Status.WAITING],
        "approved": [m for m in memberships if m.status == Status.APPROVED],
        "removed": [m for m in memberships if m.status == Status.REMOVED],
        "roles": Role.choices,
    })


OWN_MEMBERSHIP = "You can't change your own membership. Ask another of the club's administrators."
LAST_ADMINISTRATOR = "The club must keep at least one administrator. Make someone else an administrator first."


@club_administrator_required
@require_POST
def decide_membership(request, pk):
    """Approve, reject, change the role of, or remove one person at this club."""
    target = get_object_or_404(request.club.memberships.select_related("user"), pk=pk)
    action = request.POST.get("action")
    try:
        change = _decide(request, target, action, request.POST.get("role", ""))
    except ValidationError as refused:
        messages.error(request, " ".join(refused.messages))
    else:
        if change:
            target.refresh_from_db()  # as decided, for the email
            notifications.membership_decided(target, request, change)
            messages.success(request, f"{_name(target.user)}: {CHANGE_MESSAGES[change]}")
    return redirect("races:members")


CHANGE_MESSAGES = {
    "approved": "approved and emailed.",
    "rejected": "not approved, and emailed.",
    "role": "role changed, and emailed.",
    "removed": "removed from the club, and emailed.",
}


def _decide(request, target, action, role):
    if target.user_id == request.user.pk:
        raise ValidationError(OWN_MEMBERSHIP)
    with transaction.atomic():
        target = ClubMembership.objects.select_for_update().get(pk=target.pk)
        was_administrator = target.is_approved and target.role == Role.ADMINISTRATOR
        if action == "approve" and target.status == Status.WAITING:
            target.status, change = Status.APPROVED, "approved"
            if role in Role.values:
                target.role = role
        elif action == "reject" and target.status == Status.WAITING:
            target.status, change = Status.REMOVED, "rejected"
        elif action == "role" and target.is_approved and role in Role.values and role != target.role:
            target.role, change = role, "role"
        elif action == "remove" and target.is_approved:
            target.status, change = Status.REMOVED, "removed"
        else:
            return None  # a stale page, or nothing to change
        if was_administrator and not (target.is_approved and target.role == Role.ADMINISTRATOR):
            administrators = request.club.memberships.filter(status=Status.APPROVED, role=Role.ADMINISTRATOR)
            if administrators.exclude(pk=target.pk).count() == 0:
                raise ValidationError(LAST_ADMINISTRATOR)
        target.decided_by_name = request.user.get_username()
        target.decided_at = timezone.now()
        target.save()
    return change


def _name(user):
    return user.get_full_name() or user.get_username()
