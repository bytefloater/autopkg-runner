from django.conf import settings
from django.http import JsonResponse, FileResponse
from django.views import View


class ManifestView(View):
    def get(self, request):
        manifest = {
            'name': 'AutoPkg Runner',
            'short_name': 'AutoPkg',
            'description': 'AutoPkg pipeline management',
            'start_url': '/dashboard/',
            'scope': '/',
            'display': 'standalone',
            'background_color': '#ffffff',
            'theme_color': '#2563eb',
            'orientation': 'portrait-primary',
            'icons': [
                {
                    'src': '/static/logos/icon-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
                {
                    'src': '/static/logos/icon-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
            ],
        }
        response = JsonResponse(manifest)
        response['Content-Type'] = 'application/manifest+json'
        response['Cache-Control'] = 'no-cache'
        return response


class ServiceWorkerView(View):
    def get(self, request):
        import os, sys
        # In a frozen PyInstaller bundle BASE_DIR points to Application Support
        # (mutable data), not the read-only bundle resources.  Use sys._MEIPASS
        # when frozen so we find the bundled static file.
        base = getattr(sys, '_MEIPASS', None) or settings.BASE_DIR
        sw_path = os.path.join(base, 'webapp', 'static', 'sw.js')
        response = FileResponse(open(sw_path, 'rb'), content_type='application/javascript')
        response['Service-Worker-Allowed'] = '/'
        response['Cache-Control'] = 'no-cache'
        return response
