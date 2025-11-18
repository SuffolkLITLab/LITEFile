import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from efile.models import UserProfile
from efile.utils.proxy_connection import auth_with_tyler_api

logger = logging.getLogger(__name__)
User = get_user_model()


class SuffolkEFileBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.info("Trying auth?")

        jurisdiction = kwargs.get("jurisdiction", self._get_jurisdiction_from_request(request))
        if not username or not password or not jurisdiction:
            return None

        try:
            auth_data = auth_with_tyler_api(username, password, jurisdiction)
            request.session["auth_tokens"] = auth_data["tokens"]
            if not auth_data:
                logger.info("Tyler auth failed for user %s", username)
                return None

            logger.info("Auth data: %s", auth_data)

            user = self._get_or_create_user(username, auth_data, jurisdiction)
            # TODO(brycew): actually write these?
            # self._update_user_profile(user, auth_data, jurisdiction)
            # if request:
            #    self._store_tokens_in_session(request, auth_data, jurisdiction)

            logger.info("Successfully auth'd user: %s", username)
            return user
        except Exception:
            logger.exception("Error during auth for user: %s", username)
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def _get_jurisdiction_from_request(self, request):
        jurisdiction = request.GET.get("jurisdiction")
        if jurisdiction:
            return jurisdiction.lower()
        segments = request.path.split("/")
        # TODO(brycew): okay, maybe it makes sense to add an extra segment to the path...
        if len(segments) >= 2 and segments[1] not in ["api", "options", "login", "register", "upload", "review"]:
            return segments[1].lower()
        return None

    def _get_or_create_user(self, username, auth_data, jurisdiction):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # TODO(brycew): should only check username
            user = None
            pass

        if not user:
            user_data = self._extract_user_data(auth_data, username, jurisdiction)
            user = User.objects.create_user(
                username=username,
                email=user_data.get("email", username),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
            )

            logger.info("Created new user: %s", username)
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.tyler_token = auth_data.get("tyler_token")
            profile.tyler_user_id = auth_data.get("user_id")
        return user

    def _extract_user_data(self, auth_data, username, jurisdiction):
        # TODO(bryce): continue
        user_data = {"email": username}
        if auth_data:
            user_data["user_id"] = auth_data["tokens"][f"TYLER-ID-{jurisdiction.upper()}"]
            user_data["tyler_token"] = auth_data["tokens"][f"TYLER-TOKEN-{jurisdiction.upper()}"]
        return user_data
