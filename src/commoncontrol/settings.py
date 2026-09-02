"""
Django-instellingen voor CommonControl.

Alles wat per omgeving verschilt komt uit environment-variabelen, zodat hetzelfde
image op elk platform draait (K8s, Docker Compose, of lokaal).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent          # .../src


def _env(naam: str, standaard: str = "") -> str:
    return os.environ.get(naam, standaard)


def _env_bool(naam: str, standaard: bool = False) -> bool:
    waarde = os.environ.get(naam)
    if waarde is None:
        return standaard
    return waarde.strip().lower() in ("1", "true", "yes", "ja", "on")


def _env_lijst(naam: str, standaard: str = "") -> list[str]:
    ruw = os.environ.get(naam, standaard)
    return [deel.strip() for deel in ruw.split(",") if deel.strip()]


# ── Basis ────────────────────────────────────────────────────────────────────

DEBUG = _env_bool("DEBUG", False)

# Bewust GEEN bruikbare standaardwaarde. Deze broncode is openbaar: een
# meegeleverde sleutel is een publiek bekende sleutel, en daarmee kan iedereen
# sessies vervalsen en — omdat de versleuteling van opgeslagen API-credentials
# eruit wordt afgeleid — al die credentials ontsleutelen. Zonder SECRET_KEY
# start de applicatie daarom niet, behalve in DEBUG-modus voor lokaal werk.
SECRET_KEY = _env("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "alleen-voor-lokale-ontwikkeling-nooit-in-productie-gebruiken"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY is niet ingesteld. Genereer er een met:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
            "en zet die in de omgeving. Verander hem daarna nooit meer zonder "
            "ENCRYPTION_KEY apart te hebben vastgelegd: de opgeslagen "
            "API-credentials zijn er anders niet meer uit te lezen."
        )
elif len(SECRET_KEY) < 32 and not DEBUG:
    import warnings

    warnings.warn(
        "SECRET_KEY is korter dan 32 tekens; dat is te kort voor productie.",
        stacklevel=2,
    )

ALLOWED_HOSTS = _env_lijst("ALLOWED_HOSTS", "localhost,127.0.0.1")

# Achter Traefik/nginx komt het verzoek als http binnen terwijl de browser https
# gebruikt. Zonder deze header ziet Django het als onveilig en weigert het de
# CSRF-controle op elk POST-verzoek.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = _env_lijst("CSRF_TRUSTED_ORIGINS") or [
    f"https://{host}" for host in ALLOWED_HOSTS if host not in ("localhost", "127.0.0.1", "*")
]

# Kubernetes-probes komen binnen op het IP van de pod, niet op de hostnaam.
# Zonder deze regel wijst Django ze af met een 400 en gaat de pod eindeloos
# herstarten terwijl de applicatie zelf prima werkt.
_pod_ip = _env("POD_IP", "")
if _pod_ip and _pod_ip not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_pod_ip)

# Een beheerconsole met schrijfrechten op zaakregistraties hoort niet in een
# iframe van een vreemde site te kunnen staan.
X_FRAME_OPTIONS = "DENY"

# Alles over https. Achter een ingress die TLS afhandelt merkt niemand hier iets
# van (die zet X-Forwarded-Proto), maar een rechtstreeks http-verzoek wordt zo
# alsnog omgeleid in plaats van in leesbare vorm over de lijn te gaan.
SECURE_SSL_REDIRECT = _env_bool("SSL_REDIRECT", not DEBUG)
# ...behalve de gezondheidscontrole: die wordt door kubelet en de Docker-
# healthcheck op 127.0.0.1 over http opgevraagd, en een omleiding naar https
# zou daar op een certificaatfout stuklopen.
SECURE_REDIRECT_EXEMPT = [r"^gezond/$"]

# HSTS: een jaar, maar bewust ZONDER includeSubDomains en zonder preload. CG
# Control draait op een subdomein van de gemeente; die instelling zou het hele
# domein raken en dat is niet aan deze applicatie. Zet HSTS_SECONDS=0 als het
# certificaat nog niet rond is.
SECURE_HSTS_SECONDS = int(_env("HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("HSTS_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = _env_bool("COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = _env_bool("COOKIE_SECURE", not DEBUG)
# Sessie verloopt na inactiviteit (standaard 8 uur werkdag).
SESSION_COOKIE_AGE = int(_env("SESSION_COOKIE_AGE", "28800"))
SESSION_SAVE_EVERY_REQUEST = True


# ── Applicaties ──────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # CommonControl
    "commoncontrol.toegang",
    "commoncontrol.verbindingen",
    "commoncontrol.beheer",
    "commoncontrol.auditlog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Dwingt inloggen + TOTP-MFA af op ALLES wat niet expliciet vrijgegeven is.
    # Bewust middleware en geen decorator: een vergeten decorator op een nieuwe
    # view zou anders stilzwijgend een gat in de beveiliging opleveren.
    "commoncontrol.toegang.middleware.ToegangMiddleware",
]

ROOT_URLCONF = "commoncontrol.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "commoncontrol.toegang.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "commoncontrol.wsgi.application"


# ── Database ─────────────────────────────────────────────────────────────────

# PostgreSQL in productie. DB_ENGINE kan op sqlite worden gezet om het project
# te controleren of te testen zonder database-server; dat is bewust geen
# productie-optie (gelijktijdige schrijfacties gaan daar mis).
DATABASES = {
    "default": {
        "ENGINE": _env("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": _env("DB_NAME", "commoncontrol"),
        "USER": _env("DB_USER", "commoncontrol"),
        "PASSWORD": _env("DB_PASSWORD", ""),
        "HOST": _env("DB_HOST", "localhost"),
        "PORT": _env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── Wachtwoordbeleid ─────────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/inloggen/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/inloggen/"


# ── Taal en tijd ─────────────────────────────────────────────────────────────

LANGUAGE_CODE = "nl-nl"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True


# ── Statische bestanden ──────────────────────────────────────────────────────
# gunicorn serveert zelf géén statische bestanden; WhiteNoise doet dat wel,
# zodat er geen aparte nginx-container nodig is.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static-collected"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


# ── CommonControl-specifiek ─────────────────────────────────────────────────────

# Sleutel waarmee opgeslagen API-secrets versleuteld worden (Fernet).
# Leeg laten mag: dan wordt hij deterministisch afgeleid uit SECRET_KEY, zodat
# een standaardinstallatie gewoon werkt. Zet 'm expliciet als je SECRET_KEY ooit
# wilt kunnen roteren zónder alle opgeslagen credentials te verliezen.
COMMONCONTROL_ENCRYPTIE_SLEUTEL = _env("ENCRYPTION_KEY", "")

# Time-out (seconden) op elke uitgaande aanroep naar een CommonGround-component.
COMMONCONTROL_HTTP_TIMEOUT = float(_env("HTTP_TIMEOUT", "20"))

# Certificaatcontrole op uitgaande aanroepen. Alleen uitzetten voor een
# testomgeving met een self-signed certificaat — nooit in productie.
COMMONCONTROL_VERIFY_TLS = _env_bool("VERIFY_TLS", True)

# client_id/user_id waarmee CommonControl zich bij de ZGW-API's meldt. Komt terug
# in de auditlogs van OpenZaak zelf, dus herkenbaar houden.
COMMONCONTROL_ZGW_USER_ID = _env("ZGW_USER_ID", "commoncontrol")
COMMONCONTROL_ZGW_USER_WEERGAVE = _env("ZGW_USER_WEERGAVE", "CommonControl beheer")

APP_VERSIE = (BASE_DIR.parent / "version.txt").read_text(encoding="utf-8").strip() \
    if (BASE_DIR.parent / "version.txt").exists() else "0.0.0"


# ── Logging ──────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "eenvoudig": {"format": "%(asctime)s %(levelname)-7s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "eenvoudig"},
    },
    "root": {"handlers": ["console"], "level": _env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # httpx logt elk verzoek op INFO — dat zou bij elke paginaweergave
        # tientallen regels opleveren.
        "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "httpcore": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
