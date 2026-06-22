from webapp import translations as _trans
from webapp.perms import get_user_perms, PERM_EDIT_CONFIG, PERM_MANAGE_USERS

# -- Vendored front-end dependencies ------------------------------------------
# Single source of truth for vendored JS/CSS versions.  To bump a dependency:
#   1. Update the version constant below.
#   2. Download the new file(s) to webapp/static/ using the versioned filename
#      pattern (e.g. alpine-X.Y.Z.min.js) and delete the old file(s).
#   3. Run collectstatic.  All template references update automatically.
#
# Sources:
#   Alpine.js   https://cdn.jsdelivr.net/npm/alpinejs@{ver}/dist/cdn.min.js
#   htmx        https://unpkg.com/htmx.org@{ver}/dist/htmx.min.js
#   CodeMirror  https://cdnjs.cloudflare.com/ajax/libs/codemirror/{ver}/<path>
#
# Tailwind CSS is built — see tailwind.config.js / webapp/static/css/tailwind.input.css.
# Rebuild: tailwindcss -c tailwind.config.js -i webapp/static/css/tailwind.input.css
#                      -o webapp/static/css/tailwind.css --minify
_ALPINE_VERSION     = '3.14.9'
_HTMX_VERSION       = '2.0.4'
_CODEMIRROR_VERSION = '5.65.16'

_VENDOR = {
    'alpine':           f'js/alpine-{_ALPINE_VERSION}.min.js',
    'htmx':             f'js/htmx-{_HTMX_VERSION}.min.js',
    'codemirror_css':   f'codemirror/codemirror-{_CODEMIRROR_VERSION}.min.css',
    'codemirror_js':    f'codemirror/codemirror-{_CODEMIRROR_VERSION}.min.js',
    'codemirror_theme': f'codemirror/theme/material-darker-{_CODEMIRROR_VERSION}.min.css',
    'codemirror_xml':   f'codemirror/mode/xml/xml-{_CODEMIRROR_VERSION}.min.js',
    'codemirror_yaml':  f'codemirror/mode/yaml/yaml-{_CODEMIRROR_VERSION}.min.js',
}


def vendor(request):
    return {'vendor': _VENDOR}

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
