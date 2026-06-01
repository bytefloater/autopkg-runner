"""
JSON-based translation loader.

Translation files live in webapp/translations/<lang>.json.
Keys use a two-level dot path, e.g. APP.NAME or CONFIG_VIEW.OPT_LOG_LEVEL.
Values may reference other keys using the @: prefix (resolved at load time).

Templates access strings via the `t` context variable using Django's built-in
dot notation: {{ t.APP.NAME }}, {{ t.CONFIG_VIEW.OPT_AUTOPKG_BINARY }}, etc.

Missing keys fall back to the dotted key path so that every {{ t.X.Y }}
renders something visible (e.g. "APP.MISSING_KEY") instead of going blank.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).parent / 'translations'
FALLBACK_LANG = 'en-US'


class TranslationProxy(dict):
    """
    A dict subclass that returns the dotted key path (e.g. 'APP.MISSING_KEY')
    when a translation key is absent, instead of rendering empty.

    Nested dicts are automatically wrapped so the full path accumulates at
    every level.  Django template dot-notation ({{ t.APP.ACTION_SAVE }})
    resolves to a plain string for present keys, and to the path string for
    absent ones — making missing translations immediately visible without
    raising exceptions.
    """

    __slots__ = ('_path',)

    def __init__(self, data: dict, _path: str = '') -> None:
        super().__init__()
        self._path = _path
        for k, v in data.items():
            child_path = f'{_path}.{k}' if _path else k
            super().__setitem__(
                k,
                TranslationProxy(v, child_path) if isinstance(v, dict) else v,
            )

    def __missing__(self, key: str) -> 'TranslationProxy':
        child_path = f'{self._path}.{key}' if self._path else key
        return TranslationProxy({}, child_path)

    def __str__(self) -> str:      # used when Django template renders the value
        return self._path

    def __format__(self, fmt: str) -> str:
        return format(self._path, fmt)


def _resolve_ref(value: str, root: dict) -> str:
    """Dereference a single @: pointer against the root translation dict."""
    key_path = value[2:]          # strip '@:'
    current: dict | str = root
    for part in key_path.split('.'):
        if not isinstance(current, dict):
            return value          # broken reference — return as-is
        current = current.get(part, value)
    return current if isinstance(current, str) else value


def _resolve_all(data: dict, root: dict) -> dict:
    """Recursively replace all @: references in a (possibly nested) dict."""
    out: dict = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = _resolve_all(v, root)
        elif isinstance(v, str) and v.startswith('@:'):
            out[k] = _resolve_ref(v, root)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=None)
def load(lang: str) -> dict:
    """
    Load, resolve, and cache the translation for *lang* (e.g. 'en-US').
    Falls back to FALLBACK_LANG if the requested file is not found.
    """
    path = TRANSLATIONS_DIR / f'{lang}.json'
    if not path.exists():
        path = TRANSLATIONS_DIR / f'{FALLBACK_LANG}.json'
    with open(path, encoding='utf-8') as fh:
        raw = json.load(fh)
    resolved = _resolve_all(raw, raw)
    return TranslationProxy(resolved)


def available() -> list[tuple[str, str]]:
    """
    Return [(code, display_name), ...] for every .json file in the
    translations directory, sorted by code.
    """
    result: list[tuple[str, str]] = []
    for f in sorted(TRANSLATIONS_DIR.glob('*.json')):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            result.append((f.stem, data.get('NAME', f.stem)))
        except (json.JSONDecodeError, OSError):
            pass
    return result
