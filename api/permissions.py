from typing import Literal

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from webapp.perms import user_has_perm, PERM_TRIGGER_RUNS, PERM_VIEW_RUNS


class CanTriggerRuns(BasePermission):
    def has_permission(self, request, view) -> Literal[True]:
        if not (request.user and user_has_perm(request.user, PERM_TRIGGER_RUNS)):
            raise PermissionDenied()
        return True


class CanViewRuns(BasePermission):
    def has_permission(self, request, view) -> Literal[True]:
        if not (request.user and (
            user_has_perm(request.user, PERM_VIEW_RUNS) or
            user_has_perm(request.user, PERM_TRIGGER_RUNS)
        )):
            raise PermissionDenied()
        return True
