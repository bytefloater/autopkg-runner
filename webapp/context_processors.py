from webapp import translations as _trans

_BASE_TABS = [
    {'name': 'dashboard', 't_key': 'VIEWS_DASHBOARD', 'label': 'Dashboard', 'url_name': 'dashboard',  'icon': 'house'},
    {'name': 'runs',      't_key': 'VIEWS_RUNS',      'label': 'Runs',      'url_name': 'run-list',   'icon': 'list'},
    {'name': 'schedule',  't_key': 'VIEWS_SCHEDULES', 'label': 'Schedule',  'url_name': 'schedule',   'icon': 'calendar'},
    {'name': 'config',    't_key': 'VIEWS_CONFIG',    'label': 'Config',    'url_name': 'config',     'icon': 'settings'},
    {'name': 'tokens',    't_key': 'VIEWS_TOKENS',    'label': 'Tokens',    'url_name': 'api-tokens', 'icon': 'key'},
]

_ADMIN_TABS = [
    {'name': 'users', 't_key': 'VIEWS_USERS', 'label': 'Users', 'url_name': 'users', 'icon': 'users'},
]


def nav_tabs(request):
    tabs = list(_BASE_TABS)
    if request.user.is_authenticated and request.user.is_superuser:
        tabs += _ADMIN_TABS
    return {
        'nav_tabs': tabs,
        'mobile_nav_tabs': list(_BASE_TABS),
    }


def translation(request):
    """Inject `t` (translation dict) and `current_language` into every template."""
    from webapp.models import Setting
    try:
        lang = Setting.get('ui.language', 'en-US')
    except Exception:
        lang = 'en-US'
    return {
        't': _trans.load(lang),
        'current_language': lang,
        'available_languages': _trans.available(),
    }
