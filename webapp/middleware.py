import logging
import re

from django.db.utils import OperationalError
from django.http import HttpResponse

logger = logging.getLogger('autopkg_runner')

_READONLY_KEYWORDS = ('readonly database', 'read-only database', 'attempt to write')

_DB_READONLY_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Database Unavailable — AutoPkg Runner</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100dvh;
      display: flex; align-items: center; justify-content: center;
      background: #08090f;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #e5e7eb;
      padding: 24px;
    }
    .card {
      width: 100%%; max-width: 420px;
      background: #13141a;
      border: 1px solid #2a2b35;
      border-radius: 18px;
      padding: 36px 32px 32px;
      text-align: center;
    }
    .icon {
      width: 56px; height: 56px;
      background: #3a1a1a;
      border-radius: 50%%;
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 20px;
      font-size: 26px;
    }
    h1 { font-size: 18px; font-weight: 600; margin-bottom: 10px; }
    p  { font-size: 14px; color: #9ca3af; line-height: 1.55; margin-bottom: 8px; }
    .hint {
      margin-top: 16px;
      background: #1c1d24;
      border: 1px solid #2a2b35;
      border-radius: 10px;
      padding: 12px 14px;
      font-size: 12px;
      color: #6b7280;
      text-align: left;
    }
    .btn {
      display: inline-block; margin-top: 24px;
      padding: 11px 28px;
      background: #2563eb;
      color: #fff;
      font-size: 15px; font-weight: 600;
      border: none; border-radius: 10px;
      cursor: pointer; text-decoration: none;
    }
    .btn:hover { background: #1d4ed8; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">⚠️</div>
    <h1>Database Temporarily Unavailable</h1>
    <p>AutoPkg Runner can't write to its database right now.</p>
    <p>This usually happens when another app (such as a database viewer) has the database file open with exclusive access.</p>
    <div class="hint">
      <strong style="color:#d1d5db">To fix:</strong> close any database management tools
      (e.g. SQLPro, DB Browser for SQLite) and try again.
    </div>
    <a href="javascript:location.reload()" class="btn">Try Again</a>
  </div>
</body>
</html>
"""


def _is_readonly_db_error(exc: BaseException) -> bool:
    """Return True if *exc* is a SQLite 'readonly database' OperationalError."""
    if not isinstance(exc, OperationalError):
        return False
    msg = str(exc).lower()
    return any(kw in msg for kw in _READONLY_KEYWORDS)


class DatabaseWriteGuardMiddleware:
    """Intercept SQLite 'readonly database' errors and return a graceful 503 page.

    Placed early in MIDDLEWARE (before SessionMiddleware) so that write failures
    from session saves, authentication flushes, and view DB operations are all
    caught here rather than surfacing as a Django debug traceback.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except OperationalError as exc:
            if _is_readonly_db_error(exc):
                logger.error(
                    'Database is read-only — returning 503. path=%s exc=%s',
                    request.path, exc,
                )
                return HttpResponse(_DB_READONLY_HTML, status=503,
                                    content_type='text/html; charset=utf-8')
            raise


# ---------------------------------------------------------------------------

_MOBILE_UA_RE = re.compile(
    r'(android|iphone|ipad|ipod|blackberry|opera mini|mobile)',
    re.IGNORECASE,
)


class MobileDetectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ua = request.META.get('HTTP_USER_AGENT', '')
        force_desktop = (
            request.COOKIES.get('desktop_mode') == '1'
            or request.GET.get('desktop') == '1'
        )

        # iPadOS 13+ sends a macOS-style UA so the regex above misses it.
        # base_desktop.html detects the touch fingerprint in JS and sets this
        # cookie, which we pick up on the next (reloaded) request.
        ipad_detected = request.COOKIES.get('ipad_detected') == '1'

        request.is_mobile = (
            bool(_MOBILE_UA_RE.search(ua)) or ipad_detected
        ) and not force_desktop

        response = self.get_response(request)

        if request.GET.get('desktop') == '1':
            response.set_cookie('desktop_mode', '1', max_age=86400 * 365)
            # Remove the iPad detection cookie so desktop mode is fully honoured.
            response.delete_cookie('ipad_detected', path='/')

        return response
