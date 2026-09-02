"""
Generieke beheerlaag: één set views die elke resource uit de registry bedient.

Waarom generiek: de negen componenten hebben 56 beheerbare resources. Voor elke
resource een eigen view schrijven zou dezelfde vijf regels 56 keer herhalen — en
bij de volgende component opnieuw. Hier is de resource een parameter.

Beveiliging zit op twee plekken en niet op één:
  * de component- en resourcesleutel worden opgezocht in de registry, dus een
    onbekende waarde bestaat simpelweg niet en er kan nooit een willekeurig pad
    worden samengesteld;
  * per verzoek wordt het recht van de gebruiker op dát component gecontroleerd,
    lezen en schrijven apart.
"""

from __future__ import annotations

from urllib.parse import quote

from commoncontrol.api import Ongeldig, api_view, body_van, eerste_of_fout, fout, ok
from commoncontrol.auditlog.models import log
from commoncontrol.toegang import rechten
from commoncontrol.verbindingen.client import ApiFout, client_voor
from commoncontrol.verbindingen.models import Omgeving, Verbinding

from . import registry

# Querystring-parameters die van ons zijn en dus niet doorgegeven worden aan het
# achterliggende component.
EIGEN_PARAMETERS = {"ouder", "_"}


# ── hulpjes ─────────────────────────────────────────────────────────────────


def _omgeving(slug: str) -> Omgeving:
    return eerste_of_fout(Omgeving.objects.filter(slug=slug), _geen_omgeving(slug))


def _geen_omgeving(slug: str) -> str:
    """
    De interface zet de gekozen omgeving in de URL. Is er nog geen gekozen, dan
    staat daar letterlijk 'null' of 'undefined' — dan is 'omgeving bestaat niet'
    een verwarrend antwoord op een heel ander probleem.
    """
    if not slug or slug in ("null", "undefined"):
        return ("Er is nog geen omgeving gekozen. Maak er een aan onder Verbindingen "
                "en kies hem daarna bovenin.")
    return (f"De omgeving '{slug}' bestaat niet (meer). Kies bovenin een andere "
            "omgeving of maak er een aan.")


def _verbinding(omgeving: Omgeving, component_sleutel: str) -> Verbinding:
    verbinding = Verbinding.objects.filter(
        omgeving=omgeving, component=component_sleutel
    ).first()
    if verbinding is None:
        raise Ongeldig(
            f"Er is voor '{omgeving.naam}' nog geen verbinding met dit component ingesteld. "
            "Stel die eerst in onder Verbindingen.",
            409,
        )
    if not verbinding.actief:
        raise Ongeldig(
            "Dit component staat niet als 'in gebruik' aangevinkt. Zet het aan onder "
            "Instellingen -> Configuratie.",
            409,
        )
    return verbinding


def _component_en_resource(component_sleutel: str, resource_sleutel: str):
    try:
        component = registry.component(component_sleutel)
    except KeyError:
        raise Ongeldig(f"Onbekend component: {component_sleutel}", 404) from None
    try:
        resource = component.resource(resource_sleutel)
    except KeyError:
        raise Ongeldig(f"Onbekende resource: {resource_sleutel}", 404) from None
    return component, resource


def bouw_pad(component, resource, *, ouder_id: str = "", object_id: str = "") -> str:
    """
    Stelt het API-pad samen.

    Alle door de gebruiker aangeleverde delen worden URL-gecodeerd; de vaste
    delen komen uit de registry. Zo kan een identificatie met een schuine streep
    of een spatie het pad nooit veranderen.
    """
    api = component.api(resource.api)
    pad = resource.pad

    if "{ouder}" in pad:
        if not ouder_id:
            raise Ongeldig(
                f"Voor {resource.label_mv} is eerst een {resource.ouder or 'bovenliggend item'} nodig."
            )
        pad = pad.replace("{ouder}", quote(str(ouder_id), safe=""))

    volledig = f"{api.pad}{pad}"
    if object_id:
        volledig = f"{volledig}/{quote(str(object_id), safe='')}"
    return volledig


def _filters(request, resource) -> dict:
    """
    Alleen parameters doorgeven die deze resource daadwerkelijk kent.

    Paginatieparameters gaan alleen mee als de resource pagineert: de
    ZGW-componenten wijzen een onbekende queryparameter af met een harde fout,
    dus een overbodige ?page=1 breekt het hele verzoek.
    """
    toegestaan = {veld.naam for veld in resource.filters} | {"ordering", "search"}
    if resource.gepagineerd:
        toegestaan |= {"page", "pageSize", "page_size"}
    return {
        sleutel: waarde
        for sleutel, waarde in request.GET.items()
        if sleutel in toegestaan and sleutel not in EIGEN_PARAMETERS and waarde != ""
    }


def _controleer_recht(request, component_sleutel: str, schrijven: bool) -> None:
    if schrijven:
        if not rechten.mag_schrijven(request.user, component_sleutel):
            raise Ongeldig("Je hebt geen schrijfrechten op dit component.", 403)
    elif not rechten.mag_lezen(request.user, component_sleutel):
        raise Ongeldig("Je hebt geen toegang tot dit component.", 403)


def _controleer_methode(resource, methode: str) -> None:
    if methode not in resource.methoden:
        raise Ongeldig(
            f"{resource.label_mv} ondersteunt '{methode}' niet in CommonControl.", 405
        )


# ── registry + omgevingen ───────────────────────────────────────────────────


@api_view("GET")
def registry_view(request):
    """
    De registry zoals déze gebruiker hem mag zien, inclusief de status van de
    verbindingen in de gekozen omgeving.
    """
    toegestaan = rechten.zichtbare_componenten(request.user, registry.SLEUTELS)
    componenten = registry.als_dict(toegestaan)

    omgeving_slug = request.GET.get("omgeving") or ""
    verbindingen = {}
    if omgeving_slug:
        omgeving = Omgeving.objects.filter(slug=omgeving_slug).first()
        if omgeving:
            verbindingen = {
                v.component: v.als_dict() for v in omgeving.verbindingen.all()
            }

    for component in componenten:
        component["niveau"] = rechten.niveau_voor(request.user, component["key"])
        component["verbinding"] = verbindingen.get(component["key"])

    return ok(
        {
            "componenten": componenten,
            "omgevingen": [
                {
                    "slug": o.slug,
                    "naam": o.naam,
                    "domein": o.domein,
                    "standaard": o.is_standaard,
                }
                for o in Omgeving.objects.all()
            ],
            "gebruiker": {
                "naam": request.user.get_full_name() or request.user.get_username(),
                "gebruikersnaam": request.user.get_username(),
                "beheerder": request.user.is_superuser,
                "demo": bool(getattr(getattr(request.user, "profiel", None), "demo", False)),
            },
        }
    )


# ── resources ───────────────────────────────────────────────────────────────


@api_view("GET", "POST")
def collectie(request, omgeving_slug: str, component_sleutel: str, resource_sleutel: str):
    component, resource = _component_en_resource(component_sleutel, resource_sleutel)
    schrijven = request.method == "POST"
    _controleer_recht(request, component.key, schrijven)
    _controleer_methode(resource, "maak" if schrijven else "lijst")

    omgeving = _omgeving(omgeving_slug)
    verbinding = _verbinding(omgeving, component.key)
    client = client_voor(verbinding, request.user)
    pad = bouw_pad(component, resource, ouder_id=request.GET.get("ouder", ""))

    try:
        if schrijven:
            gegevens = body_van(request)
            status, resultaat = client.verzoek(
                "POST", pad, body=gegevens, geo=resource.geo
            )
            log(
                request,
                "wijziging",
                omgeving=omgeving.slug,
                component=component.key,
                resource=resource.key,
                actie="aanmaken",
                doel=str(resultaat.get(resource.id_veld) if isinstance(resultaat, dict) else "")[:500],
            )
            return ok(resultaat, status=status)

        status, resultaat = client.verzoek(
            "GET", pad, params=_filters(request, resource), geo=resource.geo
        )
        return ok(resultaat)
    except ApiFout as exc:
        if schrijven:
            log(
                request,
                "wijziging",
                gelukt=False,
                omgeving=omgeving.slug,
                component=component.key,
                resource=resource.key,
                actie="aanmaken",
                detail=exc.melding[:2000],
            )
        return fout(exc.melding, 502, **exc.details())


@api_view("GET", "PUT", "PATCH", "DELETE")
def item(request, omgeving_slug: str, component_sleutel: str, resource_sleutel: str,
         object_id: str):
    component, resource = _component_en_resource(component_sleutel, resource_sleutel)
    schrijven = request.method in ("PUT", "PATCH", "DELETE")
    _controleer_recht(request, component.key, schrijven)

    methode_naam = {
        "GET": "detail", "PUT": "wijzig", "PATCH": "wijzig", "DELETE": "verwijder"
    }[request.method]
    _controleer_methode(resource, methode_naam)

    omgeving = _omgeving(omgeving_slug)
    verbinding = _verbinding(omgeving, component.key)
    client = client_voor(verbinding, request.user)

    # Sommige resources zijn een singleton (bijvoorbeeld de archiefconfiguratie):
    # die hebben geen identificatie in het pad.
    echt_id = "" if not resource.id_veld else object_id
    pad = bouw_pad(
        component, resource, ouder_id=request.GET.get("ouder", ""), object_id=echt_id
    )

    actie = {"GET": "lezen", "PUT": "wijzigen", "PATCH": "wijzigen",
             "DELETE": "verwijderen"}[request.method]
    try:
        if request.method == "DELETE":
            status, resultaat = client.verzoek("DELETE", pad, geo=resource.geo)
        elif request.method in ("PUT", "PATCH"):
            status, resultaat = client.verzoek(
                request.method, pad, body=body_van(request), geo=resource.geo
            )
        else:
            status, resultaat = client.verzoek("GET", pad, geo=resource.geo)

        if schrijven:
            log(
                request,
                "wijziging",
                omgeving=omgeving.slug,
                component=component.key,
                resource=resource.key,
                actie=actie,
                doel=str(object_id)[:500],
            )
        return ok(resultaat, status=status)
    except ApiFout as exc:
        if schrijven:
            log(
                request,
                "wijziging",
                gelukt=False,
                omgeving=omgeving.slug,
                component=component.key,
                resource=resource.key,
                actie=actie,
                doel=str(object_id)[:500],
                detail=exc.melding[:2000],
            )
        return fout(exc.melding, 502, **exc.details())


@api_view("GET")
def rauw(request, omgeving_slug: str, component_sleutel: str):
    """
    Een willekeurig GET-pad binnen één component ophalen.

    Nodig omdat ZGW-resources naar elkaar verwijzen met volledige URL's: om bij
    een zaak de omschrijving van het zaaktype te tonen moet de interface die URL
    kunnen volgen. Alleen lezen, alleen binnen de basis-URL van deze verbinding —
    de gebruiker kan er dus geen andere host mee benaderen.
    """
    _controleer_recht(request, component_sleutel, schrijven=False)
    component = registry.component(component_sleutel) if component_sleutel in registry.PER_SLEUTEL else None
    if component is None:
        raise Ongeldig(f"Onbekend component: {component_sleutel}", 404)

    doel = request.GET.get("url") or ""
    if not doel:
        raise Ongeldig("Geen url meegegeven.")

    omgeving = _omgeving(omgeving_slug)
    verbinding = _verbinding(omgeving, component.key)

    if not doel.startswith(verbinding.basis + "/"):
        raise Ongeldig(
            "Deze URL hoort niet bij dit component. Alleen verwijzingen binnen "
            f"{verbinding.basis} kunnen worden opgehaald.",
            403,
        )

    pad = doel[len(verbinding.basis):]
    try:
        _, resultaat = client_voor(verbinding, request.user).verzoek("GET", pad)
        return ok(resultaat)
    except ApiFout as exc:
        return fout(exc.melding, 502, **exc.details())
