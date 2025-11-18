# models.py - Optional extension to store additional user information
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserProfile(AbstractUser):
    """
    Extended user profile to store eFile registration information.
    """

    # TODO(brycew): what happens if someone is trying to do stuff in multiple jurisdictions?
    tyler_jurisdiction = models.CharField(max_length=20)
    tyler_user_id = models.CharField(max_length=100, blank=True, null=True)

    # TODO(brycew): uncomment when https://github.com/SuffolkLITLab/EfileProxyServer/issues/334 is in
    # token_expires_at = models.DateTimeField(blank=True, null=True)

    # Communication Preferences
    email_updates = models.BooleanField(default=False)
    text_updates = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

# Don't forget to run migrations if you add this model:
# python manage.py makemigrations
# python manage.py migrate --run-syncdb
