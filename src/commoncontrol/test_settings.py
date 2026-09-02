"""
Instellingen voor het draaien van de testsuite.

Draai de tests met:
    python manage.py test tests --settings=commoncontrol.test_settings

Twee afwijkingen ten opzichte van productie, allebei bewust:

1. SQLite in plaats van PostgreSQL, zodat de suite draait zonder database-server.
   De applicatie gebruikt geen PostgreSQL-specifieke velden, dus dit dekt het
   gedrag; alleen gelijktijdigheid test je er niet mee.

2. Gewone staticfiles-opslag in plaats van de manifest-variant van WhiteNoise.
   Die laatste eist een `collectstatic` vooraf en zou anders elke test die een
   template rendert laten falen op een ontbrekende manifest-regel.
"""

import os

# Moet vóór de import: settings.py weigert te starten zonder SECRET_KEY, en
# dat is precies de bedoeling — deze broncode is openbaar, dus er hoort geen
# bruikbare standaardsleutel in te staan.
os.environ.setdefault("SECRET_KEY", "sleutel-uitsluitend-voor-de-testsuite-niet-in-productie")

from commoncontrol.settings import *  # noqa: E402,F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

SECRET_KEY = "sleutel-uitsluitend-voor-de-testsuite"

# De testclient doet http-verzoeken; met de https-omleiding aan zou elke test
# een 301 krijgen in plaats van het echte antwoord.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
COMMONCONTROL_ENCRYPTIE_SLEUTEL = ""
DEBUG = False

# Een echte hash per wachtwoordcontrole maakt de suite onnodig traag.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Geen logregels door de testuitvoer heen.
LOGGING["root"]["level"] = "ERROR"  # noqa: F405

LOGGING["loggers"]["django.request"]["level"] = "ERROR"  # noqa: F405
