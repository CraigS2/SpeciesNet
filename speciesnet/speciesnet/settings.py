from pathlib import Path
import os, logging

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY')

#ALLOWED_HOSTS = ['*']
ALLOWED_HOSTS = [os.environ['ALLOWED_HOST1'], os.environ['ALLOWED_HOST2'], 
                 os.environ['ALLOWED_HOST3'], os.environ['ALLOWED_HOST4']]
#CSRF_TRUSTED_ORIGINS = ['http://localhost', 'http://127.0.0.1']
CSRF_TRUSTED_ORIGINS = [os.environ['CSRF_TRUSTED_ORIGIN1'], os.environ['CSRF_TRUSTED_ORIGIN2'], 
                        os.environ['CSRF_TRUSTED_ORIGIN3'], os.environ['CSRF_TRUSTED_ORIGIN3']]

###############################################
# SITE_ID and SITE_DOMAIN must be aligned     #
# site1 configures aquarist species           #
# site2 configures cares species              #
###############################################

SITE_ID = int(os.getenv('SITE_ID', 1))
SITE_DOMAIN = os.getenv('SITE_DOMAIN', 'your_domain.example.com')

site_domain_1 = 'aquarist.example.com'
site_domain_2 = 'cares.example.com'
if SITE_ID==1:
    site_domain_1 = SITE_DOMAIN
else:
    site_domain_2 = SITE_DOMAIN

SITE_CONFIGS = {
    1: {
        'name': 'Aquarist Species',
        'domain': site_domain_1,
        #'logo': 'site1/logo.png',  # Path relative to static/
        #'primary_color': 'rgb(152, 199, 231)',  # ASN blue
        #'secondary_color': '#6c757d',
        #'contact_email': 'contact@aquarist.example.com',
        'main_css': 'styles/site1/asn_main.css',        
        'navbar_template': 'site1/navbar.html',
        'home_template': 'species/site1/home.html',
        'about_us': 'species/site1/about_us.html',
    },
    2: {
        'name': 'CARES Species',
        'domain': site_domain_2,
        #'logo': 'site2/logo.png',
        #'primary_color': 'rgb(183, 208, 189)',  # CARES green
        #'secondary_color': '#ffc107',
        #'contact_email': 'contact@cares.example.com',
        'main_css': 'styles/site2/cares_main.css',        
        'navbar_template': 'site2/navbar.html',
        'home_template': 'species/site2/home.html',
        'about_us': 'species/site2/about_us.html',
    }
}

CURRENT_SITE_CONFIG = SITE_CONFIGS.get(SITE_ID, SITE_CONFIGS[1])

#########################################################
# DEBUG environment variable shared with nginx-certbot  #
# configure as 0 (False) or 1 (True)                    #
#########################################################

DEBUG = False
if (os.environ['DEBUG'] == 'True'):
    DEBUG = True
elif (os.environ['DEBUG'] == '1'):
    DEBUG = True
print ('DEBUG = ' + str(DEBUG))

DEBUG_TOOLBAR = False
if (os.environ['DEBUG_TOOLBAR'] == 'True'):
    DEBUG_TOOLBAR = True

if DEBUG and DEBUG_TOOLBAR:
    def show_toolbar(request):
        return True
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK" : show_toolbar,
    }
    print ('DEBUG_TOOLBAR is enabled!')

if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

if os.environ.get('EMAIL_USE_TLS', 'True') == "True":
    EMAIL_USE_TLS = True
else:
    EMAIL_USE_TLS = False


### email configuration ###

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = os.environ.get('EMAIL_PORT', 587)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'user@example.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', 'unsecure')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'user@example.com')
EMAIL_SUBJECT_PREFIX = ""

### logging ###

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'error': {
            'format': '[%(asctime)s] [%(levelname)s] [%(name)s.%(funcName)s:%(lineno)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'error_console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'error',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'error_console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'error_console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    # root logger catches everything not specified above
    'root': {
        'handlers': ['console', 'error_console'],
        'level': 'INFO',
    },
}

### Apps and Middleware ###

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
    'django.contrib.sites',
    'rest_framework',
    'corsheaders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "allauth.account.middleware.AccountMiddleware",
]

# order for middleware affects toolbar 
# for some debugging may need higher in list

if DEBUG and DEBUG_TOOLBAR:
    INSTALLED_APPS = INSTALLED_APPS + ['debug_toolbar',]
    MIDDLEWARE = MIDDLEWARE + ['debug_toolbar.middleware.DebugToolbarMiddleware',]

### Authentication ###

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
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL = "/login/"
ACCOUNT_FORMS = {
    'signup': 'species.forms.CustomSignupForm',
    'reset_password': 'species.forms.CustomResetPasswordForm',
}

ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_CONFIRM_EMAIL_ON_GET = os.environ.get('ACCOUNT_CONFIRM_EMAIL_ON_GET', 'False')
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = os.environ.get('ACCOUNT_EMAIL_VERIFICATION', 'none')
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_DEFAULT_HTTP_PROTOCOL='https'
ACCOUNT_CHANGE_EMAIL = True

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

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',
]

### Session Timing ###

SESSION_COOKIE_AGE = 120960000   # 120960000 generous - Keeps users logged in for a long time

### Crispy Forms and Bootstrap CSS ###

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
                'species.context_processors.site_config',                
            ],
        },
    },
]


### WSGI - Web Server Gateway Interface ###

WSGI_APPLICATION = 'speciesnet.wsgi.application'

### Database Configuration ###

# Default Django sqlite3 Database
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         #'NAME': BASE_DIR / 'db.sqlite3',
#         'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#     }
# }

# mariadb production Database
_db_engine = os.environ.get('DATABASE_ENGINE', 'django.db.backends.mysql')
DATABASES = {
    'default': {
        'ENGINE': _db_engine,
        'NAME': os.environ.get('DATABASE_NAME', 'speciesnet'),
        'USER': os.environ.get('DATABASE_USER', 'mysqluser'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', 'unsecure'),
        'HOST': os.environ.get('DATABASE_HOST', 'db'),
        'PORT': os.environ.get('DATABASE_PORT', '3306'),
    }
}
if 'mysql' in _db_engine:
    DATABASES['default']['OPTIONS'] = {'charset': 'utf8mb4'}

### Custom User Model ###

AUTH_USER_MODEL = 'species.User'
ACCOUNT_USER_MODEL_USERNAME_FIELD='username'  # Allauth integration with custom user model

### Password validation ###

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

### Internationalization ###

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

### Static and Media File Configuration ###

STATIC_ROOT = '/static/'
STATIC_URL  = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR,'static')]

MEDIA_ROOT = '/media/'
MEDIA_URL = '/media/'

# Static files (CSS, JavaScript, Images)
# STATIC_ROOT defines the absolute path where 'collectstatic' will be populated
# STATIC_URL defines the url used by the nginx webserver to serve up static files
# STATIC_FILES_DIRs defines additional project folders for static files
# Default is to include the project app folder: ./speciesnet/species/static

#STATICFILES_DIRS = [os.path.join(BASE_DIR,'species/static')]
#MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

### Default primary key field type ###

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

### Django REST Framework ###

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAdminUser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,
}

### CORS Configuration ###

CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://localhost:8001',
]

# Allow additional production origins via environment variables
SITE1_URL = os.environ.get('SITE1_URL', '')
SITE2_URL = os.environ.get('SITE2_URL', '')
if SITE1_URL:
    CORS_ALLOWED_ORIGINS.append(SITE1_URL)
if SITE2_URL:
    CORS_ALLOWED_ORIGINS.append(SITE2_URL)

### API Service Account ###

API_SERVICE_USERNAME = os.environ.get('API_SERVICE_USERNAME', 'api_service')
API_SERVICE_PASSWORD = os.environ.get('API_SERVICE_PASSWORD', 'changeme_in_production')

### Target API URL (Site2 URL for Site1, Site1 URL for Site2) ###

TARGET_API_URL = os.environ.get('TARGET_API_URL', 'http://localhost:8001')

