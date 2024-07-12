"""
Django settings for speciesnet project.

Generated by 'django-admin startproject' using Django 5.0.1.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY')

ALLOWED_HOSTS = ['*']
#ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS').split(' ') --> Fails because of Django header mismatch 

CSRF_TRUSTED_ORIGINS = ['http://localhost', 'http://127.0.0.1', 'http://127.0.0.1:81']
#CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS').split(' ') --> Fails because of Django header mismatch 

# DEBUG SECURITY WARNING ------> do NOT run with debug turned on in production!

if os.environ.get('DEBUG', 'True') == "True":
    DEBUG = True
elif (os.environ['DEBUG'] == '1'):
    DEBUG = True
else:
    DEBUG = False

if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    # https://docs.djangoproject.com/en/5.0/topics/email/#topic-email-backends
    raise NotImplemented("add an email backend here")

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'species.apps.SpeciesConfig',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'django_recaptcha',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "allauth.account.middleware.AccountMiddleware",
]

# needed to allow Google one click auth
SECURE_REFERRER_POLICY= "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY="same-origin-allow-popups"

GOOGLE_OAUTH_LINK = os.environ.get('GOOGLE_OAUTH_LINK', 'unsecure')

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
        'FETCH_USERINFO': True
    }
}
SOCIALACCOUNT_EMAIL_AUTHENTICATION=True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT=True
SOCIALACCOUNT_LOGIN_ON_GET=True
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True
LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "/login/"
ACCOUNT_FORMS = {
    'signup': 'species.forms.CustomSignupForm',
    'reset_password': 'species.forms.CustomResetPasswordForm',
}
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_DEFAULT_HTTP_PROTOCOL='https'
ACCOUNT_CHANGE_EMAIL = True

# Keeps users logged in for a long time
SESSION_COOKIE_AGE = 120960000

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY', 'unsecure')
RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY', 'unsecure')

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

ROOT_URLCONF = 'speciesnet.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates'
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
]

WSGI_APPLICATION = 'speciesnet.wsgi.application'

#Database
#https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         #'NAME': BASE_DIR / 'db.sqlite3',
#         'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#     }
# }

# DATABASES = {
#     "default": {
#         'ENGINE': "django.db.backends.postgresql",
#         'NAME':     os.environ.get('POSTGRES_DB'),
#         'USER':     os.environ.get('POSTGRES_USER'),
#         'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
#         'HOST': "postgres_db",  # matches service in docker-compose.yml
#         'PORT': 5432,           # default postgres port
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': os.environ.get('DATABASE_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.environ.get('DATABASE_NAME', 'speciesnet'),
        'USER': os.environ.get('DATABASE_USER', 'mysqluser'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'unsecure'),
        'HOST': os.environ.get('DATABASE_HOST', 'db'),
        'PORT': os.environ.get('DATABASE_PORT', '3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}

# Custom User Model
AUTH_USER_MODEL = 'species.User'
# Allauth integration with custom user model
ACCOUNT_USER_MODEL_USERNAME_FIELD='username'

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# STATIC_ROOT defines the absolute path where 'collectstatic' will be populated
STATIC_ROOT = '/static/'
# STATIC_URL defines the url used by the nginx webserver to serve up static files
STATIC_URL = '/static/'

# STATIC_FILES_DIRs defines additional project folders for static files
# Default is to include the project app folder: ./speciesnet/species/static
#STATICFILES_DIRS = [os.path.join(BASE_DIR,'species/static')]
STATICFILES_DIRS = [os.path.join(BASE_DIR,'static')]

# image file PILLOW support - hassle configuration see urls.py
MEDIA_URL = '/media/'
#MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_ROOT = '/media/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
