import shutil

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from webapp import translations as trans

_LOG_LEVELS = [('DEBUG', 'DEBUG'), ('INFO', 'INFO'), ('WARNING', 'WARNING'), ('ERROR', 'ERROR')]

# ── Sections shown on the root config page ─────────────────────────────────────
CONFIG_SECTIONS = [
    {'key': 'autopkg',     'url_name': 'config-autopkg',     'icon': 'package'},
    {'key': 'workflow',    'url_name': 'config-workflow',    'icon': 'git-branch'},
    {'key': 'repository',  'url_name': 'config-repository',  'icon': 'hard-drive'},
    {'key': 'gc',          'url_name': 'config-gc',          'icon': 'trash-2'},
    {'key': 'logging',     'url_name': 'config-logging',     'icon': 'file-text'},
    {'key': 'notifications','url_name': 'config-notifications','icon': 'bell'},
    {'key': 'ui',          'url_name': 'config-ui',          'icon': 'globe'},
]


class ConfigRootView(LoginRequiredMixin, TemplateView):
    """Configuration landing page — shows a navigable list of sections."""

    template_name = 'webapp/config.html'

    def get_template_names(self):
        if getattr(self.request, 'is_mobile', False):
            return ['webapp/mobile/config.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        from webapp.models import Setting
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'config'
        ctx['sections']   = CONFIG_SECTIONS
        ctx['current_language'] = Setting.get('ui.language', 'en-US')
        return ctx


class ConfigSectionView(LoginRequiredMixin, TemplateView):
    """Handles GET (display) and POST (save) for a named config section."""

    # section kwarg supplied by the URL dispatcher
    section: str = ''

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.section = kwargs.get('section', self.section)

    def get_template_names(self):
        mobile = getattr(self.request, 'is_mobile', False)
        base = 'webapp/mobile/config' if mobile else 'webapp/config'
        return [f'{base}/{self.section}.html']

    def get_context_data(self, **kwargs):
        from webapp.models import Setting
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'config'
        ctx['section']    = self.section
        ctx['s']          = Setting.get_all()   # full settings dict
        ctx['log_levels'] = _LOG_LEVELS
        ctx['sections']   = CONFIG_SECTIONS     # for desktop sidebar nav

        if self.section == 'repository':
            ctx['sftp_available'] = shutil.which('sshfs') is not None

        if self.section == 'logging':
            # Allow the log-level subpage to communicate back via ?level=DEBUG
            level_param = self.request.GET.get('level', '').upper().strip()
            valid = {v for v, _ in _LOG_LEVELS}
            if level_param in valid:
                s = dict(ctx['s'])
                s['logging.level'] = level_param
                ctx['s'] = s

        return ctx

    def post(self, request, **kwargs):
        from webapp.models import Setting

        section = kwargs.get('section', self.section)

        # Each section declares which keys it owns and their types.
        # Keys absent from POST for bool fields are treated as False.
        bool_keys, int_keys, text_keys = _section_keys(section)

        for key in bool_keys:
            Setting.set(key, 'true' if request.POST.get(key) else 'false')

        for key in int_keys:
            try:
                val = str(int(request.POST.get(key, '0')))
            except ValueError:
                val = '0'
            Setting.set(key, val)

        for key in text_keys:
            val = request.POST.get(key, '')
            if val is not None:
                # Don't overwrite a saved credential with a blank submission
                # (e.g. user opens the form but doesn't change the password).
                if key in Setting.SENSITIVE_KEYS and not val:
                    continue
                Setting.set(key, val)

        messages.success(request, 'Settings saved.')
        return redirect(f'config-{section}')


class LogLevelPickerView(LoginRequiredMixin, TemplateView):
    """
    Mobile-only sub-page: show available log levels with checkmarks.
    Selecting one redirects to /config/logging/?level=<LEVEL>.
    """

    template_name = 'webapp/mobile/config/logging_level.html'

    def get_context_data(self, **kwargs):
        from webapp.models import Setting
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab']     = 'config'
        ctx['log_levels']     = _LOG_LEVELS
        ctx['current_level']  = (
            self.request.GET.get('current', '').upper().strip()
            or Setting.get('logging.level', 'INFO')
        )
        return ctx


def _section_keys(section: str) -> tuple:
    """Return (bool_keys, int_keys, text_keys) for a config section."""
    if section == 'autopkg':
        return (
            [],
            [],
            ['autopkg.bin_path', 'autopkg.cache_path', 'autopkg.recipe_list'],
        )
    elif section == 'workflow':
        return (['workflow.update_repos'], [], [])
    elif section == 'repository':
        return (
            [],
            [],
            ['repository.type', 'repository.connection_type',
             'repository.local_path',
             'repository.host', 'repository.share',
             'repository.mount_path', 'repository.public_url',
             'repository.username', 'repository.password'],
        )
    elif section == 'gc':
        return (
            ['gc.clear_temp', 'gc.clean_repo'],
            ['gc.keep_versions'],
            ['gc.repoclean_bin_path'],
        )
    elif section == 'logging':
        return (
            ['logging.to_file'],
            [],
            ['logging.level', 'logging.file_path'],
        )
    elif section == 'ui':
        return ([], [], ['ui.language'])
    else:
        return ([], [], [])
