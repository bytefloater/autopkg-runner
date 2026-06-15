"""
Permission constants, helpers, and view mixins for the granular role system.

Four permission flags exist on UserPermission. Superusers bypass all checks
and never need a row. Absence of a row is treated as all-False.
"""
from __future__ import annotations

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render

PERM_MANAGE_USERS = 'can_manage_users'
PERM_TRIGGER_RUNS = 'can_trigger_runs'
PERM_EDIT_CONFIG  = 'can_edit_config'
PERM_VIEW_RUNS    = 'can_view_runs'

ALL_PERMS = (PERM_MANAGE_USERS, PERM_TRIGGER_RUNS, PERM_EDIT_CONFIG, PERM_VIEW_RUNS)


def user_has_perm(user, perm: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return bool(getattr(user.permissions_ext, perm, False))
    except ObjectDoesNotExist:
        return False


def get_user_perms(user) -> dict:
    """Return {perm_name: bool} for all four flags."""
    if not user or not user.is_authenticated:
        return {p: False for p in ALL_PERMS}
    if user.is_superuser:
        return {p: True for p in ALL_PERMS}
    try:
        row = user.permissions_ext
        return {p: bool(getattr(row, p, False)) for p in ALL_PERMS}
    except ObjectDoesNotExist:
        return {p: False for p in ALL_PERMS}


def _denied_response(request):
    tmpl = (
        'webapp/mobile/permission_denied.html'
        if getattr(request, 'is_mobile', False)
        else 'webapp/permission_denied.html'
    )
    return render(request, tmpl, {}, status=403)


# ---------------------------------------------------------------------------
# CBV mixins
# ---------------------------------------------------------------------------

class PermissionRequiredMixin(LoginRequiredMixin):
    """
    Base mixin that checks one or more permission flags before dispatching.

    Set required_perm to a single constant or a tuple of constants.
    The user passes if they have ANY of the listed permissions.
    """
    required_perm: str | tuple = ()

    def _check_perm(self, request) -> bool:
        perms = (self.required_perm,) if isinstance(self.required_perm, str) else self.required_perm
        return any(user_has_perm(request.user, p) for p in perms)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not self._check_perm(request):
            return _denied_response(request)
        return super().dispatch(request, *args, **kwargs)


class RunAccessRequired(PermissionRequiredMixin):
    """Passes for can_view_runs OR can_trigger_runs."""
    required_perm = (PERM_VIEW_RUNS, PERM_TRIGGER_RUNS)


class RunManagerRequired(PermissionRequiredMixin):
    required_perm = PERM_TRIGGER_RUNS


class ConfigEditorRequired(PermissionRequiredMixin):
    required_perm = PERM_EDIT_CONFIG


class UserManagerRequired(PermissionRequiredMixin):
    required_perm = PERM_MANAGE_USERS


# ---------------------------------------------------------------------------
# FBV decorator
# ---------------------------------------------------------------------------

def perm_required(*perms):
    """Decorator for function-based views (e.g. run_stream)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not any(user_has_perm(request.user, p) for p in perms):
                return _denied_response(request)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
