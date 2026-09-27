# Slice 22: renaming a club

**Status: planned (2026-09-27). Waiting on the project owner's answers at the
end.**

## Goal
The operator can rename a club after it's live, for example when a club
changes its name or asks for a shorter one. Today a club's name, address and
contact email are set once, on **Create a club**, and nothing can change
them afterwards.

## What's there now
- `races/operator_forms.ClubForm` (name, address, contact email) is used only
  by `operator_views.create_club`.
- The operator's page for a club (`/operator/clubs/<pk>/`,
  `templates/operator/club.html`) shows its name, address and contact email,
  with sections for its status, people waiting, administrators, invitations
  and data. It has nowhere to change them.
- Every page, email and download reads the club's name live from `Club.name`.
  The only stored copies are in the operator log's text (for example
  "Harbour Sailing Club, contact ..." when it was created), which record what
  happened at the time and stay as they are.

## What gets built

### 1. A "Club settings" section on the operator's club page
A card near the top, under the status card, with the club's **name** in a
text box and a **Save** button. It uses the same rules as creating a club
(required, up to 100 characters).

- Saving a new name changes it everywhere at once: the heading of every page
  on the club's site, the "<Club> via Race Times" sender on its emails, Find
  my club on the landing page, the operator's pages, and downloads.
- The page then says "Renamed Old Name to New Name." Saving the same name
  says nothing changed and logs nothing.
- It works while the club is suspended too, so a club can be renamed before
  it's reactivated.
- The club's **address can't change** (see "Out of scope"). The section says
  so, next to the address.
- Question 3: the contact email in the same form.

### 2. The operator log
Each rename is logged as **Renamed a club**, with the old and new names in its
detail: "Old Name → New Name". This needs a new choice on
`OperatorAction.Action`, which means a migration that changes only the list
of choices, not any table (question 1).

### 3. Telling the club
Question 2.

## Where the code goes
- `races/operator_forms.py`: `ClubSettingsForm`, a `ModelForm` with `name`
  (and `contact_email` if question 3 is yes). `ClubForm` stays as it is for
  creating a club.
- `races/operator_views.py`: `club_settings(request, pk)`, POST only, at
  `/operator/clubs/<pk>/settings/`. It saves and logs in one transaction.
  If the form is invalid, the club page is shown again with the errors.
- `templates/operator/club.html`: the new section.

## Tests
- The operator renames a club: the name changes, the club's own pages show
  the new name, and the log has one "Renamed a club" row with both names.
- Saving the same name changes nothing and logs nothing.
- A blank or over-long name is refused, with the error on the page, and
  nothing is changed or logged.
- The address can't be changed through the form, even by a hand-made POST.
- Only the operator, only on the service's own address: a club's
  administrator gets a 403, the public is sent to log in, and on a club's
  address the page doesn't exist (`races/test_operator.py`'s existing
  pattern).
- Works while the club is suspended.
- Emails sent after a rename come from "<New Name> via Race Times".

## Docs
- `docs/operating.md`: a "Renaming a club" section.
- The user manual is for clubs' own people, so it doesn't change: they ask the
  operator for a new name.
- `docs/decisions.md`: why the address stays fixed.

## Acceptance criteria
- The operator can rename a live or suspended club from its page, and the new
  name shows at once on the club's site and in its emails.
- Every rename is in the operator log with the old and new names.
- The club's address can't change.
- All tests, Ruff and the migrations check pass; checked by hand in a browser.

## Out of scope
- **Changing a club's address** (`harbour.racetimes.co.uk`). Every bookmark,
  emailed link, invitation and shared WhatsApp message points at it, and so
  does the club's own publicity. Changing it safely needs redirects from the
  old address and its own slice, if a club ever asks.
- A club's own administrators renaming it themselves. The operator does it on
  request, for now.

## Suggested parts
One pull request.

## Questions for the project owner
1. **The operator log (a data model change).** **Recommended:** add
   "Renamed a club" to the log's list of actions. It needs a migration, but
   it only changes the list of choices: no table or column changes. Or log
   renames under an existing action, which would read wrongly.
2. **Tell the club?** **Recommended:** email the club's administrators, from
   the club as usual: "Your club is now called New Name on Race Times (it was
   Old Name). Your site's address hasn't changed." A rename is usually at the
   club's request, but it tells every administrator, not just the one who
   asked. Or send nothing.
3. **Contact email too?** **Recommended:** yes, in the same settings section,
   and logged as "Changed a club's contact email" (one more choice in
   question 1's migration). It's also fixed
   today, and a club's secretary changes more often than its name. Or name
   only, as asked.
