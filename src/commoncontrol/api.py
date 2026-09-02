"""Kleine hulpjes voor de JSON-API van CommonControl."""

from __future__ import annotations

import json
from functools import wraps

from django.http import Http404, JsonResponse


class Ongeldig(Exception):
    """Invoerfout van de gebruiker; wordt een nette 400."""

    def __init__(self, melding: str, status: int = 400):
        super().__init__(melding)
        self.melding = melding
        self.status = status


def body_van(request) -> dict:
    if not request.body:
        return {}
    try:
        gegevens = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Ongeldig("De verstuurde gegevens zijn geen geldige JSON.") from exc
    if not isinstance(gegevens, dict):
        raise Ongeldig("De verstuurde gegevens moeten een object zijn.")
    return gegevens


def ok(data=None, **extra) -> JsonResponse:
    inhoud = {"ok": True}
    if data is not None:
        inhoud["data"] = data
    inhoud.update(extra)
    return JsonResponse(inhoud)


def fout(melding: str, status: int = 400, **extra) -> JsonResponse:
    return JsonResponse({"ok": False, "fout": melding, **extra}, status=status)


def api_view(*methoden: str):
    """
    Beperkt een view tot bepaalde methoden en vertaalt Ongeldig naar JSON.

    Zonder dit zou elke view dezelfde try/except en methodecontrole herhalen —
    en zou één vergeten controle een uitzonderingspagina in plaats van een nette
    melding opleveren.
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methoden:
                return fout(f"Methode {request.method} niet toegestaan.", 405)
            try:
                return view(request, *args, **kwargs)
            except Ongeldig as exc:
                return fout(exc.melding, exc.status)
            except Http404 as exc:
                # Django antwoordt op een Http404 standaard met een HTML-pagina.
                # De interface kan daar niets mee en toont dan alleen "de server
                # gaf HTTP 404" — een melding die niets verklaart. Onder /api/
                # moet het antwoord altijd JSON zijn.
                return fout(str(exc) or "Niet gevonden.", 404)

        return wrapper

    return decorator


def eerste_of_fout(queryset, melding: str, status: int = 404):
    """
    Als get_object_or_404, maar met een uitlegbare melding in plaats van een
    kale HTML-404. Gebruik dit overal waar de gebruiker de fout kan herstellen.
    """
    obj = queryset.first()
    if obj is None:
        raise Ongeldig(melding, status)
    return obj


def beheerder_vereist(view):
    """Alleen een beheerder (superuser) mag instellingen en rechten wijzigen."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return fout("Alleen een beheerder mag dit.", 403)
        return view(request, *args, **kwargs)

    return wrapper
