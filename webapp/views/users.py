import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import TemplateView

from webapp.perms import UserManagerRequired

User = get_user_model()


def _generate_password() -> str:
    return secrets.token_urlsafe(16)


def _save_permissions(user, request):
    """Persist the four permission checkboxes for a non-superuser."""
    if user.is_superuser:
        return
    from webapp.models import UserPermission
    row, _ = UserPermission.objects.get_or_create(user=user)
    row.can_manage_users = request.POST.get('can_manage_users') == 'on'
    row.can_trigger_runs = request.POST.get('can_trigger_runs') == 'on'
    row.can_edit_config  = request.POST.get('can_edit_config') == 'on'
    row.can_view_runs    = request.POST.get('can_view_runs') == 'on'
    row.save()


class UsersView(UserManagerRequired, TemplateView):
    template_name = 'webapp/users.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/users.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'config' if getattr(self.request, 'is_mobile', False) else 'users'
        users = list(User.objects.select_related('permissions_ext').order_by('username'))
        current_pk = self.request.user.pk
        for u in users:
            setattr(u, 'is_self', u.pk == current_pk)
            setattr(u, 'perms_ext', getattr(u, 'permissions_ext', None))
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
            if not is_admin:
                _save_permissions(user, request)
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
                user.email = email
                user.save(update_fields=['email'])
                messages.success(request, 'Your email address has been updated.')
            else:
                if user.is_superuser and not is_admin:
                    remaining = User.objects.filter(is_superuser=True).exclude(pk=user.pk).count()
                    if remaining == 0:
                        messages.error(request, 'Cannot remove the last administrator account.')
                        return redirect('users')

                user.is_active    = is_active
                user.is_superuser = is_admin
                user.is_staff     = is_admin
                user.email        = email
                user.save(update_fields=['is_active', 'is_superuser', 'is_staff', 'email'])
                _save_permissions(user, request)
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


class UserEditView(UserManagerRequired, TemplateView):
    """Mobile-only subpage for editing a single user."""
    template_name = 'webapp/mobile/user_edit.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        edit_user = get_object_or_404(User, pk=kwargs['pk'])
        ctx['active_tab']  = 'config'
        ctx['edit_user']   = edit_user
        ctx['is_self']     = (edit_user.pk == self.request.user.pk)
        ctx['perms_ext']   = getattr(edit_user, 'permissions_ext', None)
        ctx['reset_creds'] = self.request.session.pop('reset_creds', None)
        return ctx

    def post(self, request, pk):
        edit_user = get_object_or_404(User, pk=pk)
        action    = request.POST.get('action', 'update')

        if action == 'update':
            email     = request.POST.get('email', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            is_admin  = request.POST.get('is_superuser') == 'on'

            if edit_user == request.user:
                edit_user.email = email
                edit_user.save(update_fields=['email'])
                messages.success(request, 'Your email address has been updated.')
            else:
                if edit_user.is_superuser and not is_admin:
                    remaining = User.objects.filter(is_superuser=True).exclude(pk=edit_user.pk).count()
                    if remaining == 0:
                        messages.error(request, 'Cannot remove the last administrator account.')
                        return redirect('user-edit', pk=pk)

                edit_user.is_active    = is_active
                edit_user.is_superuser = is_admin
                edit_user.is_staff     = is_admin
                edit_user.email        = email
                edit_user.save(update_fields=['is_active', 'is_superuser', 'is_staff', 'email'])
                _save_permissions(edit_user, request)
                messages.success(request, f'User "{edit_user.username}" updated.')
            return redirect('user-edit', pk=pk)

        elif action == 'reset_password':
            if edit_user == request.user:
                messages.error(request, 'Use "Change Password" in the user menu to change your own password.')
                return redirect('user-edit', pk=pk)
            password = _generate_password()
            edit_user.set_password(password)
            edit_user.save(update_fields=['password'])
            request.session['reset_creds'] = {
                'username': edit_user.username,
                'password': password,
            }
            return redirect('user-edit', pk=pk)

        elif action == 'delete':
            if edit_user == request.user:
                messages.error(request, 'You cannot delete your own account.')
                return redirect('user-edit', pk=pk)
            if edit_user.is_superuser:
                remaining = User.objects.filter(is_superuser=True).exclude(pk=edit_user.pk).count()
                if remaining == 0:
                    messages.error(request, 'Cannot delete the last administrator account.')
                    return redirect('user-edit', pk=pk)
            username = edit_user.username
            edit_user.delete()
            messages.success(request, f'User "{username}" deleted.')
            return redirect('users')

        return redirect('users')
