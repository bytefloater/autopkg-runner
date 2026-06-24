import os

from dotenv import load_dotenv
load_dotenv()  # Load .env before Django reads settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')

# Static file collection is handled by gunicorn_conf.py on_starting (runs once
# in the master before workers fork).  WhiteNoise finds the already-populated
# STATIC_ROOT when the WSGI application initialises here in each worker.

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
