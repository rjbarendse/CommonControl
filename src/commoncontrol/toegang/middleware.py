"""
Toegangspoort van CommonControl.

Bewust middleware in plaats van decorators per view: een nieuwe view die je
vergeet te decoreren zou anders zonder inloggen bereikbaar zijn. Hier is de
standaard "afgeschermd" en moet een pad expliciet worden vrijgegeven.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

# Paden die zónder sessie bereikbaar moeten zijn. Alles wat hier niet bij staat
# vereist een ingelogde gebruiker mét voltooide tweede factor.
# Exacte paden — bewust géén prefixen. Met "/gezond" als prefix zou een later
# toegevoegde "/gezondheidsrapport" er ongemerkt onder vallen en zonder inloggen
# bereikbaar zijn.
VRIJE_PADEN = frozenset({
    "/inloggen/",
    "/uitloggen/",
    "/gezond/",
    "/favicon.ico",
    "/favicon.svg",
})

# Prefixen die per se een prefix moeten zijn (ze hebben ondergelegen paden).
VRIJE_PREFIXEN = (
    "/sso/",
    "/static/",
)

# Paden die je met een ingelogde sessie maar zónder voltooide MFA moet kunnen
# bereiken — anders kun je de tweede factor nooit instellen of invoeren.
MFA_PADEN = ("/mfa/",)

# Methoden die niets veranderen.
LEESMETHODEN = frozenset({"GET", "HEAD", "OPTIONS"})

# Waar een demo-account tóch mag posten: inloggen, uitloggen en de tweede factor.
# Zonder die uitzonderingen zou zo'n account niet eens binnen kunnen komen.
DEMO_UITZONDERINGEN = ("/inloggen/", "/uitloggen/", "/mfa/")


def _is_api(request) -> bool:
    return request.path.startswith("/api/")


class ToegangMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        pad = request.path

        if pad in VRIJE_PADEN or pad.startswith(VRIJE_PREFIXEN):
            return self.get_response(request)

        gebruiker = getattr(request, "user", None)
        if gebruiker is None or not gebruiker.is_authenticated:
            if _is_api(request):
                return JsonResponse(
                    {"fout": "Niet ingelogd.", "code": "niet_ingelogd"}, status=401
                )
            doel = f"{settings.LOGIN_URL}?{urlencode({'next': request.get_full_path()})}"
            return redirect(doel)

        if not request.user.is_active:
            if _is_api(request):
                return JsonResponse(
                    {"fout": "Account is gedeactiveerd.", "code": "inactief"}, status=403
                )
            return redirect("toegang:uitloggen")

        # Demo-account: alles inzien, niets wijzigen. Bewust hier en niet alleen
        # in de rechtencontrole — dan geldt het ook voor een view die de
        # rechtencontrole vergeet, en voor endpoints die niets met componenten
        # te maken hebben.
        if (request.method not in LEESMETHODEN
                and not pad.startswith(DEMO_UITZONDERINGEN)
                and _profiel(request.user).demo):
            melding = "Dit is een demo-account: inzien mag, wijzigen niet."
            if _is_api(request):
                return JsonResponse({"fout": melding, "code": "demo"}, status=403)
            return HttpResponseForbidden(melding)

        if self._mfa_nodig(request):
            if pad.startswith(MFA_PADEN):
                return self.get_response(request)
            if _is_api(request):
                return JsonResponse(
                    {"fout": "Tweede factor nog niet voltooid.", "code": "mfa_vereist"},
                    status=401,
                )
            profiel = _profiel(request.user)
            naam = "toegang:mfa_controle" if profiel.mfa_ingesteld else "toegang:mfa_instellen"
            return redirect(reverse(naam))

        # MFA voltooid (of niet vereist): de MFA-schermen zelf hebben geen
        # functie meer, dus terug naar de app.
        if pad.startswith(MFA_PADEN) and not pad.startswith("/mfa/opnieuw"):
            return redirect("/")

        return self.get_response(request)

    @staticmethod
    def _mfa_nodig(request) -> bool:
        if request.session.get("mfa_ok"):
            return False
        return _profiel(request.user).mfa_vereist()


def _profiel(gebruiker):
    """Haalt (of maakt) het profiel bij een gebruiker."""
    from .models import Gebruikersprofiel

    profiel = getattr(gebruiker, "profiel", None)
    if profiel is None:
        profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    return profiel
