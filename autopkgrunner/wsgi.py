import os

from dotenv import load_dotenv
load_dotenv()  # Load .env before Django reads settings

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')
application = get_wsgi_application()
