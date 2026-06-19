import os

from dotenv import load_dotenv
load_dotenv()  # Load .env before Django reads settings

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autopkgrunner.settings')
application = get_asgi_application()
