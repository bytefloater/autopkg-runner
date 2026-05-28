import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import TemplateView, View

from webapp.notifier_types import NOTIFIER_TYPES, type_choices


class NotificationsView(LoginRequiredMixin, TemplateView):
    """List all configured notifiers."""

    template_name = 'webapp/notifications.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/notifications.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Notifier
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']   = 'config'
        ctx['notifiers']    = Notifier.objects.all()
        ctx['type_choices'] = type_choices()
        ctx['type_schemas'] = json.dumps(NOTIFIER_TYPES)
        return ctx

    def post(self, request):
        """Quick-create a new notifier (name + type only; user edits details next)."""
        from webapp.models import Notifier
        name  = request.POST.get('name', '').strip()
        ntype = request.POST.get('notifier_type', '')
        if not name or ntype not in NOTIFIER_TYPES:
            messages.error(request, 'A name and valid type are required.')
            return redirect('config-notifications')
        notifier = Notifier.objects.create(name=name, notifier_type=ntype)
        return redirect('notifier-edit', pk=notifier.pk)


class NotifierEditView(LoginRequiredMixin, TemplateView):
    """Edit a single notifier's settings."""

    template_name = 'webapp/notifier_edit.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/notifier_edit.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Notifier
        ctx = super().get_context_data(**kwargs)
        notifier = get_object_or_404(Notifier, pk=kwargs['pk'])
        schema   = NOTIFIER_TYPES.get(notifier.notifier_type, {})
        ctx['active_tab'] = 'config'
        ctx['notifier']   = notifier
        ctx['schema']     = schema
        ctx['fields']     = schema.get('fields', [])
        return ctx

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        schema   = NOTIFIER_TYPES.get(notifier.notifier_type, {})
        fields   = schema.get('fields', [])

        notifier.name    = request.POST.get('name', notifier.name).strip()
        notifier.enabled = bool(request.POST.get('enabled'))

        cfg = {}
        for field in fields:
            key   = field['key']
            ftype = field['type']
            if ftype == 'bool':
                cfg[key] = bool(request.POST.get(key))
            else:
                val = request.POST.get(key, '')
                # Don't overwrite a saved password with an empty POST value.
                # Use decrypted_config so we get the plaintext — save() will
                # re-encrypt it when the notifier is written back.
                if ftype == 'password' and not val:
                    cfg[key] = notifier.decrypted_config.get(key, '')
                else:
                    cfg[key] = val

        notifier.config = cfg
        notifier.save()
        messages.success(request, f'Notifier "{notifier.name}" saved.')
        return redirect('config-notifications')


class NotifierDeleteView(LoginRequiredMixin, View):
    """POST-only delete."""

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        name = notifier.name
        notifier.delete()
        messages.success(request, f'Notifier "{name}" deleted.')
        return redirect('config-notifications')


class NotifierToggleView(LoginRequiredMixin, View):
    """POST-only enable/disable toggle (used by the list view)."""

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        notifier.enabled = not notifier.enabled
        notifier.save(update_fields=['enabled'])
        return redirect('config-notifications')
