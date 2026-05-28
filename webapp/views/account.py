from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

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
        next_url = request.META.get('HTTP_REFERER') or '/'

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
