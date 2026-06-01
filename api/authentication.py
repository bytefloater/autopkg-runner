from typing import Optional

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class APITokenAuthentication(BaseAuthentication):
    """Authenticate requests using a named APIToken from webapp.models."""

    keyword = 'Token'

    def authenticate(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', '').split()
        if not auth or auth[0].lower() != self.keyword.lower():
            return None
        if len(auth) != 2:
            raise AuthenticationFailed('Invalid token header. Expected: Token <key>')

        return self._authenticate_key(auth[1])

    def authenticate_header(self, request) -> Optional[str]: # type: ignore
        return self.keyword

    def _authenticate_key(self, key):
        from webapp.models import APIToken
        try:
            token = APIToken.objects.select_related('user').get(key=key)
        except APIToken.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked token.')

        if not token.user.is_active:
            raise AuthenticationFailed('User account is disabled.')

        return (token.user, token)
