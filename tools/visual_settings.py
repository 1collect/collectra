"""Isolated settings for UI review; never connects to the application database."""
from config.settings import *  # noqa: F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'artifacts' / 'visual.sqlite3'}}
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
