import importlib
import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from webapp.perms import ConfigEditorRequired
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import TemplateView, View

logger = logging.getLogger('autopkg_runner')

from webapp.notifier_types import NOTIFIER_TYPES, type_choices


class NotificationsView(ConfigEditorRequired, TemplateView):
    """List all configured notifiers."""

    template_name = 'webapp/notifications.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/notifications.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Notifier, Setting
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']              = 'config'
        ctx['notifiers']               = Notifier.objects.all()
        ctx['type_choices']            = type_choices()
        ctx['type_schemas']            = json.dumps(NOTIFIER_TYPES)
        ctx['pwa_base_url']            = Setting.get('notify.pwa_base_url', '')
        ctx['share_link_expiry_days']  = Setting.get('notify.share_link_expiry_days', '')
        return ctx

    def post(self, request):
        # -- Quick-create a new notifier (name + type only) ---------------------
        from webapp.models import Notifier
        name  = request.POST.get('name', '').strip()
        ntype = request.POST.get('notifier_type', '')
        if not name or ntype not in NOTIFIER_TYPES:
            messages.error(request, 'A name and valid type are required.')
            return redirect('config-notifications')
        notifier = Notifier.objects.create(name=name, notifier_type=ntype)
        return redirect('notifier-edit', pk=notifier.pk)


class NotifierEditView(ConfigEditorRequired, TemplateView):
    """Edit a single notifier's settings."""

    template_name = 'webapp/notifier_edit.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/notifier_edit.html']
        return [self.template_name]

    # Variables available in message / title templates - shown in the UI reference.
    # Second element is the NOTIFICATIONS_VIEW translation key for the description.
    TEMPLATE_VARIABLES = [
        ('status',       'TMPLT_STATUS_VARHINT'),
        ('status_emoji', 'TMPLT_STATUS_EMOJI_VARHINT'),
        ('imports',      'TMPLT_IMPORTS_VARHINT'),
        ('failures',     'TMPLT_FAILURES_VARHINT'),
        ('downloads',    'TMPLT_DOWNLOADS_VARHINT'),
        ('duration',     'TMPLT_DURATION_VARHINT'),
        ('share_url',           'TMPLT_SHARE_URL_VARHINT'),
        ('share_link:"text"',   'TMPLT_SHARE_LINK_VARHINT'),
        ('run_id',              'TMPLT_RUN_ID_VARHINT'),
        ('triggered_by', 'TMPLT_TRIGGERED_BY_VARHINT'),
        ('date',         'TMPLT_DATE_VARHINT'),
        ('time',         'TMPLT_TIME_VARHINT'),
    ]

    def get_context_data(self, **kwargs):
        from webapp import translations as _trans
        from webapp.models import Notifier, Setting, WebPushSubscription
        ctx = super().get_context_data(**kwargs)
        notifier = get_object_or_404(Notifier, pk=kwargs['pk'])
        schema   = NOTIFIER_TYPES.get(notifier.notifier_type, {})
        ctx['active_tab']        = 'config'
        ctx['notifier']          = notifier
        ctx['schema']            = schema
        ctx['fields']            = schema.get('fields', [])
        ctx['decrypted_config']  = notifier.decrypted_config

        # Resolve variable hint descriptions from the active language.
        # Subscript access (not .get()) lets TranslationProxy.__missing__ fire for
        # absent or empty-valued keys, returning the dotted key path as a visible
        # fallback - consistent with how {{ t.X.Y }} behaves everywhere else.
        try:
            lang = Setting.get('ui.language', 'en-US')
        except Exception:
            lang = 'en-US'
        notif_t = _trans.load(lang)['NOTIFICATIONS_VIEW']
        ctx['variables'] = [
            (var, notif_t[t_key])
            for var, t_key in self.TEMPLATE_VARIABLES
        ]

        if notifier.notifier_type == 'email':
            from pathlib import Path
            from django.conf import settings as _settings
            tdir = Path(_settings.BASE_DIR) / 'resources' / 'email_templates'
            ctx['email_templates'] = sorted(p.stem for p in tdir.glob('*.html')) if tdir.exists() else []

        if notifier.notifier_type == 'webpush':
            subs = list(WebPushSubscription.objects.filter(notifier=notifier).order_by('created_at'))
            ctx['webpush_subscriptions'] = subs
            ctx['webpush_subs_json'] = json.dumps([
                {'id': str(s.pk), 'label': s.device_label or '', 'date': s.created_at.strftime('%-d %b %Y') if s.created_at else '', 'endpoint': s.endpoint}
                for s in subs
            ])
            ctx['vapid_public_key']       = Setting.get('webpush.vapid_public_key', '')
            ctx['vapid_configured']       = bool(ctx['vapid_public_key'])

        return ctx

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        schema   = NOTIFIER_TYPES.get(notifier.notifier_type, {})
        fields   = schema.get('fields', [])

        notifier.name             = request.POST.get('name', notifier.name).strip()
        notifier.enabled          = bool(request.POST.get('enabled'))
        notifier.title_template   = request.POST.get('title_template', '').strip()
        notifier.message_template = request.POST.get('message_template', '').strip()

        cfg = {}
        for field in fields:
            key   = field['key']
            ftype = field['type']
            if ftype == 'bool':
                cfg[key] = bool(request.POST.get(key))
            else:
                val = request.POST.get(key, '')
                # Don't overwrite a saved password with an empty POST value.
                # Use decrypted_config so we get the plaintext - save() will
                # re-encrypt it when the notifier is written back.
                if ftype == 'password' and not val:
                    cfg[key] = notifier.decrypted_config.get(key, '')
                else:
                    cfg[key] = val

        notifier.config = cfg
        notifier.save()
        messages.success(request, f'Notifier "{notifier.name}" saved.')
        return redirect('config-notifications')


class NotifierDeleteView(ConfigEditorRequired, View):
    """POST-only delete."""

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        name = notifier.name
        notifier.delete()
        messages.success(request, f'Notifier "{name}" deleted.')
        return redirect('config-notifications')


class NotifierToggleView(ConfigEditorRequired, View):
    """POST-only enable/disable toggle (used by the list view)."""

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)
        notifier.enabled = not notifier.enabled
        notifier.save(update_fields=['enabled'])
        return redirect('config-notifications')


class NotifierTestView(ConfigEditorRequired, View):
    """
    POST-only endpoint: send a test notification via a saved notifier.

    Uses the credentials currently saved in the database.  Returns JSON so
    the UI can show inline success / failure feedback without a page reload.

    Response:
        {"success": true,  "message": "Test sent successfully."}
        {"success": false, "message": "<error description>"}
    """

    def post(self, request, pk):
        from webapp.models import Notifier
        notifier = get_object_or_404(Notifier, pk=pk)

        module_path = f"notifiers.{notifier.notifier_type}"
        try:
            provider_mod = importlib.import_module(module_path)
        except ModuleNotFoundError:
            return JsonResponse(
                {'success': False, 'message': f"Notifier module '{module_path}' not found."},
                status=400,
            )

        _send = getattr(provider_mod, 'send', None)
        if _send is None:
            return JsonResponse(
                {'success': False, 'message': f"Module '{module_path}' has no send() function."},
                status=400,
            )

        cfg = {**notifier.decrypted_config, '_notifier_pk': str(notifier.pk)}

        try:
            _send(
                configuration=cfg,
                message=(
                    "This is a test notification from AutoPkg Runner. "
                    "If you received this, your notifier is configured correctly."
                ),
                title="AutoPkg Runner - Test",
            )
        except Exception as exc:
            logger.warning('Test notification failed: %s', exc)
            return JsonResponse(
                {'success': False, 'message': 'Notification failed. Check your notifier configuration and server logs.'},
                status=500,
            )

        return JsonResponse({'success': True, 'message': 'Test notification sent.'})


class NotificationSettingsView(ConfigEditorRequired, TemplateView):
    """Edit global notification settings (App URL for share links)."""

    template_name = 'webapp/notification_settings.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/notification_settings.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Setting
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']             = 'config'
        ctx['pwa_base_url']           = Setting.get('notify.pwa_base_url', '')
        ctx['share_link_expiry_days'] = Setting.get('notify.share_link_expiry_days', '')
        return ctx

    def post(self, request):
        from webapp.models import Setting
        Setting.set('notify.pwa_base_url', request.POST.get('notify.pwa_base_url', '').strip())
        expiry = request.POST.get('notify.share_link_expiry_days', '').strip()
        Setting.set('notify.share_link_expiry_days', expiry)
        messages.success(request, 'Settings saved.')
        return redirect('notification-settings')


class WebPushVapidKeyView(ConfigEditorRequired, View):
    """Return the VAPID public key so the browser can subscribe."""

    def get(self, request):
        from webapp.models import Setting
        key = Setting.get('webpush.vapid_public_key', '').strip()
        if not key:
            return JsonResponse({'error': 'VAPID keys not configured.'}, status=503)
        return JsonResponse({'public_key': key})


class WebPushSubscribeView(ConfigEditorRequired, View):
    """Register a new browser push subscription for a WebPush notifier."""

    def post(self, request, pk):
        from webapp.models import Notifier, WebPushSubscription
        notifier = get_object_or_404(Notifier, pk=pk)

        try:
            body = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        endpoint = body.get('endpoint', '').strip()
        p256dh   = body.get('p256dh',   '').strip()
        auth     = body.get('auth',     '').strip()
        label    = body.get('label',    '').strip()

        if not endpoint or not p256dh or not auth:
            return JsonResponse({'error': 'endpoint, p256dh, and auth are required.'}, status=400)

        sub, created = WebPushSubscription.objects.get_or_create(
            endpoint=endpoint,
            defaults={
                'notifier':     notifier,
                'p256dh':       p256dh,
                'auth':         auth,
                'device_label': label,
            },
        )
        if not created:
            # Update keys in case they rotated.
            sub.notifier     = notifier
            sub.p256dh       = p256dh
            sub.auth         = auth
            if label:
                sub.device_label = label
            sub.save()

        return JsonResponse({
            'status': 'subscribed',
            'id': str(sub.pk),
            'label': sub.device_label or '',
            'created': created,
        })


class WebPushUnsubscribeView(ConfigEditorRequired, View):
    """Remove a specific push subscription."""

    def post(self, request, pk, sub_id):
        from webapp.models import WebPushSubscription
        sub = get_object_or_404(WebPushSubscription, pk=sub_id, notifier_id=pk)
        sub.delete()
        return JsonResponse({'status': 'unsubscribed'})
