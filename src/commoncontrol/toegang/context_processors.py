"""Gegevens die elke template nodig heeft."""

from django.conf import settings


def app_context(request):
    return {
        "app_naam": "CommonControl",
        "app_versie": settings.APP_VERSIE,
    }
