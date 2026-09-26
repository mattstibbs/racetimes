# Slice 16: changing your password

**Status: planned (2026-09-26). Waiting on the owner's answers to the
questions at the end.**

## Goal
A logged-in person can change their own password from **My account**, by
giving their current password and a new one. Today the only way to change a
password is the "Forgotten your password?" email link (slice 4), and the
operator's own is changed in the Django admin.

Nothing about the data changes: no model, migration, new dependency or
JavaScript. Django already has the pieces (`PasswordChangeForm`,
`update_session_auth_hash`); this slice wires them into the site the way the
rest of the account pages work.

## What gets built

### 1. The Change my password page
- **Address:** `/account/password/`, URL name `races:change_password`, in
  `races/account_views.py` next to the other account pages. `@login_required`,
  so the public is sent to log in.
- **Every address:** like the rest of My account, the account is one across
  every club, so the page works at any club's address and on the service's own
  address (so the operator can use it too). It shows no club's data.
- **Title and heading:** **Change my password** (naming rule from slice 15).
- **The form**, `ChangePasswordForm` in `races/forms.py`, a subclass of
  Django's `PasswordChangeForm`:

  | Field | Label |
  |---|---|
  | `old_password` | Current password |
  | `new_password1` | New password |
  | `new_password2` | New password again |

  - The new password must pass the site's `AUTH_PASSWORD_VALIDATORS`, the same
    rules as sign-up and a reset: at least 8 characters, not too like your
    name or email, not a common password, not all numbers. Django's help text
    for those rules is shown under the field, as on the reset page.
  - Django's form already marks the fields `autocomplete="current-password"`
    and `"new-password"`, so browsers' password managers offer to save the new
    one. Kept.
  - Under the form: "Forgotten your current password?" linking to the existing
    reset page, and **Back to my account**.
- **Guessing is limited like a login** (`races/throttle.py`). The current
  password is checked inside `throttle.guard`, as `DeleteAccountForm` does, so
  someone at an unattended, logged-in computer can't use this form to guess
  the password. A wrong current password counts as a failed login, and after
  10 the page answers "Too many failed logins. Try again in 15 minutes."
  like the login page, even with the right password. Wrong current password
  message: "That isn't your current password."
- **On success:**
  - The password is saved and `update_session_auth_hash` keeps this browser
    logged in.
  - **Every other browser logged in to the account is logged out.** Django
    does this already: each session stores a hash of the password, and a
    session whose hash no longer matches is ended on its next request. This
    is what you want if you're changing the password because someone else
    knows it. The page says so (see below).
  - Redirect to **My account** with the message "Your password has been
    changed. Any other devices logged in to your account have been logged
    out."
  - A log line: `INFO user 42 changed their password` (an id, never a name or
    email).
  - A confirmation email (item 3).
- **The superuser (operator)** can use the page like anyone else. The Django
  admin's own "Change password" link stays as it is.

### 2. My account links to it
- A new section on `templates/races/account.html`, after **My club
  memberships** and before **My data**:

  > **My password**
  >
  > [Change my password](…)

- The login page's "Forgotten your password?" link is unchanged.

### 3. An email saying the password was changed
- A new template, `templates/emails/password_changed.txt`, built through
  `races/notifications.email_to` (so `races/test_email_sender.py` stays happy)
  and sent with `notifications.send` after the change commits. At a club's
  address it comes as "<Club> via Race Times" with Reply-To the club, as every
  email does; on the service's own address, from Race Times.
- Subject: **Your Race Times password was changed**. Body, roughly:

  > Hello Pat,
  >
  > The password for your Race Times account, pat@example.com, was changed
  > on 26 September 2026 at 14:05. Any other devices logged in to your account
  > have been logged out.
  >
  > If this was you, there's nothing more to do.
  >
  > If it wasn't, reset your password now: <link to the reset page>. Then
  > reply to this email to tell the club.

- It never contains the password.
- A failure to send is a logged warning, as with every email, and the password
  change still stands.
- Question 1 asks whether to send it at all.

## Tests
New tests, as plain pytest functions, mostly in a new
`races/test_change_password.py`:
- The public is sent to log in; any logged-in person (a member, someone not
  yet a member of any club, the operator on the service's address) gets the
  form.
- A right current password and a valid new one: the new password works, the
  old one doesn't, this client is still logged in, a second client logged in
  to the same account is logged out, the success message shows on My account,
  and one email goes to the account's address with the right subject and no
  password in it.
- A wrong current password: nothing changes, the error shows, and it counts
  towards the throttle. After 10 wrong tries the right one is refused too
  (clock fixed with `throttle.now`).
- New passwords that don't match, are too short, or are too common: refused,
  nothing changes.
- The log line names the user's id, not their email or name.
- My account has the **My password** section and its link.
- Existing checks that list every URL are updated for the new one:
  `races/test_isolation.py` (in the URL list, and in `OWN_DATA` with the other
  account pages), which `races/test_legal.py`'s every-page cookie check
  also walks.

## Manual
- A new page, `manual/getting-started/changing-your-password.md`, listed in
  `mkdocs.yml` and `manual/index.md` after "Forgotten your password?": how to
  get there from **My account**, the rules for a new password, that other
  devices are logged out, the email you'll get, and that 10 wrong current
  passwords pause it for 15 minutes like the login.
- `getting-started/joining-a-club.md`'s **Your account** section mentions the
  new **My password** section.
- `getting-started/forgotten-password.md` gains one line pointing to the new
  page for people who know their password and just want a new one.
- `members/emails.md` lists the new email.
- **Screenshots:** a new `change-password.png`, and `account.png` regenerated
  since the page gains a section. `scripts/manual_screenshots/shots.js` gets a
  step for the new page (logged in as a seed account; the change isn't
  submitted, so the seed's password stays PASSWORD).

## Also
- `docs/decisions.md`: the throttle on the current password, logging out
  other devices, and the owner's answers below.
- `docs/plan.md`: the slice's entry and status.
- `CLAUDE.md`: the account pages' description in the Data protection bullet
  mentions `/account/password/`.

## Acceptance criteria
- A logged-in person can change their password from My account at any
  address, with their current password and a new one that passes the
  validators; afterwards only the new one works.
- This browser stays logged in; every other session for the account is
  logged out.
- A wrong current password is refused and counts towards the login throttle.
- The confirmation email is sent (subject to question 1), from the club, with
  no password in it.
- No model, migration, dependency or JavaScript is added.
- The manual's text, links and screenshots match the site; `mkdocs build
  --strict` passes; all tests pass.
- Checked by hand in a browser: changing a password, logging in with the new
  one, a second browser logged out, the page at 375px wide.

## Out of scope
- Changing your email address or name.
- Two-factor authentication.
- Forcing a password change (for example after an administrator invites
  someone), or password expiry.
- Administrators or the operator setting another person's password on the
  site; they can still send them to "Forgotten your password?".
- An email after a reset by link (the person has just used their email to do
  it).
- Changing the reset flow, or letting a reset lift a throttle lock (the owner
  decided against that in slice 11 part 4).

## Questions for the project owner
1. **Send an email when the password changes?** **Recommended: yes**, so that
   if someone else changed it, the owner hears about it and can reset it. It's
   one more email, only when they change their password.
2. **Log out other devices?** Django does this by default when a password
   changes. **Recommended: yes, and say so on the page**, since a leaked
   password is the main reason to change one. The alternative is keeping
   other sessions logged in, which needs extra code against Django's default.
3. **Where the link goes.** **Recommended:** a **My password** section on My
   account, between My club memberships and My data. Or a plain link under
   your name and email at the top of the page.
4. **The manual.** **Recommended:** a new page, "Changing your password",
   next to "Forgotten your password?". Or a section added to the existing
   "Joining a club, and your data" page.
