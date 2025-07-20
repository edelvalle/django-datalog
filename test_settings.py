"""
Django settings for django-datalog tests
"""

SECRET_KEY = 'test-secret-key-for-django-datalog-tests'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'djdatalog',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

USE_TZ = True
USE_I18N = True

# Enable test models and facts
DJDATALOG_TESTING = True

# Minimal logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'djdatalog': {
            'handlers': ['null'],
        },
    },
}