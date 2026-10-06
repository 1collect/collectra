from .settings import *  # noqa: F403


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
DATABASES['import_progress'] = {**DATABASES['default'], 'TEST': {'MIRROR': 'default'}}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
IMPORT_PROGRESS_DB_ALIAS = 'default'
IMPORT_PREBUILD_ERROR_REPORTS = False
