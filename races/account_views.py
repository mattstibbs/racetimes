"""A person's own account: what's held about them, downloading it, and deleting it (slice 11 part 5).

The account is one across every club, so these pages show and act on every
club's membership, not just the club whose address they're on.
"""

import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from . import notifications
from .account_deletion import clubs_needing_them, delete_account
from .clubs import club_address
from .forms import DeleteAccountForm
from .models import ClubMembership
from .my_data import my_data

DELETED = "Your account has been deleted."
OPERATOR = "The service's operator account can't be deleted here."


@login_required
def account(request):
    memberships = ClubMembership.objects.filter(user=request.user).select_related("club").order_by("club__name")
    return render(request, "races/account.html", {
        "memberships": [(m, club_address(request, m.club)) for m in memberships],
    })


@login_required
def download_my_data(request):
    response = HttpResponse(
        json.dumps(my_data(request.user), indent=2, ensure_ascii=False),
        content_type="application/json; charset=utf-8",
    )
    day = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="race-times-my-data-{day}.json"'
    return response


@login_required
def delete_my_account(request):
    user = request.user
    blocking = clubs_needing_them(user)
    form = DeleteAccountForm(request.POST or None, request=request)
    if request.method == "POST" and not blocking and not user.is_superuser and form.is_valid():
        goodbye = notifications.account_deleted(user, request)
        delete_account(user)
        logout(request)
        notifications.send([goodbye], request)
        messages.success(request, DELETED)
        return redirect("results:home")
    return render(request, "races/delete_account.html", {
        "form": form, "blocking": blocking, "operator": user.is_superuser,
    })
