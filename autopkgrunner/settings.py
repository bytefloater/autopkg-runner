import os
import sys
from pathlib import Path

from __info__ import BUNDLE_ID

# In a frozen PyInstaller .app bundle, __file__ resolves inside the read-only
# sys._MEIPASS tree.  Mutable runtime data (DB, collected static files) must
# live in Application Support instead.
if getattr(sys, 'frozen', False):
    _data_home = Path(f'/Library/Application Support/{BUNDLE_ID}')
    if not os.access(_data_home.parent, os.W_OK):
        # Non-root invocation: fall back to user Application Support
        _data_home = Path.home() / f'Library/Application Support/{BUNDLE_ID}'
    _data_home.mkdir(parents=True, exist_ok=True)
    BASE_DIR = _data_home
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']   # required - set in plist (bundle) or .env (dev)

DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'

# True when running Django management commands (migrate, createsuperuser, etc.).
# False when serving via gunicorn.
# In the frozen bundle the entrypoint sets AUTOPKG_MODE; in dev mode we
# fall back to inspecting sys.argv[0] for manage.py.
_VIA_MANAGE = (
    (bool(sys.argv) and os.path.basename(sys.argv[0]) in ('manage.py', 'manage'))
    or os.environ.get('AUTOPKG_MODE') == 'manage'
)

ALLOWED_HOSTS = os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    'localhost 127.0.0.1'
).split()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_apscheduler',
    'webapp',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'webapp.middleware.DatabaseWriteGuardMiddleware',
    # WhiteNoise serves static files when running under gunicorn.
    # The Django dev server handles static files itself, so WhiteNoise is
    # excluded when launched via manage.py to avoid unnecessary overhead.
    *(['whitenoise.middleware.WhiteNoiseMiddleware'] if not _VIA_MANAGE else []),
    'django.contrib.sessions.middleware.SessionMiddleware',
    'webapp.middleware.MobileDetectionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'autopkgrunner.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'webapp.context_processors.nav_tabs',
            'webapp.context_processors.translation',
        ],
    },
},]

WSGI_APPLICATION = 'autopkgrunner.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20},
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

AUTHENTICATION_BACKENDS = [
    'webapp.auth_backends.ChallengeResponseBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if not _VIA_MANAGE:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = LOGIN_URL

# Production hardening — active when not in debug mode.
# These are safe to set unconditionally; they are no-ops in DEBUG=True
# because Django's dev server doesn't enforce them.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    _https = os.environ.get('DJANGO_HTTPS_REDIRECT', 'false').lower() == 'true'
    SECURE_SSL_REDIRECT = _https
    SESSION_COOKIE_SECURE = _https
    CSRF_COOKIE_SECURE = _https
    if _https:
        SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000'))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.APITokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'api.renderers.AutoPkgXMLRenderer',
    ],
}

APSCHEDULER_DATETIME_FORMAT = 'N j, Y, f:s a'
APSCHEDULER_RUN_NOW_TIMEOUT = 25

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'autopkg_runner': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apscheduler': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
