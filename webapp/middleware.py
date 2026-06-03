import re

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
