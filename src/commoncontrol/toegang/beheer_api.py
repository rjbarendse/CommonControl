"""Beheer van gebruikers, groepen, rechten en SSO — alleen voor beheerders."""

from __future__ import annotations

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404

from commoncontrol.api import Ongeldig, api_view, beheerder_vereist, body_van, ok
from commoncontrol.auditlog.models import log
from commoncontrol.beheer import registry

from .models import (
    NIVEAU_GEEN,
    NIVEAU_KEUZES,
    ComponentToegang,
    Gebruikersprofiel,
    OIDCInstelling,
)
from .oidc import OIDCFout, haal_discovery
from .rechten import rechten_van


def _gebruiker_dict(gebruiker: User) -> dict:
    profiel = getattr(gebruiker, "profiel", None)
    return {
        "id": gebruiker.pk,
        "gebruikersnaam": gebruiker.get_username(),
        "naam": gebruiker.get_full_name(),
        "email": gebruiker.email,
        "actief": gebruiker.is_active,
        "beheerder": gebruiker.is_superuser,
        "viaSso": bool(profiel and profiel.via_sso),
        "demo": bool(profiel and profiel.demo),
        "mfaIngesteld": bool(profiel and profiel.mfa_ingesteld),
        "laatsteLogin": profiel.laatste_login.isoformat()
        if profiel and profiel.laatste_login
        else None,
        "groepen": list(gebruiker.groups.values_list("name", flat=True)),
        "rechten": rechten_van(gebruiker) if not gebruiker.is_superuser else {"*": "schrijven"},
    }


@api_view("GET", "POST")
@beheerder_vereist
def gebruikers(request):
    if request.method == "GET":
        return ok(
            {
                "gebruikers": [
                    _gebruiker_dict(g)
                    for g in User.objects.all().prefetch_related("groups").order_by("username")
                ],
                "componenten": [
                    {"key": c.key, "label": c.label} for c in registry.COMPONENTEN
                ],
                "niveaus": [{"waarde": w, "label": l} for w, l in NIVEAU_KEUZES],
            }
        )

    gegevens = body_van(request)
    gebruikersnaam = (gegevens.get("gebruikersnaam") or "").strip()
    wachtwoord = gegevens.get("wachtwoord") or ""
    if not gebruikersnaam:
        raise Ongeldig("Vul een gebruikersnaam in.")
    if not wachtwoord:
        raise Ongeldig("Vul een wachtwoord in.")

    if gegevens.get("demo") and gegevens.get("beheerder"):
        raise Ongeldig("Een demo-account kan geen beheerder zijn.")

    gebruiker = User(
        username=gebruikersnaam,
        email=(gegevens.get("email") or "").strip(),
        first_name=(gegevens.get("naam") or "").strip()[:150],
        is_superuser=bool(gegevens.get("beheerder")),
        is_staff=bool(gegevens.get("beheerder")),
    )
    try:
        validate_password(wachtwoord, gebruiker)
    except ValidationError as exc:
        raise Ongeldig(" ".join(exc.messages)) from None

    gebruiker.set_password(wachtwoord)
    try:
        gebruiker.save()
    except IntegrityError:
        raise Ongeldig(f"'{gebruikersnaam}' bestaat al.", 409) from None

    profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    if gegevens.get("demo"):
        profiel.demo = True
        profiel.save(update_fields=["demo"])

    # Rechten en groepen horen in dezelfde handeling mee: wie ze in het formulier
    # invult verwacht niet dat ze stilzwijgend verdwijnen omdat de gebruiker
    # toevallig nieuw is.
    if "groepen" in gegevens:
        namen = [n for n in (gegevens.get("groepen") or []) if isinstance(n, str)]
        gebruiker.groups.set(Group.objects.filter(name__in=namen))
    if "rechten" in gegevens:
        _zet_rechten(gebruiker=gebruiker, groep=None, nieuw=gegevens["rechten"])

    log(request, "instelling", actie="gebruiker-aanmaken", doel=gebruikersnaam)
    return ok(_gebruiker_dict(gebruiker))


@api_view("PATCH", "DELETE")
@beheerder_vereist
def gebruiker(request, gebruiker_id: int):
    obj = get_object_or_404(User, pk=gebruiker_id)

    if request.method == "DELETE":
        if obj.pk == request.user.pk:
            raise Ongeldig("Je kunt je eigen account niet verwijderen.")
        naam = obj.get_username()
        obj.delete()
        log(request, "instelling", actie="gebruiker-verwijderen", doel=naam)
        return ok()

    gegevens = body_van(request)

    if "naam" in gegevens:
        obj.first_name = (gegevens.get("naam") or "").strip()[:150]
    if "email" in gegevens:
        obj.email = (gegevens.get("email") or "").strip()
    if "actief" in gegevens:
        if obj.pk == request.user.pk and not gegevens["actief"]:
            raise Ongeldig("Je kunt jezelf niet deactiveren.")
        obj.is_active = bool(gegevens["actief"])
    if "beheerder" in gegevens:
        if obj.pk == request.user.pk and not gegevens["beheerder"]:
            # Anders kan de laatste beheerder zichzelf buitensluiten en is er
            # niemand meer die rechten kan uitdelen.
            raise Ongeldig("Je kunt je eigen beheerdersrol niet afnemen.")
        obj.is_superuser = bool(gegevens["beheerder"])
        obj.is_staff = obj.is_superuser

    if gegevens.get("wachtwoord"):
        try:
            validate_password(gegevens["wachtwoord"], obj)
        except ValidationError as exc:
            raise Ongeldig(" ".join(exc.messages)) from None
        obj.set_password(gegevens["wachtwoord"])

    obj.save()

    if "groepen" in gegevens:
        namen = [n for n in (gegevens.get("groepen") or []) if isinstance(n, str)]
        obj.groups.set(Group.objects.filter(name__in=namen))

    if "demo" in gegevens:
        profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=obj)
        demo = bool(gegevens["demo"])
        if demo and obj.is_superuser:
            raise Ongeldig("Een beheerder kan geen demo-account zijn. Haal eerst de "
                           "beheerdersrol weg.")
        profiel.demo = demo
        profiel.save(update_fields=["demo"])

    if "mfaResetten" in gegevens and gegevens["mfaResetten"]:
        profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=obj)
        profiel.mfa_ingesteld = False
        profiel.totp_geheim = ""
        profiel.save(update_fields=["mfa_ingesteld", "totp_geheim_versleuteld"])
        log(request, "instelling", actie="mfa-resetten", doel=obj.get_username())

    if "rechten" in gegevens:
        _zet_rechten(gebruiker=obj, groep=None, nieuw=gegevens["rechten"])

    log(request, "instelling", actie="gebruiker-wijzigen", doel=obj.get_username())
    return ok(_gebruiker_dict(obj))


def _zet_rechten(*, gebruiker, groep, nieuw: dict) -> None:
    """Vervangt de rechtenset van één gebruiker of groep."""
    if not isinstance(nieuw, dict):
        raise Ongeldig("Rechten moeten als object worden aangeleverd.")

    geldige_niveaus = {waarde for waarde, _ in NIVEAU_KEUZES}
    for sleutel, niveau in nieuw.items():
        if sleutel not in registry.PER_SLEUTEL:
            raise Ongeldig(f"Onbekend component: {sleutel}")
        if niveau not in geldige_niveaus:
            raise Ongeldig(f"Onbekend rechtenniveau: {niveau}")

    ComponentToegang.objects.filter(gebruiker=gebruiker, groep=groep).delete()
    ComponentToegang.objects.bulk_create(
        [
            ComponentToegang(gebruiker=gebruiker, groep=groep, component=sleutel, niveau=niveau)
            for sleutel, niveau in nieuw.items()
            if niveau != NIVEAU_GEEN
        ]
    )


@api_view("GET", "POST")
@beheerder_vereist
def groepen(request):
    if request.method == "GET":
        return ok(
            [
                {
                    "id": g.pk,
                    "naam": g.name,
                    "leden": g.user_set.count(),
                    "rechten": {
                        r.component: r.niveau for r in g.component_rechten.all()
                    },
                }
                for g in Group.objects.all().order_by("name")
            ]
        )

    gegevens = body_van(request)
    naam = (gegevens.get("naam") or "").strip()
    if not naam:
        raise Ongeldig("Geef de groep een naam.")
    groep, gemaakt = Group.objects.get_or_create(name=naam)
    if not gemaakt:
        raise Ongeldig(f"De groep '{naam}' bestaat al.", 409)
    log(request, "instelling", actie="groep-aanmaken", doel=naam)
    return ok({"id": groep.pk, "naam": groep.name, "leden": 0, "rechten": {}})


@api_view("PATCH", "DELETE")
@beheerder_vereist
def groep(request, groep_id: int):
    obj = get_object_or_404(Group, pk=groep_id)

    if request.method == "DELETE":
        naam = obj.name
        obj.delete()
        log(request, "instelling", actie="groep-verwijderen", doel=naam)
        return ok()

    gegevens = body_van(request)
    if gegevens.get("naam"):
        obj.name = gegevens["naam"].strip()
        obj.save(update_fields=["name"])
    if "rechten" in gegevens:
        _zet_rechten(gebruiker=None, groep=obj, nieuw=gegevens["rechten"])
    log(request, "instelling", actie="groep-wijzigen", doel=obj.name)
    return ok(
        {
            "id": obj.pk,
            "naam": obj.name,
            "leden": obj.user_set.count(),
            "rechten": {r.component: r.niveau for r in obj.component_rechten.all()},
        }
    )


# ── SSO ─────────────────────────────────────────────────────────────────────


def _sso_dict(instelling: OIDCInstelling) -> dict:
    return {
        "actief": instelling.actief,
        "knopLabel": instelling.knop_label,
        "discoveryUrl": instelling.discovery_url,
        "clientId": instelling.client_id,
        "heeftClientSecret": bool(instelling.client_secret_versleuteld),
        "scopes": instelling.scopes,
        "claimGebruikersnaam": instelling.claim_gebruikersnaam,
        "claimEmail": instelling.claim_email,
        "claimGroepen": instelling.claim_groepen,
        "groepBeheerders": instelling.groep_beheerders,
        "gebruikersAanmaken": instelling.gebruikers_aanmaken,
    }


@api_view("GET", "PUT")
@beheerder_vereist
def sso(request):
    instelling = OIDCInstelling.huidige()

    if request.method == "PUT":
        gegevens = body_van(request)
        instelling.actief = bool(gegevens.get("actief"))
        instelling.knop_label = (gegevens.get("knopLabel") or "Inloggen met SSO").strip()
        instelling.discovery_url = (gegevens.get("discoveryUrl") or "").strip()
        instelling.client_id = (gegevens.get("clientId") or "").strip()
        instelling.scopes = (gegevens.get("scopes") or "openid email profile").strip()
        instelling.claim_gebruikersnaam = (
            gegevens.get("claimGebruikersnaam") or "preferred_username"
        ).strip()
        instelling.claim_email = (gegevens.get("claimEmail") or "email").strip()
        instelling.claim_groepen = (gegevens.get("claimGroepen") or "groups").strip()
        instelling.groep_beheerders = (gegevens.get("groepBeheerders") or "").strip()
        instelling.gebruikers_aanmaken = bool(gegevens.get("gebruikersAanmaken", True))
        # Leeg = ongewijzigd, zoals overal in deze applicatie.
        if gegevens.get("clientSecret"):
            instelling.client_secret = gegevens["clientSecret"]
        instelling.save()
        log(request, "instelling", actie="sso-opslaan",
            doel="ingeschakeld" if instelling.actief else "uitgeschakeld")

    return ok(_sso_dict(instelling))


@api_view("POST")
@beheerder_vereist
def sso_test(request):
    """
    Haalt het discovery-document op zodat je vóór het inschakelen weet of de
    URL klopt — een fout ontdekken tijdens het uitloggen is te laat.
    """
    gegevens = body_van(request)
    instelling = OIDCInstelling.huidige()
    tijdelijk = OIDCInstelling(
        discovery_url=(gegevens.get("discoveryUrl") or instelling.discovery_url).strip()
    )
    try:
        document = haal_discovery(tijdelijk, forceer=True)
    except OIDCFout as exc:
        return ok({"ok": False, "melding": str(exc)})

    redirect_uri = request.build_absolute_uri("/sso/callback/")
    return ok(
        {
            "ok": True,
            "melding": f"Verbinding met {document.get('issuer')} werkt.",
            "issuer": document.get("issuer"),
            "redirectUri": redirect_uri,
            "scopesOndersteund": document.get("scopes_supported") or [],
        }
    )
