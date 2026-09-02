"""Inloggen, tweede factor (TOTP) en SSO."""

from __future__ import annotations

import io

import pyotp
import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from commoncontrol.auditlog.models import ip_van, log, mislukte_pogingen

from .models import Gebruikersprofiel, OIDCInstelling
from .oidc import OIDCFout, groepen_uit_claims, start_url, verwerk_callback

MAX_MISLUKTE_POGINGEN = 10
UITGEVER = "CommonControl"


def _profiel(gebruiker) -> Gebruikersprofiel:
    profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    return profiel


def _veilige_next(request) -> str:
    """
    Alleen paden binnen deze applicatie zijn een geldige bestemming — anders is
    ?next= een open redirect naar een phishingsite.
    """
    doel = request.POST.get("next") or request.GET.get("next") or ""
    # Django's eigen controle in plaats van een zelfgeschreven prefixtest: die
    # laatste liet '/\\evil.com' door, en browsers lezen een backslash daar als
    # schuine streep — dus alsnog een omleiding naar een vreemde site.
    if url_has_allowed_host_and_scheme(doel, allowed_hosts=None,
                                       require_https=request.is_secure()):
        return doel
    return settings.LOGIN_REDIRECT_URL


def _na_login(request, gebruiker, doel: str) -> HttpResponseRedirect:
    profiel = _profiel(gebruiker)
    profiel.laatste_login = timezone.now()
    profiel.laatste_login_ip = ip_van(request)
    profiel.save(update_fields=["laatste_login", "laatste_login_ip"])

    if not profiel.mfa_vereist():
        request.session["mfa_ok"] = True
        return redirect(doel)

    request.session["mfa_doel"] = doel
    naam = "toegang:mfa_controle" if profiel.mfa_ingesteld else "toegang:mfa_instellen"
    return redirect(reverse(naam))


# ── Wachtwoordlogin ─────────────────────────────────────────────────────────


@csrf_protect
@require_http_methods(["GET", "POST"])
def inloggen(request):
    instelling = OIDCInstelling.huidige()
    context = {
        "sso_actief": instelling.is_bruikbaar(),
        "sso_label": instelling.knop_label,
        "next": _veilige_next(request),
    }

    if request.user.is_authenticated and request.session.get("mfa_ok"):
        return redirect(context["next"])

    if request.method == "GET":
        return render(request, "toegang/inloggen.html", context)

    gebruikersnaam = (request.POST.get("gebruikersnaam") or "").strip()
    wachtwoord = request.POST.get("wachtwoord") or ""

    if mislukte_pogingen(gebruikersnaam, ip_van(request)) >= MAX_MISLUKTE_POGINGEN:
        context["fout"] = (
            "Te veel mislukte pogingen. Probeer het over een kwartier opnieuw of "
            "neem contact op met een beheerder."
        )
        log(
            request,
            "login_mislukt",
            gelukt=False,
            gebruikersnaam=gebruikersnaam,
            detail="Geblokkeerd door de pogingenlimiet",
        )
        return render(request, "toegang/inloggen.html", context, status=429)

    gebruiker = authenticate(request, username=gebruikersnaam, password=wachtwoord)
    if gebruiker is None or not gebruiker.is_active:
        # Eén melding voor 'onbekende gebruiker' en 'fout wachtwoord': anders
        # vertelt het inlogscherm welke gebruikersnamen bestaan.
        context["fout"] = "Gebruikersnaam of wachtwoord klopt niet."
        log(request, "login_mislukt", gelukt=False, gebruikersnaam=gebruikersnaam)
        return render(request, "toegang/inloggen.html", context, status=401)

    login(request, gebruiker)
    request.session["mfa_ok"] = False
    log(request, "login", gebruikersnaam=gebruiker.get_username())
    return _na_login(request, gebruiker, context["next"])


@require_POST
def uitloggen(request):
    if request.user.is_authenticated:
        log(request, "uitloggen")
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


# ── Tweede factor ───────────────────────────────────────────────────────────


@csrf_protect
@require_http_methods(["GET", "POST"])
def mfa_instellen(request):
    """Koppelt een authenticator-app. Verplicht vóór het eerste gebruik."""
    profiel = _profiel(request.user)

    if profiel.mfa_ingesteld and not request.session.get("mfa_herstel"):
        return redirect("toegang:mfa_controle")

    geheim = request.session.get("mfa_nieuw_geheim")
    if not geheim:
        geheim = pyotp.random_base32()
        request.session["mfa_nieuw_geheim"] = geheim

    uri = pyotp.TOTP(geheim).provisioning_uri(
        name=request.user.get_username(), issuer_name=UITGEVER
    )
    context = {"geheim": geheim, "qr_svg": _qr_svg(uri)}

    if request.method == "POST":
        code = (request.POST.get("code") or "").replace(" ", "")
        if pyotp.TOTP(geheim).verify(code, valid_window=1):
            profiel.totp_geheim = geheim
            profiel.mfa_ingesteld = True
            profiel.save(update_fields=["totp_geheim_versleuteld", "mfa_ingesteld"])
            request.session.pop("mfa_nieuw_geheim", None)
            request.session.pop("mfa_herstel", None)
            request.session["mfa_ok"] = True
            log(request, "mfa", detail="Authenticator gekoppeld")
            return redirect(request.session.pop("mfa_doel", settings.LOGIN_REDIRECT_URL))
        context["fout"] = "Die code klopt niet. Controleer of de tijd op je telefoon goed staat."
        log(request, "mfa_mislukt", gelukt=False, detail="Code fout bij inschrijving")

    return render(request, "toegang/mfa_instellen.html", context)


@csrf_protect
@require_http_methods(["GET", "POST"])
def mfa_controle(request):
    profiel = _profiel(request.user)
    if not profiel.mfa_ingesteld:
        return redirect("toegang:mfa_instellen")

    context = {}
    if request.method == "POST":
        code = (request.POST.get("code") or "").replace(" ", "")
        gebruikersnaam = request.user.get_username()

        if mislukte_pogingen(gebruikersnaam, ip_van(request)) >= MAX_MISLUKTE_POGINGEN:
            context["fout"] = "Te veel mislukte pogingen. Probeer het over een kwartier opnieuw."
            return render(request, "toegang/mfa_controle.html", context, status=429)

        if pyotp.TOTP(profiel.totp_geheim).verify(code, valid_window=1):
            request.session["mfa_ok"] = True
            log(request, "mfa")
            return redirect(request.session.pop("mfa_doel", settings.LOGIN_REDIRECT_URL))

        context["fout"] = "Die code klopt niet."
        log(request, "mfa_mislukt", gelukt=False, gebruikersnaam=gebruikersnaam)
        return render(request, "toegang/mfa_controle.html", context, status=401)

    return render(request, "toegang/mfa_controle.html", context)


def _qr_svg(uri: str) -> str:
    """QR-code als inline SVG — geen Pillow en geen externe CDN nodig."""
    afbeelding = qrcode.make(
        uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2
    )
    buffer = io.BytesIO()
    afbeelding.save(buffer)
    return buffer.getvalue().decode("utf-8")


# ── SSO ─────────────────────────────────────────────────────────────────────


def _redirect_uri(request) -> str:
    return request.build_absolute_uri(reverse("toegang:sso_callback"))


@require_http_methods(["GET"])
def sso_start(request):
    instelling = OIDCInstelling.huidige()
    if not instelling.is_bruikbaar():
        return render(
            request,
            "toegang/sso_fout.html",
            {"melding": "SSO is niet ingeschakeld of niet volledig ingesteld."},
            status=400,
        )
    request.session["oidc_next"] = _veilige_next(request)
    try:
        return redirect(start_url(instelling, _redirect_uri(request), request.session))
    except OIDCFout as exc:
        log(request, "sso_mislukt", gelukt=False, detail=str(exc))
        return render(request, "toegang/sso_fout.html", {"melding": str(exc)}, status=502)


@require_http_methods(["GET"])
def sso_callback(request):
    instelling = OIDCInstelling.huidige()
    verwacht = request.session.pop("oidc_state", None)
    nonce = request.session.pop("oidc_nonce", None)
    doel = request.session.pop("oidc_next", settings.LOGIN_REDIRECT_URL)

    fout = request.GET.get("error")
    if fout:
        omschrijving = request.GET.get("error_description", "")
        melding = f"{fout}: {omschrijving}".strip().strip(":").strip()
        log(request, "sso_mislukt", gelukt=False, detail=melding)
        return render(request, "toegang/sso_fout.html", {"melding": melding}, status=400)

    state = request.GET.get("state")
    code = request.GET.get("code")
    if not verwacht or state != verwacht:
        log(request, "sso_mislukt", gelukt=False, detail="State komt niet overeen")
        return render(
            request,
            "toegang/sso_fout.html",
            {
                "melding": "De inlogpoging is verlopen of komt niet van dit apparaat. "
                "Probeer het opnieuw."
            },
            status=400,
        )
    if not code:
        return render(
            request,
            "toegang/sso_fout.html",
            {"melding": "Geen autorisatiecode ontvangen."},
            status=400,
        )

    try:
        claims = verwerk_callback(instelling, code, _redirect_uri(request), nonce)
    except OIDCFout as exc:
        log(request, "sso_mislukt", gelukt=False, detail=str(exc))
        return render(request, "toegang/sso_fout.html", {"melding": str(exc)}, status=502)

    gebruikersnaam = (
        claims.get(instelling.claim_gebruikersnaam)
        or claims.get("email")
        or claims.get("sub")
        or ""
    ).strip()
    if not gebruikersnaam:
        melding = "De identity provider gaf geen bruikbare gebruikersnaam terug."
        log(request, "sso_mislukt", gelukt=False, detail=melding)
        return render(request, "toegang/sso_fout.html", {"melding": melding}, status=400)

    email = (claims.get(instelling.claim_email) or "").strip()
    groepen = groepen_uit_claims(claims, instelling.claim_groepen)

    gebruiker = User.objects.filter(username__iexact=gebruikersnaam).first()
    if gebruiker is None and email:
        gebruiker = User.objects.filter(email__iexact=email).first()

    if gebruiker is None:
        if not instelling.gebruikers_aanmaken:
            melding = (
                f"{gebruikersnaam} is hier niet bekend en automatisch aanmaken staat uit. "
                "Vraag een beheerder om een account."
            )
            log(
                request,
                "sso_mislukt",
                gelukt=False,
                gebruikersnaam=gebruikersnaam,
                detail=melding,
            )
            return render(request, "toegang/sso_fout.html", {"melding": melding}, status=403)
        gebruiker = User.objects.create_user(username=gebruikersnaam, email=email)
        gebruiker.set_unusable_password()
        gebruiker.save()

    if not gebruiker.is_active:
        melding = "Dit account is gedeactiveerd."
        log(request, "sso_mislukt", gelukt=False, gebruikersnaam=gebruikersnaam, detail=melding)
        return render(request, "toegang/sso_fout.html", {"melding": melding}, status=403)

    if email and gebruiker.email != email:
        gebruiker.email = email

    # Beheerdersrol volgt de IdP-groep, in beide richtingen: wie er niet meer in
    # zit verliest de rol ook weer. Zonder dat laatste blijft een oud-beheerder
    # via SSO gewoon beheerder.
    if instelling.groep_beheerders:
        is_beheerder = instelling.groep_beheerders in groepen
        gebruiker.is_superuser = is_beheerder
        gebruiker.is_staff = is_beheerder
    gebruiker.save()

    _synchroniseer_groepen(gebruiker, groepen)

    profiel = _profiel(gebruiker)
    profiel.via_sso = True
    profiel.save(update_fields=["via_sso"])

    login(request, gebruiker)
    request.session["mfa_ok"] = True  # tweede factor is de verantwoordelijkheid van de IdP
    log(
        request,
        "sso",
        gebruikersnaam=gebruiker.get_username(),
        detail=f"Groepen: {', '.join(groepen) or 'geen'}",
    )
    return _na_login(request, gebruiker, doel if doel.startswith("/") else "/")


def _synchroniseer_groepen(gebruiker, namen: list[str]) -> None:
    """
    Koppelt de gebruiker aan de Django-groepen met dezelfde naam als de
    IdP-groepen. Groepen worden hier NIET aangemaakt: welke groepen rechten
    krijgen is een bewuste keuze van de beheerder, geen bijproduct van een login.
    """
    if not namen:
        return
    bestaand = list(Group.objects.filter(name__in=namen))
    if bestaand:
        gebruiker.groups.set(bestaand)


# ── Overig ──────────────────────────────────────────────────────────────────


def gezond(request):
    """Liveness/readiness-probe. Bewust zonder databasequery."""
    return JsonResponse({"status": "ok", "versie": settings.APP_VERSIE})
