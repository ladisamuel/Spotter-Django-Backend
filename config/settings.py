"""
Django settings for route_optimizer project.

Dual-mode architecture:
- DEBUG=True:  SQLite, LocMemCache, Python geospatial math
- DEBUG=False: PostgreSQL+PostGIS, Redis, database-level spatial queries
"""

import os
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================
DEBUG = config('DEBUG', default=True, cast=bool)
SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-me')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
]

if not DEBUG:
    # PostGIS support in production
    DJANGO_APPS.insert(5, 'django.contrib.gis')

LOCAL_APPS = [
    'apps.fuel',
    'apps.cache',
    'apps.api',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# =============================================================================
# DATABASE CONFIGURATION (Dual-Mode)
# =============================================================================
if DEBUG:
    # Development: SQLite - zero infrastructure, free hosting ready
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    # Production: PostgreSQL + PostGIS - scalable, spatial indexing
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.postgis',
            'NAME': config('DB_NAME', default='route_optimizer'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 600,  # Persistent connections for performance
        }
    }

# =============================================================================
# CACHE CONFIGURATION (Dual-Mode)
# =============================================================================
if DEBUG:
    # Development: In-memory cache - no external dependency
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }
else:
    # Production: Redis - distributed, persistent, high-performance
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
            }
        }
    }

CACHE_TTL_SECONDS = config('CACHE_TTL_SECONDS', default=86400, cast=int)

# =============================================================================
# PASSWORD VALIDATION
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC FILES
# =============================================================================
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# REST FRAMEWORK
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
    },
    'EXCEPTION_HANDLER': 'apps.api.views.custom_exception_handler',
}

# =============================================================================
# LOGGING
# =============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'apps.routing': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps.fuel': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps.optimization': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'apps.cache': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
    },
}

# =============================================================================
# VEHICLE & OPTIMIZATION CONFIG
# =============================================================================
VEHICLE_RANGE_MILES = config('VEHICLE_RANGE_MILES', default=500, cast=float)
FUEL_EFFICIENCY_MPG = config('FUEL_EFFICIENCY_MPG', default=10, cast=float)
TANK_CAPACITY_GALLONS = config('TANK_CAPACITY_GALLONS', default=50, cast=float)
ROUTE_CORRIDOR_WIDTH_MILES = config('ROUTE_CORRIDOR_WIDTH_MILES', default=25, cast=float)

# =============================================================================
# OSRM CONFIG
# =============================================================================
OSRM_BASE_URL = config('OSRM_BASE_URL', default='http://router.project-osrm.org')
OSRM_ROUTE_ENDPOINT = config('OSRM_ROUTE_ENDPOINT', default='/route/v1/driving/')
OSRM_REQUEST_TIMEOUT = 30  # seconds
OSRM_MAX_RETRIES = 2
