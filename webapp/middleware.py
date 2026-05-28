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
        request.is_mobile = bool(_MOBILE_UA_RE.search(ua)) and not force_desktop

        response = self.get_response(request)

        if request.GET.get('desktop') == '1':
            response.set_cookie('desktop_mode', '1', max_age=86400 * 365)

        return response
