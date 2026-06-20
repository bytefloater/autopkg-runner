import json
import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# -- Inline-SVG icon cache ------------------------------------------------------
_SVG_CACHE: dict[str, str] = {}


def _read_svg(name: str) -> str:
    """Read a Lucide SVG from staticfiles; cache the raw content in-process."""
    if name not in _SVG_CACHE:
        from django.contrib.staticfiles import finders
        path = finders.find(f'ui_symbols/{name}.svg')
        if isinstance(path, str):
            with open(path, 'r', encoding='utf-8') as fh:
                _SVG_CACHE[name] = fh.read().strip()
        else:
            _SVG_CACHE[name] = ''
    return _SVG_CACHE[name]


# -- Filters --------------------------------------------------------------------

@register.filter
def duration(start, end):
    """Return a human-readable duration string from two datetimes."""
    if not start or not end:
        return '-'
    delta = end - start
    total = int(delta.total_seconds())
    if total < 0:
        return '-'
    if total < 60:
        return f'{total}s'
    m, s = divmod(total, 60)
    if m < 60:
        return f'{m}m {s}s'
    h, m = divmod(m, 60)
    return f'{h}h {m}m'


@register.filter
def status_color(status):
    """Map a run/stage status to a Tailwind colour class set."""
    mapping = {
        'pending':   'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
        'running':   'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
        'success':   'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
        'failed':    'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
        'cancelled': 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
        'skipped':   'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
    }
    return mapping.get(status, 'bg-gray-100 text-gray-600')


@register.filter
def status_dot(status):
    """Return a solid dot colour class for status indicators."""
    mapping = {
        'pending':   'bg-gray-400',
        'running':   'bg-blue-500 animate-pulse',
        'success':   'bg-green-500',
        'failed':    'bg-red-500',
        'cancelled': 'bg-yellow-500',
        'skipped':   'bg-gray-300',
    }
    return mapping.get(status, 'bg-gray-400')


@register.filter
def level_color(level):
    """Map a log level to a Tailwind text colour class."""
    mapping = {
        'DEBUG':    'text-gray-400 dark:text-gray-500',
        'INFO':     'text-gray-500',
        'NOTICE':   'text-blue-600 dark:text-blue-400',
        'WARNING':  'text-yellow-600 dark:text-yellow-400',
        'ERROR':    'text-red-600 dark:text-red-400',
        'CRITICAL': 'text-red-700 font-bold dark:text-red-300',
    }
    return mapping.get(level, 'text-gray-600')


@register.simple_tag
def lucide(name, classes='w-5 h-5'):
    """Render a Lucide icon as an inline SVG.

    Uses ``currentColor`` from the surrounding element, so icons automatically
    adapt to any text colour - including dark-mode variants.

    Handles both compact single-line SVGs and the multi-line format emitted by
    the Lucide static CDN (which includes a license comment and a pre-existing
    class attribute on the root <svg> element).
    """
    svg = _read_svg(name)
    if not svg:
        return mark_safe(f'<span class="{classes}" aria-hidden="true"></span>')

    # Strip leading license/comment block (CDN format: <!-- @license … -->)
    svg = re.sub(r'^<!--.*?-->\s*', '', svg, count=1, flags=re.DOTALL).strip()

    def _process_root_tag(m):
        tag = m.group(0)
        # Remove width/height (we size via CSS classes)
        tag = re.sub(r'\s+(?:width|height)="[^"]*"', '', tag)
        # Remove any pre-existing class attribute (CDN adds class="lucide lucide-*")
        tag = re.sub(r'\s*class="[^"]*"', '', tag)
        # Collapse multi-line attribute formatting to a single line
        tag = re.sub(r'\s+', ' ', tag).strip()
        # Inject Tailwind classes and aria-hidden right after <svg
        tag = tag.replace('<svg', f'<svg class="{classes}" aria-hidden="true"', 1)
        return tag

    # [^>]* matches newlines too, so this handles multi-line opening tags
    svg = re.sub(r'<svg\b[^>]*>', _process_root_tag, svg, count=1)
    return mark_safe(svg)


@register.filter
def json_encode(val):
    """Serialize a value to JSON safe for use inside a double-quoted HTML attribute.

    Double quotes in the JSON are HTML-escaped to &quot; so they don't break
    the attribute delimiter. Browsers decode entities before Alpine.js evaluates
    the expression, so Alpine receives valid JSON.
    """
    import html
    return mark_safe(html.escape(json.dumps(val, default=str), quote=True))


@register.filter
def ensure_list(val):
    if isinstance(val, list):
        return val
    if val:
        return [val]
    return []


@register.filter
def lookup(d, key):
    """Look up a key in a dict (for use in templates).

    Uses ``d[key]`` rather than ``d.get(key)`` so that subclasses such as
    TranslationProxy can handle missing keys via ``__missing__`` (returning
    the dotted key path) rather than silently producing ``None``.

    Returns ``''`` for missing keys and for keys whose stored value is
    ``None``, so that ``value="{{ config|lookup:'x' }}"`` renders blank
    rather than the string "None".
    """
    if isinstance(d, dict):
        try:
            val = d[key]
            return '' if val is None else val
        except KeyError:
            return ''
    return ''


_RESULT_TYPE_KEYS = {
    'failure':        'RESULT_TYPE_FAILURE',
    'pkg_copied':     'RESULT_TYPE_PKG_COPIED',
    'pkgcopied':      'RESULT_TYPE_PKG_COPIED',
    'url_downloaded': 'RESULT_TYPE_URL_DOWNLOADED',
    'urldownloaded':  'RESULT_TYPE_URL_DOWNLOADED',
    'deprecation':    'RESULT_TYPE_DEPRECATION',
    'munki_import':   'RESULT_TYPE_MUNKI_IMPORT',
    'munkiimport':    'RESULT_TYPE_MUNKI_IMPORT',
    'trust_updated':  'RESULT_TYPE_TRUST_UPDATED',
    'trustupdated':   'RESULT_TYPE_TRUST_UPDATED',
}


@register.filter
def result_type_label(result_type, t):
    """Return a translated display name for an AutoPkg result_type.

    Usage: {{ result.result_type|result_type_label:t }}
    Falls back to the dotted translation key (e.g. RUN_DETAIL_VIEW.RESULT_TYPE_FAILURE)
    for missing translations, consistent with TranslationProxy.__missing__.
    """
    key = _RESULT_TYPE_KEYS.get(result_type)
    if key and t:
        try:
            return t['RUN_DETAIL_VIEW'][key]
        except (KeyError, TypeError):
            return f'RUN_DETAIL_VIEW.{key}'
    synthetic = 'RESULT_TYPE_' + result_type.upper()
    return f'RUN_DETAIL_VIEW.{synthetic}'

# Maps field names to RESULT_FIELD_* translation keys.
# 'name' is qualified with its result_type since it has a specific meaning in
# deprecation warnings that differs from a generic "name" field.
_RESULT_FIELD_KEYS = {
    'message':            'RESULT_FIELD_MESSAGE',
    'recipe':             'RESULT_FIELD_RECIPE',
    'recipe_id':          'RESULT_FIELD_RECIPE_ID',
    'traceback':          'RESULT_FIELD_TRACEBACK',
    'pkg_path':           'RESULT_FIELD_PKG_PATH',
    'pkg_repo_path':      'RESULT_FIELD_PKG_REPO_PATH',
    'download_path':      'RESULT_FIELD_DOWNLOAD_PATH',
    'warning':            'RESULT_FIELD_WARNING',
    'deprecation:name':   'RESULT_FIELD_DEPRECATION_NAME',
    'name':               'RESULT_FIELD_NAME',
    'catalogs':           'RESULT_FIELD_CATALOGS',
    'icon_repo_path':     'RESULT_FIELD_ICON_REPO_PATH',
    'pkginfo_path':       'RESULT_FIELD_PKGINFO_PATH',
    'version':            'RESULT_FIELD_VERSION',
}


@register.simple_tag
def result_field_label(field_name, result_type, t):
    """Return a translated column header for an AutoPkg result field.

    Usage: {% result_field_label key result.result_type t %}
    Tries the result_type-qualified key first, then the plain field name.
    Falls back to the dotted translation key (e.g. RUN_DETAIL_VIEW.RESULT_FIELD_PKG_PATH)
    for missing translations, consistent with TranslationProxy.__missing__.
    """
    for lookup in [f'{result_type}:{field_name}', field_name]:
        translation_key = _RESULT_FIELD_KEYS.get(lookup)
        if translation_key:
            try:
                return t['RUN_DETAIL_VIEW'][translation_key]
            except (KeyError, TypeError):
                return f'RUN_DETAIL_VIEW.{translation_key}'
    synthetic = 'RESULT_FIELD_' + field_name.upper()
    return f'RUN_DETAIL_VIEW.{synthetic}'
