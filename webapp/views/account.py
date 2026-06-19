from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.conf import settings as django_settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View


def _safe_redirect(url: str, request, fallback: str = '/') -> str:
    """Return *url* if it is safe to redirect to, otherwise *fallback*."""
    if url_has_allowed_host_and_scheme(url, allowed_hosts=request.get_host(), require_https=request.is_secure()):
        return url
    return fallback


class MobileAwareLoginView(DjangoLoginView):
    """Django's LoginView extended for zero-knowledge challenge-response login.

    When the browser JS is present it intercepts the form submit, fetches a
    challenge from /api/auth/challenge/, runs Argon2id locally, and posts
    challenge_id + response instead of the plaintext password.

    Falls back to the standard Django password POST when challenge_id is absent
    (e.g. JS disabled), so compatibility is preserved.
    """

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/login.html']
        return ['webapp/login.html']

    def post(self, request, *args, **kwargs):
        challenge_id = request.POST.get('challenge_id', '').strip()
        response_hex = request.POST.get('response', '').strip()
        username     = request.POST.get('username', '').strip()

        if challenge_id and response_hex:
            user = authenticate(
                request,
                username=username,
                challenge_id=challenge_id,
                response=response_hex,
            )
            if user is not None:
                auth_login(request, user, backend='webapp.auth_backends.ChallengeResponseBackend')
                next_url = _safe_redirect(
                    request.POST.get('next', ''), request,
                    fallback=django_settings.LOGIN_REDIRECT_URL,
                )
                return redirect(next_url)

            # Invalid ZK response — re-render login form with error flag.
            # We set an attribute the template checks to show the error banner.
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form, zk_failed=True))

        return super().post(request, *args, **kwargs)

_MIN_PASSWORD_LENGTH = 8


class ChangePasswordView(LoginRequiredMixin, View):
    """Allows the currently logged-in user to change their own password.

    Requires the current password for verification so an unattended session
    cannot be hijacked to set a new password silently.  Uses
    ``update_session_auth_hash`` so the user stays logged in after the change.
    """

    def post(self, request):
        current = request.POST.get('current_password', '')
        new_pw  = request.POST.get('new_password', '')
        confirm = request.POST.get('confirm_password', '')
        user    = request.user
        next_url = _safe_redirect(request.META.get('HTTP_REFERER', ''), request)

        if not user.check_password(current):
            messages.error(request, 'Current password is incorrect.')
            return redirect(next_url)

        if len(new_pw) < _MIN_PASSWORD_LENGTH:
            messages.error(request, f'New password must be at least {_MIN_PASSWORD_LENGTH} characters.')
            return redirect(next_url)

        if new_pw != confirm:
            messages.error(request, 'New passwords do not match.')
            return redirect(next_url)

        user.set_password(new_pw)
        user.save(update_fields=['password'])
        update_session_auth_hash(request, user)  # keep session valid after pw change
        messages.success(request, 'Password changed successfully.')
        return redirect(next_url)
