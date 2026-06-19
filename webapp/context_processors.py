from webapp import translations as _trans
from webapp.perms import get_user_perms, PERM_EDIT_CONFIG, PERM_MANAGE_USERS

# Cached server timezone key — determined once at first request then reused.
_local_tz_key = None


def _get_local_tz_key() -> str:
    global _local_tz_key
    if _local_tz_key is None:
        from webapp.scheduler import get_system_timezone
        _local_tz_key = get_system_timezone().key
    return _local_tz_key


_DASHBOARD_TAB = {'name': 'dashboard', 't_key': 'VIEWS_DASHBOARD', 'label': 'Dashboard', 'url_name': 'dashboard',     'icon': 'house'}
_RUNS_TAB      = {'name': 'runs',      't_key': 'VIEWS_RUNS',      'label': 'Runs',      'url_name': 'run-list',      'icon': 'list'}
_RECIPES_TAB   = {'name': 'recipes',   't_key': 'VIEWS_RECIPES',   'label': 'Recipes',   'url_name': 'recipes-repos', 'icon': 'package'}
_CONFIG_TAB    = {'name': 'config',    't_key': 'VIEWS_CONFIG',    'label': 'Config',    'url_name': 'config',        'icon': 'settings'}
_USERS_TAB     = {'name': 'users',     't_key': 'VIEWS_USERS',     'label': 'Users',     'url_name': 'users',         'icon': 'users'}

_MOBILE_EXCLUDED = {'recipes', 'users'}


def nav_tabs(request):
    tabs = [_DASHBOARD_TAB, _RUNS_TAB]
    perms: dict = {}

    if request.user.is_authenticated:
        perms = get_user_perms(request.user)
        if perms[PERM_EDIT_CONFIG]:
            tabs += [_RECIPES_TAB, _CONFIG_TAB]
        if perms[PERM_MANAGE_USERS]:
            tabs += [_USERS_TAB]

    return {
        'nav_tabs': tabs,
        'mobile_nav_tabs': [t for t in tabs if t['name'] not in _MOBILE_EXCLUDED],
        'local_tz': _get_local_tz_key(),
        'user_perms': perms,
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
