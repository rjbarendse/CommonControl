"""API voor omgevingen en verbindingen."""

from __future__ import annotations

import re
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from django.db import IntegrityError
from django.utils import timezone

from commoncontrol.api import (
    Ongeldig,
    api_view,
    beheerder_vereist,
    body_van,
    eerste_of_fout,
    fout,
    ok,
)
from commoncontrol.beheer.views import _geen_omgeving
from commoncontrol.toegang import rechten
from commoncontrol.auditlog.models import log
from commoncontrol.beheer import registry

from .client import ApiFout, client_voor
from .models import AUTH_KEUZES, AUTH_SESSIE, AUTH_TOKEN, AUTH_ZGW, Omgeving, Verbinding

# Waarde die de interface stuurt als een geheim ongewijzigd moet blijven. Het
# echte geheim wordt nooit teruggestuurd naar de browser, dus "leeg laten =
# ongewijzigd" is de enige werkbare afspraak — dezelfde als in KubeManager.
ONGEWIJZIGD = ""


def _slug(tekst: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (tekst or "").lower()).strip("-")
    return slug or "omgeving"


# ── Omgevingen ──────────────────────────────────────────────────────────────


@api_view("GET", "POST")
def omgevingen(request):
    if request.method == "GET":
        return ok(
            [
                {
                    "slug": o.slug,
                    "naam": o.naam,
                    "domein": o.domein,
                    "opmerking": o.opmerking,
                    "standaard": o.is_standaard,
                    "aantalVerbindingen": o.verbindingen.count(),
                }
                for o in Omgeving.objects.all()
            ]
        )

    if not request.user.is_superuser:
        return fout("Alleen een beheerder mag omgevingen aanmaken.", 403)

    gegevens = body_van(request)
    naam = (gegevens.get("naam") or "").strip()
    if not naam:
        raise Ongeldig("Geef de omgeving een naam.")

    slug = _slug(gegevens.get("slug") or naam)
    basis, teller = slug, 2
    while Omgeving.objects.filter(slug=slug).exists():
        slug, teller = f"{basis}-{teller}", teller + 1

    try:
        omgeving = Omgeving.objects.create(
            naam=naam,
            slug=slug,
            domein=(gegevens.get("domein") or "").strip().lower(),
            opmerking=(gegevens.get("opmerking") or "").strip(),
            is_standaard=bool(gegevens.get("standaard"))
            or not Omgeving.objects.exists(),
        )
    except IntegrityError:
        raise Ongeldig(f"Er bestaat al een omgeving met de naam '{naam}'.", 409) from None

    log(request, "instelling", omgeving=omgeving.slug, actie="omgeving-aanmaken",
        doel=omgeving.naam)
    return ok({"slug": omgeving.slug, "naam": omgeving.naam})


@api_view("GET", "PATCH", "DELETE")
@beheerder_vereist
def omgeving(request, slug: str):
    obj = eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))

    if request.method == "DELETE":
        naam = obj.naam
        obj.delete()
        log(request, "instelling", actie="omgeving-verwijderen", doel=naam)
        return ok()

    if request.method == "PATCH":
        gegevens = body_van(request)
        for veld, attribuut in (
            ("naam", "naam"), ("domein", "domein"), ("opmerking", "opmerking")
        ):
            if veld in gegevens:
                setattr(obj, attribuut, (gegevens.get(veld) or "").strip())
        if "standaard" in gegevens:
            obj.is_standaard = bool(gegevens["standaard"])
        obj.save()
        log(request, "instelling", omgeving=obj.slug, actie="omgeving-wijzigen",
            doel=obj.naam)

    return ok(
        {
            "slug": obj.slug,
            "naam": obj.naam,
            "domein": obj.domein,
            "opmerking": obj.opmerking,
            "standaard": obj.is_standaard,
            "verbindingen": [v.als_dict() for v in obj.verbindingen.all()],
        }
    )


# ── Verbindingen ────────────────────────────────────────────────────────────


@api_view("GET", "PUT", "DELETE")
def verbinding(request, slug: str, component_sleutel: str):
    if component_sleutel not in registry.PER_SLEUTEL:
        raise Ongeldig(f"Onbekend component: {component_sleutel}", 404)
    component = registry.component(component_sleutel)
    omgeving_obj = eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))
    bestaand = Verbinding.objects.filter(
        omgeving=omgeving_obj, component=component_sleutel
    ).first()

    if request.method == "GET":
        # Ook zonder geheimen verraadt dit het adres en het client-id van een
        # component; dat hoort alleen zichtbaar te zijn voor wie het mag beheren.
        if not rechten.mag_lezen(request.user, component_sleutel):
            return fout("Je hebt geen toegang tot dit component.", 403)
        return ok(bestaand.als_dict() if bestaand else None)

    if not request.user.is_superuser:
        return fout("Alleen een beheerder mag verbindingen wijzigen.", 403)

    if request.method == "DELETE":
        if bestaand:
            bestaand.delete()
        log(request, "verbinding", omgeving=slug, component=component_sleutel,
            actie="verwijderen")
        return ok()

    gegevens = body_van(request)
    obj = bestaand or Verbinding(omgeving=omgeving_obj, component=component_sleutel)

    basis_url = (gegevens.get("basisUrl") or "").strip().rstrip("/")
    if not basis_url:
        raise Ongeldig("Vul de basis-URL van het component in.")
    if not basis_url.startswith(("http://", "https://")):
        basis_url = "https://" + basis_url
    obj.basis_url = basis_url

    auth_type = gegevens.get("authType") or component.auth
    if auth_type not in dict(AUTH_KEUZES):
        raise Ongeldig(f"Onbekende authenticatievorm: {auth_type}")
    obj.auth_type = auth_type

    obj.actief = bool(gegevens.get("actief", True))
    obj.client_id = (gegevens.get("clientId") or "").strip()
    obj.gebruikersnaam = (gegevens.get("gebruikersnaam") or "").strip()
    prefix = (gegevens.get("tokenPrefix") or "").strip()
    obj.token_prefix = prefix or component.token_prefix

    # Geheimen: alleen overschrijven als er daadwerkelijk iets nieuws is
    # ingevuld. Zo kun je de URL aanpassen zonder het secret opnieuw te typen.
    if gegevens.get("secret", ONGEWIJZIGD):
        obj.secret = gegevens["secret"]
    if gegevens.get("token", ONGEWIJZIGD):
        obj.token = gegevens["token"]
    if gegevens.get("wachtwoord", ONGEWIJZIGD):
        obj.wachtwoord = gegevens["wachtwoord"]

    # Overschakelen naar een andere authenticatievorm laat de oude geheimen niet
    # slingeren; die horen niet bij de nieuwe vorm en zouden alleen verwarren.
    if auth_type != AUTH_ZGW:
        obj.secret_versleuteld = ""
    if auth_type != AUTH_TOKEN:
        obj.token_versleuteld = ""
    if auth_type != AUTH_SESSIE:
        obj.wachtwoord_versleuteld = ""

    obj.save()
    log(request, "verbinding", omgeving=slug, component=component_sleutel,
        actie="opslaan", doel=obj.basis)
    return ok(obj.als_dict())


@api_view("POST")
def test_verbinding(request, slug: str, component_sleutel: str):
    """Probeert de verbinding echt uit en slaat het resultaat op."""
    if component_sleutel not in registry.PER_SLEUTEL:
        raise Ongeldig(f"Onbekend component: {component_sleutel}", 404)
    component = registry.component(component_sleutel)
    # Een test doet een uitgaande aanroep namens deze installatie; dat hoort niet
    # te kunnen door iemand zonder toegang tot dat component.
    if not rechten.mag_lezen(request.user, component_sleutel):
        return fout("Je hebt geen toegang tot dit component.", 403)
    omgeving_obj = eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))
    obj = Verbinding.objects.filter(
        omgeving=omgeving_obj, component=component_sleutel
    ).first()
    if obj is None:
        raise Ongeldig("Deze verbinding bestaat nog niet. Sla hem eerst op.", 404)
    if not obj.actief:
        # De gegevens blijven bewaard als je een component uitvinkt, maar dan
        # hoort er ook geen verkeer meer naartoe te gaan.
        raise Ongeldig(
            "Dit component staat niet als 'in gebruik' aangevinkt onder Configuratie; "
            "er wordt daarom niets naartoe gestuurd.",
            409,
        )

    try:
        uitkomst = client_voor(obj, request.user).test(component.probe)
    except ApiFout as exc:
        uitkomst = {"ok": False, "status": exc.status, "melding": exc.melding,
                    "tokenPrefix": obj.token_prefix}

    obj.laatste_test_op = timezone.now()
    obj.laatste_test_ok = uitkomst["ok"]
    obj.laatste_test_melding = uitkomst["melding"][:2000]
    # Heeft de test een ander token-voorvoegsel nodig gehad, dan is dát voortaan
    # het juiste — anders zou elke volgende aanroep opnieuw op 401 stuiten.
    if uitkomst.get("tokenPrefix"):
        obj.token_prefix = uitkomst["tokenPrefix"]
    obj.save(
        update_fields=[
            "laatste_test_op", "laatste_test_ok", "laatste_test_melding", "token_prefix"
        ]
    )
    return ok(uitkomst)


@api_view("POST")
def test_alles(request, slug: str):
    """Test alle ingestelde verbindingen van een omgeving in één keer."""
    omgeving_obj = eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))
    resultaten = {}
    for obj in omgeving_obj.verbindingen.all():
        if obj.component not in registry.PER_SLEUTEL:
            continue
        if not rechten.mag_lezen(request.user, obj.component):
            continue
        if not obj.actief:
            # Uitgevinkt onder Configuratie: overslaan. Anders zou deze knop
            # verkeer sturen naar een component dat de beheerder juist heeft
            # uitgezet — en een foutmelding opleveren over iets wat niet in
            # gebruik is.
            continue
        component = registry.component(obj.component)
        try:
            uitkomst = client_voor(obj, request.user).test(component.probe)
        except ApiFout as exc:
            uitkomst = {"ok": False, "status": exc.status, "melding": exc.melding}
        obj.laatste_test_op = timezone.now()
        obj.laatste_test_ok = uitkomst["ok"]
        obj.laatste_test_melding = uitkomst["melding"][:2000]
        if uitkomst.get("tokenPrefix"):
            obj.token_prefix = uitkomst["tokenPrefix"]
        obj.save(
            update_fields=[
                "laatste_test_op", "laatste_test_ok", "laatste_test_melding", "token_prefix"
            ]
        )
        resultaten[obj.component] = uitkomst
    return ok(resultaten)


# ── Configuratie: hoofddomein + welke componenten in gebruik zijn ───────────

# Een hostnaam mag alleen letters, cijfers, koppeltekens en punten bevatten, en
# moet minstens één punt hebben. Bewust streng: deze waarde wordt straks de basis
# van elke uitgaande aanroep.
HOSTNAAM = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

DNS_TIMEOUT = 5.0

# Gedeelde pool met een harde bovengrens: een vastgelopen opzoeking bezet één
# werker en niet een steeds groeiend aantal threads. Zijn ze alle vier bezet,
# dan loopt het volgende verzoek gewoon in zijn eigen time-out en krijgt de
# gebruiker een nette melding.
_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns")


def _host_met_poort(waarde: str) -> str:
    """Haalt schema, pad en eventuele inloggegevens weg; poort blijft staan."""
    waarde = (waarde or "").strip().lower()
    waarde = re.sub(r"^[a-z]+://", "", waarde)
    waarde = waarde.split("/")[0].split("?")[0].split("#")[0]
    return waarde.split("@")[-1]


def _alleen_host(waarde: str) -> str:
    return _host_met_poort(waarde).split(":")[0]


def _basis_uit_hostnaam(waarde: str) -> str:
    host = _host_met_poort(waarde)
    if not host:
        return ""
    if not HOSTNAAM.match(host.split(":")[0]):
        raise Ongeldig(f"'{waarde}' is geen geldige hostnaam.")
    return f"https://{host}"


def _configuratie_dict(omgeving: Omgeving) -> dict:
    per_component = {v.component: v for v in omgeving.verbindingen.all()}
    regels = []
    for component in registry.COMPONENTEN:
        verbinding = per_component.get(component.key)
        voorstel = (f"{component.subdomein}.{omgeving.domein}"
                    if omgeving.domein and component.subdomein else "")
        regels.append({
            "component": component.key,
            "label": component.label,
            "beschrijving": component.beschrijving,
            "subdomein": component.subdomein,
            "auth": component.auth,
            "gebruikt": bool(verbinding and verbinding.actief),
            "hostnaam": _host_met_poort(verbinding.basis) if verbinding else "",
            "voorstel": voorstel,
            "heeftGegevens": bool(verbinding),
            "ingevuld": bool(verbinding and verbinding.is_ingevuld()),
            "laatsteTestOk": verbinding.laatste_test_ok if verbinding else None,
        })
    return {
        "omgeving": {"slug": omgeving.slug, "naam": omgeving.naam, "domein": omgeving.domein},
        "componenten": regels,
    }


@api_view("GET", "PUT")
@beheerder_vereist
def configuratie(request, slug: str):
    """
    Het instapscherm: welk hoofddomein, en welke componenten gebruikt deze
    organisatie. Het adres per component staat hier; de inloggegevens staan
    onder Verbindingen. Die twee bewust gescheiden: het adres kent iedereen die
    de omgeving inricht, de credentials niet.
    """
    omgeving = eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))

    if request.method == "PUT":
        gegevens = body_van(request)

        domein = _alleen_host(gegevens.get("domein") or "")
        if domein and not HOSTNAAM.match(domein):
            raise Ongeldig(f"'{domein}' is geen geldig domein.")
        omgeving.domein = domein
        omgeving.save(update_fields=["domein"])

        aangezet, uitgezet, verwijderd = [], [], []
        for regel in gegevens.get("componenten") or []:
            sleutel = regel.get("component")
            if sleutel not in registry.PER_SLEUTEL:
                continue
            component = registry.component(sleutel)
            bestaand = Verbinding.objects.filter(
                omgeving=omgeving, component=sleutel
            ).first()

            if regel.get("verwijderen"):
                if bestaand:
                    bestaand.delete()
                    verwijderd.append(sleutel)
                continue

            if not regel.get("gebruikt"):
                # Uitzetten, niet weggooien: de credentials blijven staan zodat
                # opnieuw aanzetten geen nieuw token vereist. Wissen kan apart.
                if bestaand and bestaand.actief:
                    bestaand.actief = False
                    # De vorige uitslag zegt niets meer en zou als rode melding
                    # op het scherm blijven staan bij een component dat uitstaat.
                    bestaand.laatste_test_op = None
                    bestaand.laatste_test_ok = None
                    bestaand.laatste_test_melding = ""
                    bestaand.save(update_fields=[
                        "actief", "laatste_test_op", "laatste_test_ok", "laatste_test_melding",
                    ])
                    uitgezet.append(sleutel)
                continue

            basis = _basis_uit_hostnaam(regel.get("hostnaam") or "")
            if not basis:
                raise Ongeldig(
                    f"Vul een hostnaam in voor {component.label}, of vink het component uit."
                )
            if bestaand is None:
                bestaand = Verbinding(
                    omgeving=omgeving, component=sleutel,
                    auth_type=component.auth, token_prefix=component.token_prefix,
                )
                aangezet.append(sleutel)
            elif not bestaand.actief:
                aangezet.append(sleutel)
            bestaand.basis_url = basis
            bestaand.actief = True
            bestaand.save()

        log(request, "instelling", omgeving=slug, actie="configuratie",
            doel=(f"domein={domein or '-'} aan={','.join(aangezet) or '-'} "
                  f"uit={','.join(uitgezet) or '-'} weg={','.join(verwijderd) or '-'}")[:500])

    return ok(_configuratie_dict(omgeving))


@api_view("POST")
@beheerder_vereist
def dns_check(request):
    """
    Controleert of een hostnaam te herleiden is naar een adres.

    Bewust alleen een naamsopzoeking en géén verbinding: dit beantwoordt de vraag
    "wijst de DNS al goed?" nog voordat er een certificaat of een token is. Of het
    component daadwerkelijk antwoordt, toont de verbindingstest.
    """
    hostnaam = _alleen_host(body_van(request).get("hostnaam") or "")
    if not hostnaam:
        raise Ongeldig("Vul eerst een hostnaam in.")
    if not HOSTNAAM.match(hostnaam):
        raise Ongeldig(f"'{hostnaam}' is geen geldige hostnaam.")

    def opzoeken():
        return socket.getaddrinfo(hostnaam, None, proto=socket.IPPROTO_TCP)

    try:
        # getaddrinfo kent zelf geen time-out; zonder deze grens kan een trage
        # of kapotte resolver het verzoek minutenlang laten hangen.
        #
        # Bewust GEEN `with ThreadPoolExecutor(...)`: het verlaten van dat blok
        # wacht op de draaiende thread, dus dan hangt het verzoek alsnog de volle
        # resolver-time-out. Een gedeelde pool die we niet afsluiten geeft het
        # verzoek meteen vrij; de opzoeking loopt in de achtergrond af.
        resultaten = _DNS_POOL.submit(opzoeken).result(timeout=DNS_TIMEOUT)
    except FuturesTimeout:
        return ok({"hostnaam": hostnaam, "ok": False, "adressen": [],
                   "melding": f"Geen antwoord van de DNS binnen {DNS_TIMEOUT:.0f} seconden."})
    except socket.gaierror as exc:
        return ok({"hostnaam": hostnaam, "ok": False, "adressen": [],
                   "melding": f"Niet gevonden in de DNS ({exc.strerror or exc})."})

    adressen = sorted({item[4][0] for item in resultaten})
    return ok({
        "hostnaam": hostnaam,
        "ok": True,
        "adressen": adressen,
        "melding": "Wijst naar " + ", ".join(adressen[:4])
                   + (" en meer" if len(adressen) > 4 else "") + ".",
    })
