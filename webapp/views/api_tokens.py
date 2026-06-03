from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

_API_ENDPOINTS = [
    ('POST', '/api/auth/get_token/',            'username + password → token key'),
    ('GET',  '/api/auth/check_token/',          'Validate a token → {valid, username}'),
    ('POST', '/api/tasks/trigger_run/',         'Start a pipeline run → task UUID'),
    ('POST', '/api/tasks/trigger_db_cleanup/',  'Start a DB cleanup → task UUID'),
    ('GET',  '/api/tasks/get_task_status/',     '?uuid=… → task status'),
    ('GET',  '/api/history/get_run_data/',      '?uuid=… → full run + logs'),
    ('GET',  '/api/history/list_runs/',         '?start_date=&end_date= → run list'),
]


class ApiTokensView(LoginRequiredMixin, TemplateView):
    template_name = 'webapp/api_tokens.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/api_tokens.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import APIToken
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']     = 'tokens' if not self.request.is_mobile else 'config'
        ctx['tokens']         = APIToken.objects.filter(user=self.request.user)
        ctx['new_token']      = self.request.session.pop('new_token_value', None)
        ctx['new_token_name'] = self.request.session.pop('new_token_name', None)
        ctx['api_endpoints']  = _API_ENDPOINTS
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
            request.session['new_token_value'] = token.key
            request.session['new_token_name']  = token.name

        elif action == 'revoke':
            token_id = request.POST.get('token_id')
            deleted, _ = APIToken.objects.filter(user=request.user, pk=token_id).delete()
            if deleted:
                messages.success(request, 'Token revoked.')
            else:
                messages.error(request, 'Token not found.')

        return redirect('api-tokens')
