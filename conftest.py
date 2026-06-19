"""Root conftest - sets required env vars before Django settings are imported.

``pytest_configure`` is called during the Config initialisation phase, which
happens before ``pytest_load_initial_conftests`` (the phase where
pytest-django loads Django settings).  Module-level code here runs even
earlier.
"""
import os

# Set before Django settings module is imported by pytest-django.
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('DJANGO_DEBUG', 'true')


def pytest_configure(config):
    """Ensure env vars are present even if this file is somehow loaded late."""
    os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-not-for-production')
    os.environ.setdefault('DJANGO_DEBUG', 'true')
