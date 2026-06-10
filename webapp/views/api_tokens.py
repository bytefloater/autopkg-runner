from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from webapp.perms import ConfigEditorRequired
from django.shortcuts import redirect
from django.views.generic import TemplateView

_API_ENDPOINTS = [
    ('GET',  '/api/auth/challenge/',            '?username=… → {challenge_id, nonce, argon2_params} (step 1 of ZK login)'),
    ('POST', '/api/auth/get_token/',            '{username, challenge_id, response} → {token_id, token_secret} (step 2 of ZK login)'),
    ('GET',  '/api/auth/check_token/',          'Validate a signed request → {valid, username}'),
    ('POST', '/api/tasks/trigger_run/',         'Start a pipeline run → task UUID'),
    ('POST', '/api/tasks/trigger_db_cleanup/',  'Start a DB cleanup → task UUID'),
    ('GET',  '/api/tasks/get_task_status/',     '?uuid=… → task status'),
    ('GET',  '/api/history/get_run_data/',      '?uuid=… → full run + logs'),
    ('GET',  '/api/history/list_runs/',         '?start_date=&end_date= → run list'),
]

_HMAC_SIGNING_GUIDE = """\
Authorization: HMAC-SHA256 Credential=<token_id>, Timestamp=<unix_epoch_seconds>, Nonce=<16-byte-hex>, Signature=<sha256-hex>

Canonical request string (what you sign):
  METHOD\\nURL_PATH\\nTIMESTAMP\\nNONCE\\nSHA256(request_body_bytes)

Signature = HMAC-SHA256(key=token_secret_bytes, msg=canonical_request.encode())

Rules:
  • Timestamp must be within ±5 minutes of server time.
  • Nonce must be unique per request (prevents replay attacks).
  • token_secret is shown only once at creation time — store it securely.
"""


class ApiTokensView(ConfigEditorRequired, TemplateView):
    template_name = 'webapp/api_tokens.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/api_tokens.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import APIToken
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']     = 'config'
        ctx['tokens']         = APIToken.objects.filter(user=self.request.user)
        ctx['new_token_id']     = self.request.session.pop('new_token_id', None)
        ctx['new_token_secret'] = self.request.session.pop('new_token_secret', None)
        ctx['new_token_name']   = self.request.session.pop('new_token_name', None)
        ctx['api_endpoints']      = _API_ENDPOINTS
        ctx['hmac_signing_guide'] = _HMAC_SIGNING_GUIDE
        return ctx

    def post(self, request):
        from webapp.models import APIToken
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'A token name is required.')
                return redirect('api-tokens')
            token = APIToken.objects.create(user=request.user, name=name)
            request.session['new_token_id']     = token.token_id
            request.session['new_token_secret'] = token.decrypted_secret
            request.session['new_token_name']   = token.name

        elif action == 'revoke':
            token_id = request.POST.get('token_id')
            deleted, _ = APIToken.objects.filter(user=request.user, pk=token_id).delete()
            if deleted:
                messages.success(request, 'Token revoked.')
            else:
                messages.error(request, 'Token not found.')

        return redirect('api-tokens')
