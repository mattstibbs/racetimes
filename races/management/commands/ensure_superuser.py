"""Create the first staff login from environment variables, if it is missing.

Run on every deploy (see build.sh). A host's free tier may have no shell to
run `createsuperuser` in, so the username and password are set as environment
variables on the host instead. The command only ever creates the account: it
never changes an existing one, so a password changed later in the admin stays
changed, and removing the variables afterwards is harmless.
"""

import os

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create a superuser from DJANGO_SUPERUSER_USERNAME and "
        "DJANGO_SUPERUSER_PASSWORD, unless that user already exists."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not username or not password:
            self.stdout.write("No DJANGO_SUPERUSER_USERNAME/PASSWORD set; nothing to do.")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"User {username!r} already exists; left unchanged.")
            return

        user = User(username=username, email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""))
        try:
            # The same rules as any other password: a weak one fails the
            # deploy with the reason, rather than going live.
            password_validation.validate_password(password, user)
        except ValidationError as error:
            raise CommandError("DJANGO_SUPERUSER_PASSWORD: " + " ".join(error.messages))
        User.objects.create_superuser(username=username, email=user.email, password=password)
        self.stdout.write(f"Created superuser {username!r}.")
