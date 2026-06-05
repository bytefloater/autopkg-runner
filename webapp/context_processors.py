from webapp import translations as _trans

# Cached server timezone key — determined once at first request then reused.
_local_tz_key = None  # str once resolved, None until first request


def _get_local_tz_key() -> str:
    global _local_tz_key
    if _local_tz_key is None:
        from webapp.scheduler import get_system_timezone
        _local_tz_key = get_system_timezone().key
    return _local_tz_key

_BASE_TABS = [
    {'name': 'dashboard', 't_key': 'VIEWS_DASHBOARD', 'label': 'Dashboard', 'url_name': 'dashboard',  'icon': 'house'},
    {'name': 'runs',      't_key': 'VIEWS_RUNS',      'label': 'Runs',      'url_name': 'run-list',   'icon': 'list'},
    {'name': 'schedule',  't_key': 'VIEWS_SCHEDULES', 'label': 'Schedule',  'url_name': 'schedule',      'icon': 'calendar'},
    {'name': 'recipes',   't_key': 'VIEWS_RECIPES',  'label': 'Recipes',   'url_name': 'recipes-repos', 'icon': 'package'},
    {'name': 'config',    't_key': 'VIEWS_CONFIG',    'label': 'Config',    'url_name': 'config',        'icon': 'settings'},
]

_ADMIN_TABS = [
    {'name': 'users', 't_key': 'VIEWS_USERS', 'label': 'Users', 'url_name': 'users', 'icon': 'users'},
]


def nav_tabs(request):
    tabs = list(_BASE_TABS)
    if request.user.is_authenticated and request.user.is_superuser:
        tabs += _ADMIN_TABS
    # Recipes is accessible via Config on mobile — exclude from tab bar
    _MOBILE_EXCLUDED = {'recipes'}
    return {
        'nav_tabs': tabs,
        'mobile_nav_tabs': [t for t in _BASE_TABS if t['name'] not in _MOBILE_EXCLUDED],
        'local_tz': _get_local_tz_key(),
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
