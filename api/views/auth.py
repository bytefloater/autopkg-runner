import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.challenge_auth import parse_argon2_hash, make_challenge_message

User = get_user_model()

_CHALLENGE_TTL_SECONDS = 300  # 5 minutes


class ChallengeView(APIView):
    """
    GET /api/auth/challenge/?username=<u>

    Returns a one-time challenge for zero-knowledge authentication.
    The response includes the Argon2id parameters from the user's stored hash
    so the client can locally derive the same hash and use it as an HMAC key.

    Returns 400 if the user's password is not yet Argon2id (they must log in
    via the web UI first to trigger the hash upgrade).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get('username', '').strip()
        if not username:
            return Response({'error': 'username is required'}, status=400)

        try:
            user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            # Don't reveal whether the user exists; return a generic error.
            return Response({'error': 'Cannot issue challenge for this account'}, status=400)

        params = parse_argon2_hash(user.password)
        if params is None:
            return Response(
                {'error': 'Account password must be upgraded. Log in via the web UI first.'},
                status=400,
            )

        from webapp.models import AuthChallenge
        nonce = secrets.token_hex(32)
        challenge_id = secrets.token_hex(32)
        expires_at = timezone.now() + timezone.timedelta(seconds=_CHALLENGE_TTL_SECONDS)

        AuthChallenge.objects.create(
            challenge_id=challenge_id,
            nonce=nonce,
            username=username,
            expires_at=expires_at,
        )

        return Response({
            'challenge_id': challenge_id,
            'nonce': nonce,
            'argon2_params': {
                'salt':        params.salt_b64,
                'time_cost':   params.time_cost,
                'memory_cost': params.memory_cost,
                'parallelism': params.parallelism,
                'hash_len':    params.hash_len,
            },
        })


class GetTokenView(APIView):
    """
    POST /api/auth/get_token/

    Zero-knowledge token issuance.  Body:
      { "username": "...", "challenge_id": "...", "response": "<hmac-hex>" }

    On success returns { "token_id": "...", "token_secret": "...", "username": "..." }.
    The token_secret is shown only once; store it securely.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username     = request.data.get('username', '').strip()
        challenge_id = request.data.get('challenge_id', '').strip()
        response_hex = request.data.get('response', '').strip()

        if not (username and challenge_id and response_hex):
            return Response({'error': 'username, challenge_id and response are required'}, status=400)

        from webapp.models import AuthChallenge, APIToken
        from api.challenge_auth import verify_challenge_response

        try:
            challenge = AuthChallenge.objects.get(
                challenge_id=challenge_id,
                username=username,
                used=False,
            )
        except AuthChallenge.DoesNotExist:
            return Response({'error': 'Invalid or expired challenge'}, status=401)

        if challenge.expires_at < timezone.now():
            return Response({'error': 'Challenge has expired'}, status=401)

        try:
            user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=401)

        if not verify_challenge_response(
            django_hash=user.password,
            nonce=challenge.nonce,
            username=username,
            challenge_id=challenge_id,
            client_response=response_hex,
        ):
            return Response({'error': 'Invalid credentials'}, status=401)

        challenge.used = True
        challenge.save(update_fields=['used'])

        token = APIToken.objects.filter(user=user).order_by('-created').first()
        if not token:
            token = APIToken.objects.create(user=user, name='Default')

        return Response({
            'token_id':     token.token_id,
            'token_secret': token.decrypted_secret,
            'username':     user.username,
        })


class CheckTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'valid': True, 'username': request.user.username})
