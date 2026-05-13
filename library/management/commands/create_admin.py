import getpass

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from library.models import UserProfile


class Command(BaseCommand):
    help = "Create or update an admin user."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--password")

    def handle(self, *args, **options):
        username = options["username"].strip()
        email = options["email"].strip()
        password = options.get("password") or getpass.getpass("Password: ")

        if not username or not email or not password:
            raise CommandError("Username, email, and password are required.")

        existing_username = User.objects.filter(username__iexact=username).first()
        existing_email = User.objects.filter(email__iexact=email).first()

        if existing_username and existing_email and existing_username.id != existing_email.id:
            raise CommandError("Username and email belong to different users.")

        user = existing_username or existing_email
        created = user is None

        if created:
            user = User.objects.create_user(username=username, email=email, password=password)
        else:
            user.username = username
            user.email = email
            user.set_password(password)

        user.is_staff = True
        user.is_superuser = True
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.access_status = UserProfile.ACCESS_APPROVED
        profile.save(update_fields=["access_status", "updated_at"])

        if created:
            self.stdout.write(self.style.SUCCESS("Admin user created."))
        else:
            self.stdout.write(self.style.SUCCESS("Admin user updated."))
