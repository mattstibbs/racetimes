"""Deleting a person's account, keeping the clubs' records whole (slice 11 part 5).

What goes, with the account (the foreign keys do it): their memberships and
the requests they made. What stays: their boats, as each club's records with
no owner, every result, and the change history, which loses its link to them.

Wherever their login is kept as text ("who decided", "who declared this
final", the operator log and so on), it becomes "a deleted account", agreed
with the project owner (docs/decisions.md). A login is unique, so matching it
exactly finds them and no one else. Free text, such as a reason typed for a
correction, can't be searched reliably for a name and is left as written.

These updates bypass the models' own rules on purpose: a recorded change is
never edited (``ScoringChange.save``) and a final series is locked, but
removing a name changes no result.
"""

from django.db import transaction

from .models import (
    BoatRequest, ClubInvitation, ClubMembership, EntryRequest, OperatorAction, ScoringChange, Series,
)

DELETED = "a deleted account"


def clubs_needing_them(user):
    """The clubs where this person is the only approved administrator.

    They can't delete their account until they've made someone else one: a
    club always keeps an administrator.
    """
    approved_administrators = ClubMembership.objects.filter(
        role=ClubMembership.Role.ADMINISTRATOR, status=ClubMembership.Status.APPROVED
    )
    theirs = approved_administrators.filter(user=user).select_related("club")
    return sorted(
        (m.club for m in theirs if approved_administrators.filter(club=m.club).count() == 1),
        key=lambda club: club.name,
    )


def delete_account(user):
    """Remove every stored mention of the person's login, then the account itself."""
    names = {name for name in (user.get_username(), user.email) if name}
    with transaction.atomic():
        for name in names:
            ScoringChange.objects.filter(user_name=name).update(user_name=DELETED)
            BoatRequest.objects.filter(decided_by_name=name).update(decided_by_name=DELETED)
            EntryRequest.objects.filter(decided_by_name=name).update(decided_by_name=DELETED)
            ClubMembership.objects.filter(decided_by_name=name).update(decided_by_name=DELETED)
            Series.objects.filter(declared_final_by_name=name).update(declared_final_by_name=DELETED)
            ClubInvitation.objects.filter(invited_by_name=name).update(invited_by_name=DELETED)
            ClubInvitation.objects.filter(email__iexact=name).update(email=DELETED)
            OperatorAction.objects.filter(who=name).update(who=DELETED)
            for action in OperatorAction.objects.filter(detail__icontains=name):
                action.detail = _replace(action.detail, name)
                action.save(update_fields=["detail"])
        user.delete()


def _replace(text, name):
    """Every mention of ``name`` in ``text``, in any case, as "a deleted account"."""
    lower, found, out, start = text.lower(), name.lower(), [], 0
    while (at := lower.find(found, start)) != -1:
        out += [text[start:at], DELETED]
        start = at + len(found)
    return "".join(out) + text[start:]
