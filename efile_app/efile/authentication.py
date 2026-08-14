import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from efile.utils.account_ids import jurisdiction_account_username
from efile.utils.jurisdiction_stuff import get_jurisdiction_from_request
from efile.utils.proxy_connection import auth_with_tyler_api

logger = logging.getLogger(__name__)
User = get_user_model()


class SuffolkEFileBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.info("Trying auth?")

        jurisdiction = kwargs.get("jurisdiction", get_jurisdiction_from_request(request))
        if not username or not password or not jurisdiction:
            return None

        try:
            auth_data = auth_with_tyler_api(username, password, jurisdiction)
            if not auth_data or "tokens" not in auth_data:
                logger.info("Tyler auth failed for user %s", username)
                return None

            request.session["auth_tokens"] = auth_data["tokens"]

            logger.info("Auth data: %s", auth_data)

            user = self._get_or_create_user(username, auth_data, jurisdiction)
            # TODO(brycew): actually write these?
            # if request:
            #    self._store_tokens_in_session(request, auth_data, jurisdiction)

            logger.info("Successfully auth'd user: %s", username)
            request.session["user_email"] = user.email
            return user
        except Exception:
            logger.exception("Error during auth for user: %s", username)
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _get_or_create_user(self, username, auth_data, jurisdiction):
        user = User.objects.filter(
            tyler_username__iexact=username,
            tyler_jurisdiction__iexact=jurisdiction,
        ).first()
        if user is None:
            # Accounts created before ``tyler_username`` was introduced stored the
            # Tyler login directly in Django's username field.
            user = User.objects.filter(
                username__iexact=username,
                tyler_jurisdiction__iexact=jurisdiction,
                tyler_username="",
            ).first()

        user_data = self._extract_user_data(auth_data, username, jurisdiction)
        if not user:
            user = User.objects.create_user(
                username=jurisdiction_account_username(username, jurisdiction),
                tyler_jurisdiction=jurisdiction,
                tyler_username=username,
                tyler_user_id=user_data.get("user_id", None),
                email=user_data.get("email", username),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
            )
        else:
            user.tyler_username = username
            user.tyler_user_id = user_data.get("user_id", None)
            user.email = user_data.get("email", username)
            user.save(update_fields=["tyler_username", "tyler_user_id", "email", "updated_at"])

        logger.info("Authenticated local account %s for %s", user.pk, jurisdiction)
        return user

    def _extract_user_data(self, auth_data, username, jurisdiction):
        user_data = {"email": username}
        if auth_data:
            user_data["user_id"] = auth_data["tokens"][f"TYLER-ID-{jurisdiction.upper()}"]
            user_data["tyler_token"] = auth_data["tokens"][f"TYLER-TOKEN-{jurisdiction.upper()}"]
        return user_data

    @staticmethod
    def logout(request):
        """Log the current user out. Here for symmetry.

        If logout fails, will raise an exception.
        """
        from django.contrib.auth import logout
        from django.contrib.messages.api import get_messages

        # Clear any existing messages first
        storage = get_messages(request)
        for _message in storage:
            pass  # This consumes all messages

        logout(request)
        session_keys_to_keep = ["csrftoken"]
        session_data = {k: v for k, v in request.session.items() if k in session_keys_to_keep}
        request.session.clear()
        request.session.update(session_data)

    @staticmethod
    def password_reset(request):
        """Calls the efile-proxy's "reset password" API, which
        sends an email from Tyler to reset the password.
        """
