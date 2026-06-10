from rest_framework.permissions import BasePermission
from webapp.perms import user_has_perm, PERM_TRIGGER_RUNS, PERM_VIEW_RUNS


class CanTriggerRuns(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and user_has_perm(request.user, PERM_TRIGGER_RUNS))


class CanViewRuns(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and (
                user_has_perm(request.user, PERM_VIEW_RUNS) or
                user_has_perm(request.user, PERM_TRIGGER_RUNS)
            )
        )
