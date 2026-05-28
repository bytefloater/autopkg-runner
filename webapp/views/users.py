import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

User = get_user_model()


def _generate_password() -> str:
    return secrets.token_urlsafe(16)


class UsersView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/users.html'

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # Only superusers may manage accounts.
        if request.user.is_authenticated and not request.user.is_superuser:
            messages.error(request, 'Administrator access required.')
            return redirect('dashboard')
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'users'
        users = list(User.objects.order_by('username'))
        current_pk = self.request.user.pk
        for u in users:
            u.is_self = (u.pk == current_pk)
        ctx['users'] = users
        ctx['new_user_creds'] = self.request.session.pop('new_user_creds', None)
        ctx['reset_creds']    = self.request.session.pop('reset_creds', None)
        return ctx

    def post(self, request):
        action = request.POST.get('action')

        if action == 'create':
            username = request.POST.get('username', '').strip()
            email    = request.POST.get('email', '').strip()
            is_admin = request.POST.get('is_superuser') == 'on'

            if not username:
                messages.error(request, 'Username is required.')
                return redirect('users')
            if User.objects.filter(username=username).exists():
                messages.error(request, f'Username "{username}" is already taken.')
                return redirect('users')

            password = _generate_password()
            user = User.objects.create_superuser(username=username, email=email, password=password) \
                   if is_admin else \
                   User.objects.create_user(username=username, email=email, password=password)
            request.session['new_user_creds'] = {
                'username': user.username,
                'password': password,
                'role': 'Administrator' if is_admin else 'User',
            }

        elif action == 'update':
            user_id   = request.POST.get('user_id')
            is_active = request.POST.get('is_active') == 'on'
            is_admin  = request.POST.get('is_superuser') == 'on'
            email     = request.POST.get('email', '').strip()

            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                return redirect('users')

            if user == request.user:
                # Self-edit: only allow email changes; ignore role/active inputs.
                user.email = email
                user.save(update_fields=['email'])
                messages.success(request, 'Your email address has been updated.')
            else:
                # Prevent removing the last superuser.
                if user.is_superuser and not is_admin:
                    remaining = User.objects.filter(is_superuser=True).exclude(pk=user.pk).count()
                    if remaining == 0:
                        messages.error(request, 'Cannot remove the last administrator account.')
                        return redirect('users')

                user.is_active    = is_active
                user.is_superuser = is_admin
                user.is_staff     = is_admin  # keep staff in sync with superuser
                user.email        = email
                user.save(update_fields=['is_active', 'is_superuser', 'is_staff', 'email'])
                messages.success(request, f'User "{user.username}" updated.')

        elif action == 'reset_password':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                return redirect('users')

            if user == request.user:
                messages.error(request, 'Use "Change Password" in the user menu to change your own password.')
                return redirect('users')

            password = _generate_password()
            user.set_password(password)
            user.save(update_fields=['password'])
            request.session['reset_creds'] = {
                'username': user.username,
                'password': password,
            }

        elif action == 'delete':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
                return redirect('users')

            if user == request.user:
                messages.error(request, 'You cannot delete your own account.')
                return redirect('users')

            if user.is_superuser:
                remaining = User.objects.filter(is_superuser=True).exclude(pk=user.pk).count()
                if remaining == 0:
                    messages.error(request, 'Cannot delete the last administrator account.')
                    return redirect('users')

            username = user.username
            user.delete()
            messages.success(request, f'User "{username}" deleted.')

        return redirect('users')
