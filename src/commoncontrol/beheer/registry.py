"""
Componentregistry — één bron van waarheid voor CommonControl.

Dezelfde filosofie als `cg-components.js` in KubeManager: elk component en elke
beheerbare resource staat hier één keer beschreven, en zowel de API-laag als de
interface leiden daar alles uit af. Een resource toevoegen is dus één descriptor
erbij, geen nieuwe view en geen nieuw scherm.

Waarom descriptors en niet negen handgeschreven modules: de negen componenten
zijn stuk voor stuk DRF-API's met dezelfde vorm (gepagineerde lijst, detail op
uuid, POST/PUT/PATCH/DELETE). Het verschil zit in paden, velden en
authenticatie — precies wat hier data is.

BRONVERMELDING — de paden en authenticatievormen hieronder zijn geverifieerd
tegen de OpenAPI-specificaties van de upstream-projecten en tegen de
`api_root`-waarden waarmee KubeManager deze componenten in productie aan elkaar
knoopt. Waar iets niet met zekerheid vast te stellen viel staat dat er expliciet
bij; die gevallen zijn zo gebouwd dat de verbindingstest het uitwijst in plaats
van dat de applicatie stilzwijgend het verkeerde doet.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Bouwstenen ───────────────────────────────────────────────────────────────

# Veldtypen die de interface kent. 'json' is de ontsnappingsklep: elk veld dat
# hier niet in past (geneste objecten, lijsten van objecten) wordt als JSON
# bewerkt, zodat geen enkel API-veld onbereikbaar is.
VELDTYPEN = (
    "tekst", "tekstlang", "getal", "bool", "datum", "datumtijd",
    "keuze", "url", "email", "json", "lijst", "duur",
)

VERTROUWELIJKHEID = (
    "openbaar", "beperkt_openbaar", "intern", "zaakvertrouwelijk",
    "vertrouwelijk", "confidentieel", "geheim", "zeer_geheim",
)


@dataclass(frozen=True)
class Veld:
    naam: str
    label: str
    type: str = "tekst"
    verplicht: bool = False
    keuzes: tuple[str, ...] = ()
    hint: str = ""
    alleen_lezen: bool = False
    in_lijst: bool = False
    # Sleutel van een resource BINNEN HETZELFDE COMPONENT waar dit url-veld
    # naar verwijst (bv. "catalogussen" bij Zaaktype.catalogus). De interface
    # haalt dan bij het openen van het formulier de bestaande items van die
    # resource op en biedt ze aan als voorstellen (via een <datalist>), naast
    # de mogelijkheid om zelf een URL te typen/plakken. Leeg = geen
    # voorstellen — geldt voor externe verwijzingen (bv. de Selectielijst-API)
    # en voor cross-component verwijzingen, die de registry niet modelleert.
    verwijst_naar: str = ""

    def als_dict(self) -> dict:
        return {
            "naam": self.naam,
            "label": self.label,
            "type": self.type,
            "verplicht": self.verplicht,
            "keuzes": list(self.keuzes),
            "hint": self.hint,
            "alleenLezen": self.alleen_lezen,
            "inLijst": self.in_lijst,
            "verwijstNaar": self.verwijst_naar,
        }


@dataclass(frozen=True)
class Actie:
    """
    Een POST-actie op een BESTAAND item die geen gewone 'wijzig' is — bv.
    Zaaktype.publish (onomkeerbaar: een concept wordt definitief) of
    Zaak.zaak_verlengen (stuurt een eigen, samengestelde payload in plaats
    van een veldsgewijze PATCH). Verschijnt als knop naast Opslaan/Verwijderen
    in het bewerkscherm van een bestaand item.

    Leeg `velden` = kale POST zonder body (zoals publish). Gevulde `velden`
    opent eerst een klein formulier — voor deze acties zijn dat vrijwel
    altijd samengestelde/geneste objecten, dus de velden zijn doorgaans van
    het type 'json' (dezelfde ontsnappingsklep als elders in de registry).
    """
    sleutel: str
    label: str
    velden: tuple[Veld, ...] = ()
    bevestiging: str = ""         # niet-leeg = vraag dit bevestigend vóór verzenden
    hint: str = ""

    def als_dict(self) -> dict:
        return {
            "sleutel": self.sleutel,
            "label": self.label,
            "velden": [v.als_dict() for v in self.velden],
            "bevestiging": self.bevestiging,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class Resource:
    key: str
    label: str
    label_mv: str
    api: str                      # sleutel van de ApiGroep binnen het component
    pad: str                      # bijv. "/zaaktypen"
    velden: tuple[Veld, ...] = ()
    id_veld: str = "uuid"
    titel_veld: str = ""
    methoden: tuple[str, ...] = ("lijst", "detail", "maak", "wijzig", "verwijder")
    filters: tuple[Veld, ...] = ()
    geo: bool = False             # ZGW: vereist Accept-Crs / Content-Crs
    # Niet elke ZGW-endpoint pagineert. vng-api-common wijst een onbekende
    # queryparameter af met een harde fout, dus een blind meegestuurde ?page=1
    # laat het hele verzoek mislukken. Gemeten bij Open Notificaties.
    gepagineerd: bool = True
    hint: str = ""
    ouder: str = ""               # sleutel van de bovenliggende resource (genest)
    acties: tuple[Actie, ...] = ()  # extra POST-acties op een bestaand item (zie Actie)

    def _titel(self) -> str:
        """Welk veld de rij in de lijst benoemt."""
        if self.titel_veld:
            return self.titel_veld
        return self.velden[0].naam if self.velden else self.id_veld

    def als_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "labelMv": self.label_mv,
            "api": self.api,
            "pad": self.pad,
            "idVeld": self.id_veld,
            "titelVeld": self._titel(),
            "methoden": list(self.methoden),
            "velden": [v.als_dict() for v in self.velden],
            "filters": [v.als_dict() for v in self.filters],
            "geo": self.geo,
            "gepagineerd": self.gepagineerd,
            "hint": self.hint,
            "ouder": self.ouder,
            "acties": [a.als_dict() for a in self.acties],
        }


@dataclass(frozen=True)
class ApiGroep:
    """Eén API binnen een component (OpenZaak levert er vijf)."""

    key: str
    label: str
    pad: str                      # bijv. "/zaken/api/v1"

    def als_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "pad": self.pad}


@dataclass(frozen=True)
class Component:
    key: str
    label: str
    subdomein: str                # voor het automatisch zoeken op één basisdomein
    auth: str                     # standaard authenticatievorm
    apis: tuple[ApiGroep, ...]
    resources: tuple[Resource, ...]
    beschrijving: str = ""
    token_prefix: str = "Token"
    probe: str = ""               # pad dat bewijst dat dit component hier draait
    # Waar je het API-token aanmaakt als KubeManager het niet kan aanleveren.
    token_hint: str = ""
    let_op: str = ""              # bekende beperking, getoond in de interface
    doc_url: str = ""
    volgorde: int = 100

    def api(self, key: str) -> ApiGroep:
        for groep in self.apis:
            if groep.key == key:
                return groep
        raise KeyError(f"Onbekende API-groep '{key}' voor component '{self.key}'")

    def resource(self, key: str) -> Resource:
        for res in self.resources:
            if res.key == key:
                return res
        raise KeyError(f"Onbekende resource '{key}' voor component '{self.key}'")

    def als_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "subdomein": self.subdomein,
            "auth": self.auth,
            "tokenPrefix": self.token_prefix,
            "tokenHint": self.token_hint,
            "beschrijving": self.beschrijving,
            "letOp": self.let_op,
            "docUrl": self.doc_url,
            "apis": [a.als_dict() for a in self.apis],
            "resources": [r.als_dict() for r in self.resources],
        }


# ── Herbruikbare velden ──────────────────────────────────────────────────────

UUID = Veld("uuid", "UUID", "tekst", alleen_lezen=True)
URL = Veld("url", "URL", "url", alleen_lezen=True)

# Gedeeld door zaaktypen/besluittypen/informatieobjecttypen — alle drie kennen
# exact dezelfde /{uuid}/publish-actie (kale POST, geen body, geverifieerd
# tegen de live Catalogi API-spec: requestBody is None). Onomkeerbaar: een
# concept wordt definitief en is daarna niet meer te wijzigen.
PUBLICEER_ACTIE = Actie(
    sleutel="publish", label="📢 Publiceren",
    bevestiging=(
        "Publiceren kan niet ongedaan worden gemaakt. Na publicatie is dit item "
        "niet meer te wijzigen — maak dan een nieuwe versie aan. Doorgaan?"
    ),
)


def _geldigheid() -> tuple[Veld, ...]:
    return (
        Veld("beginGeldigheid", "Begin geldigheid", "datum", verplicht=True),
        Veld("eindeGeldigheid", "Einde geldigheid", "datum"),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  OpenZaak — vijf ZGW-API's in één component
#  api_roots geverifieerd tegen KubeManager's wizard (main.js): /catalogi,
#  /zaken, /documenten, /besluiten en /autorisaties, elk onder /api/v1/.
# ═══════════════════════════════════════════════════════════════════════════

OPENZAAK = Component(
    key="openzaak",
    label="OpenZaak",
    subdomein="openzaak",
    auth="zgw-jwt",
    volgorde=10,
    beschrijving=(
        "Registratiecomponent voor zaakgericht werken: catalogus (zaaktypen), zaken, "
        "documenten, besluiten en de autorisaties van alle aangesloten applicaties."
    ),
    probe="/catalogi/api/v1/catalogussen",
    doc_url="https://vng-realisatie.github.io/gemma-zaken/",
    apis=(
        ApiGroep("catalogi", "Catalogi API", "/catalogi/api/v1"),
        ApiGroep("zaken", "Zaken API", "/zaken/api/v1"),
        ApiGroep("documenten", "Documenten API", "/documenten/api/v1"),
        ApiGroep("besluiten", "Besluiten API", "/besluiten/api/v1"),
        ApiGroep("autorisaties", "Autorisaties API", "/autorisaties/api/v1"),
    ),
    resources=(
        # ── Catalogi ────────────────────────────────────────────────────────
        Resource(
            key="catalogussen", label="Catalogus", label_mv="Catalogussen",
            api="catalogi", pad="/catalogussen", titel_veld="naam",
            # Geverifieerd tegen de officiële Catalogi API-OpenAPI-spec:
            # /catalogussen/{uuid} kent alléén GET. Geen PUT/PATCH/DELETE —
            # een catalogus is dus alleen aan te maken en in te zien, niet
            # te wijzigen of te verwijderen via de API.
            methoden=("lijst", "detail", "maak"),
            hint=(
                "Een catalogus bundelt alle zaaktypen van één organisatie. Eenmaal "
                "aangemaakt is een catalogus niet meer te wijzigen of te verwijderen via "
                "de API — dat kan alleen in OpenZaak zelf."
            ),
            velden=(
                UUID, URL,
                Veld("naam", "Naam", verplicht=False, in_lijst=True),
                Veld("domein", "Domein", verplicht=True, in_lijst=True,
                     hint="Vijf hoofdletters, uniek binnen de organisatie."),
                Veld("rsin", "RSIN", verplicht=True, in_lijst=True),
                Veld("contactpersoonBeheerNaam", "Contactpersoon beheer", verplicht=True),
                Veld("contactpersoonBeheerTelefoonnummer", "Telefoon beheer"),
                Veld("contactpersoonBeheerEmailadres", "E-mail beheer", "email"),
            ),
        ),
        Resource(
            key="zaaktypen", label="Zaaktype", label_mv="Zaaktypen",
            api="catalogi", pad="/zaaktypen", titel_veld="omschrijving",
            acties=(PUBLICEER_ACTIE,),
            hint=(
                "Zaaktypen zijn versiegebonden: een gepubliceerd zaaktype is niet meer te "
                "wijzigen. Maak dan een nieuwe versie aan."
            ),
            filters=(
                Veld("catalogus", "Catalogus", "url"),
                Veld("status", "Status", "keuze", keuzes=("alles", "concept", "definitief")),
                Veld("identificatie", "Identificatie"),
            ),
            velden=(
                UUID, URL,
                Veld("identificatie", "Identificatie", verplicht=True, in_lijst=True),
                Veld("omschrijving", "Omschrijving", verplicht=True, in_lijst=True),
                Veld("omschrijvingGeneriek", "Omschrijving generiek"),
                Veld("vertrouwelijkheidaanduiding", "Vertrouwelijkheid", "keuze",
                     verplicht=True, keuzes=VERTROUWELIJKHEID, in_lijst=True),
                Veld("doel", "Doel", "tekstlang", verplicht=True),
                Veld("aanleiding", "Aanleiding", "tekstlang", verplicht=True),
                Veld("indicatieInternOfExtern", "Intern of extern", "keuze",
                     verplicht=True, keuzes=("intern", "extern")),
                Veld("handelingInitiator", "Handeling initiator", verplicht=True),
                Veld("onderwerp", "Onderwerp", verplicht=True),
                Veld("handelingBehandelaar", "Handeling behandelaar", verplicht=True),
                Veld("doorlooptijd", "Doorlooptijd", "duur", verplicht=True,
                     hint="ISO 8601-duur, bijvoorbeeld P30D voor dertig dagen."),
                Veld("servicenorm", "Servicenorm", "duur"),
                Veld("opschortingEnAanhoudingMogelijk", "Opschorting mogelijk", "bool",
                     verplicht=True),
                Veld("verlengingMogelijk", "Verlenging mogelijk", "bool", verplicht=True),
                Veld("verlengingstermijn", "Verlengingstermijn", "duur"),
                Veld("publicatieIndicatie", "Publicatie-indicatie", "bool", verplicht=True),
                Veld("publicatietekst", "Publicatietekst", "tekstlang"),
                Veld("productenOfDiensten", "Producten of diensten", "lijst", verplicht=True,
                     hint="Lijst met URL's naar producten/diensten. Mag leeg zijn."),
                Veld("referentieproces", "Referentieproces", "json", verplicht=True,
                     hint='Bijvoorbeeld {"naam": "Vergunningaanvraag", "link": ""}'),
                Veld("catalogus", "Catalogus", "url", verplicht=True, verwijst_naar="catalogussen"),
                Veld("besluittypen", "Besluittypen", "lijst", verplicht=True),
                Veld("gerelateerdeZaaktypen", "Gerelateerde zaaktypen", "json", verplicht=True),
                Veld("selectielijstProcestype", "Selectielijst-procestype", "url"),
                Veld("versiedatum", "Versiedatum", "datum", verplicht=True),
                Veld("concept", "Concept", "bool", alleen_lezen=True, in_lijst=True),
                *_geldigheid(),
            ),
        ),
        Resource(
            key="statustypen", label="Statustype", label_mv="Statustypen",
            api="catalogi", pad="/statustypen", titel_veld="omschrijving",
            filters=(Veld("zaaktype", "Zaaktype", "url"),
                     Veld("status", "Status", "keuze", keuzes=("alles", "concept", "definitief"))),
            velden=(
                UUID, URL,
                Veld("omschrijving", "Omschrijving", verplicht=True, in_lijst=True),
                Veld("omschrijvingGeneriek", "Omschrijving generiek"),
                Veld("statustekst", "Statustekst"),
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("volgnummer", "Volgnummer", "getal", verplicht=True, in_lijst=True),
                Veld("isEindstatus", "Is eindstatus", "bool", alleen_lezen=True),
                Veld("informeren", "Informeren", "bool"),
            ),
        ),
        Resource(
            key="resultaattypen", label="Resultaattype", label_mv="Resultaattypen",
            api="catalogi", pad="/resultaattypen", titel_veld="omschrijving",
            filters=(Veld("zaaktype", "Zaaktype", "url"),),
            velden=(
                UUID, URL,
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("omschrijving", "Omschrijving", verplicht=True, in_lijst=True),
                Veld("resultaattypeomschrijving", "Resultaattypeomschrijving", "url",
                     verplicht=True),
                Veld("selectielijstklasse", "Selectielijstklasse", "url", verplicht=True),
                Veld("archiefnominatie", "Archiefnominatie", "keuze",
                     keuzes=("blijvend_bewaren", "vernietigen"), in_lijst=True),
                Veld("archiefactietermijn", "Archiefactietermijn", "duur"),
                Veld("brondatumArchiefprocedure", "Brondatum archiefprocedure", "json"),
                Veld("toelichting", "Toelichting", "tekstlang"),
            ),
        ),
        Resource(
            key="roltypen", label="Roltype", label_mv="Roltypen",
            api="catalogi", pad="/roltypen", titel_veld="omschrijving",
            filters=(Veld("zaaktype", "Zaaktype", "url"),),
            velden=(
                UUID, URL,
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("omschrijving", "Omschrijving", verplicht=True, in_lijst=True),
                Veld("omschrijvingGeneriek", "Omschrijving generiek", "keuze", verplicht=True,
                     in_lijst=True,
                     keuzes=("adviseur", "behandelaar", "belanghebbende", "beslisser",
                             "initiator", "klantcontacter", "zaakcoordinator",
                             "mede_initiator")),
            ),
        ),
        Resource(
            key="eigenschappen", label="Eigenschap", label_mv="Eigenschappen",
            api="catalogi", pad="/eigenschappen", titel_veld="naam",
            filters=(Veld("zaaktype", "Zaaktype", "url"),),
            velden=(
                UUID, URL,
                Veld("naam", "Naam", verplicht=True, in_lijst=True),
                Veld("definitie", "Definitie", verplicht=True),
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("specificatie", "Specificatie", "json", verplicht=True,
                     hint='Bijvoorbeeld {"groep":"","formaat":"tekst","lengte":"20",'
                          '"kardinaliteit":"1","waardenverzameling":[]}'),
                Veld("toelichting", "Toelichting", "tekstlang"),
            ),
        ),
        Resource(
            key="informatieobjecttypen", label="Informatieobjecttype",
            label_mv="Informatieobjecttypen",
            api="catalogi", pad="/informatieobjecttypen", titel_veld="omschrijving",
            acties=(PUBLICEER_ACTIE,),
            filters=(Veld("catalogus", "Catalogus", "url"),
                     Veld("status", "Status", "keuze", keuzes=("alles", "concept", "definitief"))),
            velden=(
                UUID, URL,
                Veld("catalogus", "Catalogus", "url", verplicht=True, verwijst_naar="catalogussen"),
                Veld("omschrijving", "Omschrijving", verplicht=True, in_lijst=True),
                Veld("vertrouwelijkheidaanduiding", "Vertrouwelijkheid", "keuze",
                     verplicht=True, keuzes=VERTROUWELIJKHEID, in_lijst=True),
                Veld("informatieobjectcategorie", "Categorie", verplicht=True),
                Veld("concept", "Concept", "bool", alleen_lezen=True, in_lijst=True),
                *_geldigheid(),
            ),
        ),
        Resource(
            key="besluittypen", label="Besluittype", label_mv="Besluittypen",
            api="catalogi", pad="/besluittypen", titel_veld="omschrijving",
            acties=(PUBLICEER_ACTIE,),
            filters=(Veld("catalogus", "Catalogus", "url"),),
            velden=(
                UUID, URL,
                Veld("catalogus", "Catalogus", "url", verplicht=True, verwijst_naar="catalogussen"),
                Veld("omschrijving", "Omschrijving", in_lijst=True),
                Veld("omschrijvingGeneriek", "Omschrijving generiek"),
                Veld("besluitcategorie", "Besluitcategorie"),
                Veld("reactietermijn", "Reactietermijn", "duur"),
                Veld("publicatieIndicatie", "Publicatie-indicatie", "bool", verplicht=True),
                Veld("zaaktypen", "Zaaktypen", "lijst"),
                Veld("informatieobjecttypen", "Informatieobjecttypen", "lijst"),
                Veld("concept", "Concept", "bool", alleen_lezen=True, in_lijst=True),
                *_geldigheid(),
            ),
        ),
        Resource(
            key="zaaktype-informatieobjecttypen", label="Zaaktype-informatieobjecttype",
            label_mv="Zaaktype ↔ informatieobjecttype",
            api="catalogi", pad="/zaaktype-informatieobjecttypen", titel_veld="volgnummer",
            hint="Koppelt welke documenttypen bij welk zaaktype horen.",
            filters=(Veld("zaaktype", "Zaaktype", "url"),),
            velden=(
                UUID, URL,
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("informatieobjecttype", "Informatieobjecttype", "url", verplicht=True,
                     in_lijst=True, verwijst_naar="informatieobjecttypen"),
                Veld("volgnummer", "Volgnummer", "getal", verplicht=True),
                Veld("richting", "Richting", "keuze", verplicht=True,
                     keuzes=("inkomend", "intern", "uitgaand"), in_lijst=True),
                Veld("statustype", "Statustype", "url", verwijst_naar="statustypen"),
            ),
        ),
        Resource(
            key="zaakobjecttypen", label="Zaakobjecttype", label_mv="Zaakobjecttypen",
            api="catalogi", pad="/zaakobjecttypen", titel_veld="relatieOmschrijving",
            hint="Beschrijft welk soort object (adres, pand, persoon, …) bij een zaaktype hoort.",
            filters=(Veld("zaaktype", "Zaaktype", "url"),),
            velden=(
                UUID, URL,
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("anderObjecttype", "Ander objecttype", "bool", verplicht=True, in_lijst=True,
                     hint="Geeft aan of het objecttype niet in de standaardlijst van de Zaken API voorkomt."),
                Veld("objecttype", "Objecttype (URL)", "url", verplicht=True, in_lijst=True),
                Veld("relatieOmschrijving", "Relatieomschrijving", verplicht=True, in_lijst=True),
                Veld("statustype", "Statustype", "url", verwijst_naar="statustypen"),
                # ⚠ Anders dan bij zaaktypen/informatieobjecttypen/besluittypen is
                # beginGeldigheid hier NIET verplicht (gemeten tegen de live spec) —
                # dus bewust niet de gedeelde _geldigheid()-helper hergebruikt.
                Veld("beginGeldigheid", "Begin geldigheid", "datum"),
                Veld("eindeGeldigheid", "Einde geldigheid", "datum"),
            ),
        ),
        # ── Zaken ───────────────────────────────────────────────────────────
        Resource(
            key="zaken", label="Zaak", label_mv="Zaken",
            api="zaken", pad="/zaken", titel_veld="identificatie", geo=True,
            hint=(
                "Zaken zijn productiegegevens. Verwijderen is onomkeerbaar en verwijdert "
                "ook de gekoppelde statussen, rollen en documentkoppelingen."
            ),
            # ⚠ Deze vier acties zijn OPEN ZAAK-SPECIFIEK (bevestigd: staan niet in
            # de VNG-standaardspec van de Zaken API, alleen in de live installatie).
            # Elk combineert meerdere samenhangende objecten in één verzoek — vandaar
            # 'json'-velden i.p.v. losse formuliervelden, dezelfde ontsnappingsklep
            # als elders in de registry voor samengestelde/geneste payloads.
            acties=(
                Actie(
                    sleutel="zaak_afsluiten", label="🏁 Zaak afsluiten",
                    bevestiging="Een zaak afsluiten zet resultaat + eindstatus in één keer. Doorgaan?",
                    velden=(
                        Veld("zaak", "Zaak (JSON)", "json", verplicht=True,
                             hint='Minimaal {"uuid": "..."} van de zaak zelf.'),
                        Veld("resultaat", "Resultaat (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"resultaattype": "<url>", "toelichting": ""}'),
                        Veld("status", "Status (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"statustype": "<url>", "datumStatusGezet": "..."}'),
                    ),
                ),
                Actie(
                    sleutel="zaak_bijwerken", label="✏️ Zaak bijwerken (workflow)",
                    velden=(
                        Veld("zaak", "Zaak (JSON)", "json",
                             hint="Alleen de velden die moeten wijzigen."),
                        Veld("rollen", "Rollen (JSON-lijst)", "lijst"),
                        Veld("status", "Status (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"statustype": "<url>", "datumStatusGezet": "..."}'),
                    ),
                ),
                Actie(
                    sleutel="zaak_opschorten", label="⏸️ Zaak opschorten",
                    bevestiging="Zaak opschorten zet een nieuwe status. Doorgaan?",
                    velden=(
                        Veld("zaak", "Zaak (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"opschorting": {"indicatie": true, "reden": "..."}}'),
                        Veld("status", "Status (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"statustype": "<url>", "datumStatusGezet": "..."}'),
                    ),
                ),
                Actie(
                    sleutel="zaak_verlengen", label="⏳ Zaak verlengen",
                    velden=(
                        Veld("zaak", "Zaak (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"verlenging": {"reden": "...", "duur": "P30D"}}'),
                        Veld("status", "Status (JSON)", "json", verplicht=True,
                             hint='Bijvoorbeeld {"statustype": "<url>", "datumStatusGezet": "..."}'),
                    ),
                ),
            ),
            filters=(
                Veld("identificatie", "Identificatie"),
                Veld("zaaktype", "Zaaktype", "url"),
                Veld("bronorganisatie", "Bronorganisatie"),
                Veld("startdatum", "Startdatum", "datum"),
                Veld("archiefstatus", "Archiefstatus", "keuze",
                     keuzes=("nog_te_archiveren", "gearchiveerd",
                             "gearchiveerd_procestermijn_onbekend", "overgedragen")),
            ),
            velden=(
                UUID, URL,
                Veld("identificatie", "Identificatie", in_lijst=True,
                     hint="Leeg laten laat OpenZaak zelf een nummer toekennen."),
                Veld("bronorganisatie", "Bronorganisatie (RSIN)", verplicht=True),
                Veld("omschrijving", "Omschrijving", in_lijst=True),
                Veld("toelichting", "Toelichting", "tekstlang"),
                Veld("zaaktype", "Zaaktype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaaktypen"),
                Veld("registratiedatum", "Registratiedatum", "datum"),
                Veld("verantwoordelijkeOrganisatie", "Verantwoordelijke organisatie (RSIN)",
                     verplicht=True),
                Veld("startdatum", "Startdatum", "datum", verplicht=True, in_lijst=True),
                Veld("einddatum", "Einddatum", "datum", alleen_lezen=True),
                Veld("einddatumGepland", "Einddatum gepland", "datum"),
                Veld("uiterlijkeEinddatumAfdoening", "Uiterlijke einddatum", "datum"),
                Veld("vertrouwelijkheidaanduiding", "Vertrouwelijkheid", "keuze",
                     keuzes=VERTROUWELIJKHEID),
                Veld("betalingsindicatie", "Betalingsindicatie", "keuze",
                     keuzes=("nvt", "nog_niet", "gedeeltelijk", "geheel")),
                Veld("archiefnominatie", "Archiefnominatie", "keuze",
                     keuzes=("blijvend_bewaren", "vernietigen")),
                Veld("archiefstatus", "Archiefstatus", "keuze", in_lijst=True,
                     keuzes=("nog_te_archiveren", "gearchiveerd",
                             "gearchiveerd_procestermijn_onbekend", "overgedragen")),
                Veld("archiefactiedatum", "Archiefactiedatum", "datum"),
                Veld("status", "Huidige status", "url", alleen_lezen=True),
                Veld("resultaat", "Resultaat", "url", alleen_lezen=True),
                Veld("zaakgeometrie", "Zaakgeometrie", "json"),
            ),
        ),
        Resource(
            key="statussen", label="Status", label_mv="Statussen",
            api="zaken", pad="/statussen", titel_veld="statustoelichting",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("statustype", "Statustype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="statustypen"),
                Veld("datumStatusGezet", "Datum gezet", "datumtijd", verplicht=True,
                     in_lijst=True),
                Veld("statustoelichting", "Toelichting", "tekstlang"),
            ),
            methoden=("lijst", "detail", "maak"),
        ),
        # ⚠ Open Zaak-specifiek (geen VNG-standaard, bevestigd). Geen PUT/PATCH/
        # DELETE op de live spec, alleen GET+POST.
        Resource(
            key="substatussen", label="Substatus", label_mv="Substatussen",
            api="zaken", pad="/substatussen", titel_veld="omschrijving",
            hint="Open Zaak-specifiek: verfijning van een hoofdstatus, bv. om voortgang binnen een status te tonen.",
            methoden=("lijst", "detail", "maak"),
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("status", "Hoofdstatus", "url", verwijst_naar="statussen"),
                Veld("omschrijving", "Omschrijving", "tekstlang", verplicht=True, in_lijst=True),
                Veld("tijdstip", "Tijdstip", "datumtijd", in_lijst=True),
                Veld("doelgroep", "Doelgroep", "keuze", keuzes=("betrokkenen", "intern"),
                     hint="Leeg = voor iedereen zichtbaar."),
            ),
        ),
        Resource(
            key="rollen", label="Rol", label_mv="Rollen",
            api="zaken", pad="/rollen", titel_veld="roltoelichting",
            filters=(Veld("zaak", "Zaak", "url"),
                     Veld("betrokkeneType", "Betrokkenetype", "keuze",
                          keuzes=("natuurlijk_persoon", "niet_natuurlijk_persoon", "vestiging",
                                  "organisatorische_eenheid", "medewerker"))),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("betrokkene", "Betrokkene", "url"),
                Veld("betrokkeneType", "Betrokkenetype", "keuze", verplicht=True, in_lijst=True,
                     keuzes=("natuurlijk_persoon", "niet_natuurlijk_persoon", "vestiging",
                             "organisatorische_eenheid", "medewerker")),
                Veld("roltype", "Roltype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="roltypen"),
                Veld("roltoelichting", "Toelichting", "tekstlang", verplicht=True),
                Veld("betrokkeneIdentificatie", "Betrokkene-identificatie", "json"),
            ),
            methoden=("lijst", "detail", "maak", "verwijder"),
        ),
        Resource(
            key="resultaten", label="Resultaat", label_mv="Resultaten",
            api="zaken", pad="/resultaten", titel_veld="toelichting",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("resultaattype", "Resultaattype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="resultaattypen"),
                Veld("toelichting", "Toelichting", "tekstlang"),
            ),
        ),
        Resource(
            key="zaakinformatieobjecten", label="Zaakdocument", label_mv="Zaakdocumenten",
            api="zaken", pad="/zaakinformatieobjecten", titel_veld="titel",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("informatieobject", "Informatieobject", "url", verplicht=True,
                     in_lijst=True, verwijst_naar="enkelvoudiginformatieobjecten"),
                Veld("titel", "Titel", in_lijst=True),
                Veld("beschrijving", "Beschrijving", "tekstlang"),
            ),
        ),
        # Geverifieerd tegen de live Zaken API: /klantcontacten/{uuid} kent
        # alléén GET (geen PUT/PATCH/DELETE).
        Resource(
            key="klantcontacten", label="Klantcontact", label_mv="Klantcontacten",
            api="zaken", pad="/klantcontacten", titel_veld="onderwerp",
            methoden=("lijst", "detail", "maak"),
            hint="Legacy-koppeling; nieuwe klantcontacten horen doorgaans in Open Klant thuis.",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("identificatie", "Identificatie", in_lijst=True),
                Veld("datumtijd", "Datum/tijd", "datumtijd", verplicht=True, in_lijst=True),
                Veld("kanaal", "Kanaal"),
                Veld("onderwerp", "Onderwerp", in_lijst=True),
                Veld("toelichting", "Toelichting", "tekstlang"),
            ),
        ),
        # Geverifieerd: /zaakcontactmomenten/{uuid} kent GET+DELETE, geen wijzig.
        Resource(
            key="zaakcontactmomenten", label="Zaakcontactmoment", label_mv="Zaakcontactmomenten",
            api="zaken", pad="/zaakcontactmomenten",
            methoden=("lijst", "detail", "maak", "verwijder"),
            hint="Koppelt een zaak aan een contactmoment uit een externe Klantcontacten-API.",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("contactmoment", "Contactmoment", "url", verplicht=True, in_lijst=True),
            ),
        ),
        Resource(
            key="zaakobjecten", label="Zaakobject", label_mv="Zaakobjecten",
            api="zaken", pad="/zaakobjecten", titel_veld="relatieomschrijving",
            hint=(
                "Koppelt een willekeurig extern object (adres, pand, persoon, …) aan een "
                "zaak. Bij objectType 'overige' met een eigen schemadefinitie "
                "(objectTypeOverigeDefinitie) kan hier alleen via 'Alle velden als JSON' "
                "gewerkt worden — de 29 objectspecifieke schemavarianten zijn niet één "
                "voor één uitgewerkt."
            ),
            filters=(Veld("zaak", "Zaak", "url"), Veld("objectType", "Objecttype")),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("object", "Object (URL)", "url", in_lijst=True,
                     hint="URL naar de externe resource die het object beschrijft."),
                Veld("zaakobjecttype", "Zaakobjecttype", "url", verwijst_naar="zaakobjecttypen"),
                Veld("objectType", "Objecttype", "keuze", verplicht=True, in_lijst=True, keuzes=(
                    "adres", "besluit", "buurt", "enkelvoudig_document", "gemeente",
                    "gemeentelijke_openbare_ruimte", "huishouden", "inrichtingselement",
                    "kadastrale_onroerende_zaak", "kunstwerkdeel", "maatschappelijke_activiteit",
                    "medewerker", "natuurlijk_persoon", "niet_natuurlijk_persoon",
                    "openbare_ruimte", "organisatorische_eenheid", "pand", "spoorbaandeel",
                    "status", "terreindeel", "terrein_gebouwd_object", "vestiging", "waterdeel",
                    "wegdeel", "wijk", "woonplaats", "woz_deelobject", "woz_object",
                    "woz_waarde", "zakelijk_recht", "overige",
                )),
                Veld("objectTypeOverige", "Objecttype (overige)",
                     hint="Alleen bij objectType 'overige'."),
                Veld("relatieomschrijving", "Relatieomschrijving", in_lijst=True),
            ),
        ),
        # Geverifieerd: /zaakverzoeken/{uuid} kent GET+DELETE, geen wijzig.
        Resource(
            key="zaakverzoeken", label="Zaak-verzoek", label_mv="Zaak-verzoeken",
            api="zaken", pad="/zaakverzoeken",
            methoden=("lijst", "detail", "maak", "verwijder"),
            hint="Koppelt een zaak aan een verzoek uit een externe Verzoeken-API.",
            filters=(Veld("zaak", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("zaak", "Zaak", "url", verplicht=True, in_lijst=True, verwijst_naar="zaken"),
                Veld("verzoek", "Verzoek", "url", verplicht=True, in_lijst=True),
            ),
        ),
        # ⚠ Open Zaak-specifiek (geen VNG-standaard, bevestigd: komt niet voor
        # in de referentiespec) — maar wél een gewone CRUD-resource met een
        # eigen lijst/detail, vandaar de standaardmethoden i.p.v. 'maak' alleen.
        Resource(
            key="zaaknotities", label="Zaaknotitie", label_mv="Zaaknotities",
            api="zaken", pad="/zaaknotities", titel_veld="onderwerp",
            hint="Open Zaak-specifiek: interne of externe notitie bij een zaak.",
            filters=(Veld("gerelateerdAan", "Zaak", "url"),),
            velden=(
                UUID, URL,
                Veld("gerelateerdAan", "Zaak", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="zaken"),
                Veld("onderwerp", "Onderwerp", verplicht=True, in_lijst=True),
                Veld("tekst", "Tekst", "tekstlang", verplicht=True),
                Veld("aangemaaktDoor", "Aangemaakt door"),
                Veld("notitieType", "Notitietype", "keuze", keuzes=("intern", "extern"),
                     hint="Intern: alleen zichtbaar voor medewerkers."),
                Veld("status", "Status", "keuze", keuzes=("concept", "definitief"), in_lijst=True),
            ),
        ),
        # ⚠ Open Zaak-specifiek (geen VNG-standaard): eenmalige aanmaak-acties
        # zonder eigen lijst/detail — vandaar methoden=('maak',) alleen.
        Resource(
            key="zaak_registreren", label="Zaak registreren (samengesteld)",
            label_mv="Zaak registreren",
            api="zaken", pad="/zaak_registreren", methoden=("maak",),
            hint=(
                "Open Zaak-specifieke actie: registreert in één verzoek een zaak + rollen "
                "+ status (+ optioneel documenten/objecten) — een alternatief voor los een "
                "Zaak, Rol en Status aanmaken."
            ),
            velden=(
                Veld("zaak", "Zaak (JSON)", "json", verplicht=True),
                Veld("rollen", "Rollen (JSON-lijst)", "lijst", verplicht=True),
                Veld("zaakinformatieobjecten", "Zaakinformatieobjecten (JSON-lijst)", "lijst"),
                Veld("zaakobjecten", "Zaakobjecten (JSON-lijst)", "lijst"),
                Veld("status", "Status (JSON)", "json", verplicht=True),
            ),
        ),
        Resource(
            key="reserveer_zaaknummer", label="Zaaknummer reserveren",
            label_mv="Zaaknummer reserveren",
            api="zaken", pad="/reserveer_zaaknummer", methoden=("maak",),
            hint="Open Zaak-specifieke actie: reserveert alvast een zaaknummer zonder een zaak aan te maken.",
            velden=(
                Veld("bronorganisatie", "Bronorganisatie (RSIN)", verplicht=True),
                Veld("aantal", "Aantal", "getal", hint="Standaard 1 als leeg gelaten."),
            ),
        ),
        # ── Documenten ──────────────────────────────────────────────────────
        Resource(
            key="enkelvoudiginformatieobjecten", label="Document", label_mv="Documenten",
            api="documenten", pad="/enkelvoudiginformatieobjecten", titel_veld="titel",
            hint=(
                "De inhoud van een document wordt base64-gecodeerd verstuurd. Voor grote "
                "bestanden gebruikt de Documenten API een aparte upload in delen; die flow "
                "zit hier bewust niet in."
            ),
            filters=(Veld("identificatie", "Identificatie"),
                     Veld("bronorganisatie", "Bronorganisatie")),
            velden=(
                UUID, URL,
                Veld("identificatie", "Identificatie", in_lijst=True),
                Veld("bronorganisatie", "Bronorganisatie (RSIN)", verplicht=True),
                Veld("creatiedatum", "Creatiedatum", "datum", verplicht=True, in_lijst=True),
                Veld("titel", "Titel", verplicht=True, in_lijst=True),
                Veld("auteur", "Auteur", verplicht=True),
                Veld("status", "Status", "keuze",
                     keuzes=("in_bewerking", "ter_vaststelling", "definitief", "gearchiveerd"),
                     in_lijst=True),
                Veld("formaat", "Formaat (mimetype)"),
                Veld("taal", "Taal", verplicht=True, hint="ISO 639-2/B, bijvoorbeeld 'nld'."),
                Veld("bestandsnaam", "Bestandsnaam"),
                Veld("inhoud", "Inhoud (base64)", "tekstlang"),
                Veld("bestandsomvang", "Bestandsomvang", "getal"),
                Veld("beschrijving", "Beschrijving", "tekstlang"),
                Veld("informatieobjecttype", "Informatieobjecttype", "url", verplicht=True,
                     verwijst_naar="informatieobjecttypen"),
                Veld("vertrouwelijkheidaanduiding", "Vertrouwelijkheid", "keuze",
                     keuzes=VERTROUWELIJKHEID),
                Veld("indicatieGebruiksrecht", "Indicatie gebruiksrecht", "bool"),
            ),
        ),
        Resource(
            key="gebruiksrechten", label="Gebruiksrecht", label_mv="Gebruiksrechten",
            api="documenten", pad="/gebruiksrechten", titel_veld="omschrijvingVoorwaarden",
            filters=(Veld("informatieobject", "Informatieobject", "url"),),
            velden=(
                UUID, URL,
                Veld("informatieobject", "Informatieobject", "url", verplicht=True,
                     in_lijst=True, verwijst_naar="enkelvoudiginformatieobjecten"),
                Veld("startdatum", "Startdatum", "datumtijd", verplicht=True, in_lijst=True),
                Veld("einddatum", "Einddatum", "datumtijd"),
                Veld("omschrijvingVoorwaarden", "Omschrijving voorwaarden", "tekstlang",
                     verplicht=True),
            ),
        ),
        # Geverifieerd: /objectinformatieobjecten/{uuid} kent GET+DELETE, geen wijzig.
        Resource(
            key="objectinformatieobjecten", label="Object-informatieobject relatie",
            label_mv="Object-informatieobject relaties",
            api="documenten", pad="/objectinformatieobjecten",
            methoden=("lijst", "detail", "maak", "verwijder"),
            hint="Koppelt een document aan een besluit, zaak of verzoek (buiten de Zaken-koppeling om).",
            filters=(Veld("informatieobject", "Informatieobject", "url"),
                     Veld("object", "Object", "url")),
            velden=(
                UUID, URL,
                Veld("informatieobject", "Informatieobject", "url", verplicht=True,
                     in_lijst=True, verwijst_naar="enkelvoudiginformatieobjecten"),
                Veld("object", "Object (URL)", "url", verplicht=True, in_lijst=True),
                Veld("objectType", "Objecttype", "keuze", verplicht=True, in_lijst=True,
                     keuzes=("besluit", "zaak", "verzoek")),
            ),
        ),
        Resource(
            key="verzendingen", label="Verzending", label_mv="Verzendingen",
            api="documenten", pad="/verzendingen", titel_veld="informatieobject",
            hint="Registreert de verzending van een document naar een betrokkene (bv. per post of e-mail).",
            filters=(Veld("informatieobject", "Informatieobject", "url"),
                     Veld("betrokkene", "Betrokkene", "url")),
            velden=(
                UUID, URL,
                Veld("betrokkene", "Betrokkene", "url", verplicht=True, in_lijst=True),
                Veld("informatieobject", "Informatieobject", "url", verplicht=True,
                     in_lijst=True, verwijst_naar="enkelvoudiginformatieobjecten"),
                Veld("aardRelatie", "Aard relatie", "keuze", verplicht=True, in_lijst=True,
                     keuzes=("afzender", "geadresseerde")),
                Veld("toelichting", "Toelichting", "tekstlang"),
                Veld("ontvangstdatum", "Ontvangstdatum", "datum"),
                Veld("verzenddatum", "Verzenddatum", "datum", in_lijst=True),
                Veld("contactPersoon", "Contactpersoon", "url", verplicht=True),
                Veld("contactpersoonnaam", "Contactpersoonnaam"),
                Veld("faxnummer", "Faxnummer"),
                Veld("emailadres", "E-mailadres", "email"),
                Veld("mijnOverheid", "MijnOverheid", "bool"),
                Veld("telefoonnummer", "Telefoonnummer"),
                Veld("binnenlandsCorrespondentieadres", "Binnenlands correspondentieadres (JSON)", "json"),
                Veld("buitenlandsCorrespondentieadres", "Buitenlands correspondentieadres (JSON)", "json"),
                Veld("correspondentiePostadres", "Correspondentiepostadres (JSON)", "json"),
            ),
        ),
        # ⚠ Open Zaak-specifiek (geen VNG-standaard): eenmalige aanmaak-acties
        # zonder eigen lijst/detail.
        Resource(
            key="document_registreren", label="Document registreren (samengesteld)",
            label_mv="Document registreren",
            api="documenten", pad="/document_registreren", methoden=("maak",),
            hint=(
                "Open Zaak-specifieke actie: registreert in één verzoek een document én de "
                "koppeling naar een zaak — een alternatief voor los een Document aanmaken "
                "en dan een Zaakdocument-koppeling."
            ),
            velden=(
                Veld("enkelvoudiginformatieobject", "Document (JSON)", "json", verplicht=True),
                Veld("zaakinformatieobject", "Zaakkoppeling (JSON)", "json", verplicht=True),
            ),
        ),
        Resource(
            key="documentnummer_reserveren", label="Documentnummer reserveren",
            label_mv="Documentnummer reserveren",
            api="documenten", pad="/documentnummer_reserveren", methoden=("maak",),
            hint="Open Zaak-specifieke actie: reserveert alvast een documentnummer zonder een document aan te maken.",
            velden=(
                Veld("bronorganisatie", "Bronorganisatie (RSIN)", verplicht=True),
                Veld("aantal", "Aantal", "getal", hint="Standaard 1 als leeg gelaten."),
            ),
        ),
        # ── Besluiten ───────────────────────────────────────────────────────
        Resource(
            key="besluiten", label="Besluit", label_mv="Besluiten",
            api="besluiten", pad="/besluiten", titel_veld="identificatie",
            filters=(Veld("identificatie", "Identificatie"), Veld("zaak", "Zaak", "url")),
            velden=(
                UUID, URL,
                Veld("identificatie", "Identificatie", in_lijst=True),
                Veld("verantwoordelijkeOrganisatie", "Verantwoordelijke organisatie (RSIN)",
                     verplicht=True),
                Veld("besluittype", "Besluittype", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="besluittypen"),
                Veld("zaak", "Zaak", "url", in_lijst=True, verwijst_naar="zaken"),
                Veld("datum", "Datum", "datum", verplicht=True, in_lijst=True),
                Veld("toelichting", "Toelichting", "tekstlang"),
                Veld("ingangsdatum", "Ingangsdatum", "datum", verplicht=True),
                Veld("vervaldatum", "Vervaldatum", "datum"),
                Veld("vervalreden", "Vervalreden", "keuze",
                     keuzes=("tijdelijk", "ingetrokken_overheid", "ingetrokken_belanghebbende")),
                Veld("publicatiedatum", "Publicatiedatum", "datum"),
                Veld("verzenddatum", "Verzenddatum", "datum"),
                Veld("uiterlijkeReactiedatum", "Uiterlijke reactiedatum", "datum"),
            ),
        ),
        # Geverifieerd: /besluitinformatieobjecten/{uuid} kent GET+DELETE, geen wijzig.
        Resource(
            key="besluitinformatieobjecten", label="Besluit-informatieobject relatie",
            label_mv="Besluit-informatieobject relaties",
            api="besluiten", pad="/besluitinformatieobjecten",
            methoden=("lijst", "detail", "maak", "verwijder"),
            hint="Koppelt een document aan een besluit.",
            filters=(Veld("besluit", "Besluit", "url"),
                     Veld("informatieobject", "Informatieobject", "url")),
            velden=(
                UUID, URL,
                Veld("besluit", "Besluit", "url", verplicht=True, in_lijst=True,
                     verwijst_naar="besluiten"),
                Veld("informatieobject", "Informatieobject", "url", verplicht=True, in_lijst=True),
            ),
        ),
        # ⚠ Open Zaak-specifiek (geen VNG-standaard): eenmalige aanmaak-actie
        # zonder eigen lijst/detail.
        Resource(
            key="besluit_verwerken", label="Besluit verwerken (samengesteld)",
            label_mv="Besluit verwerken",
            api="besluiten", pad="/besluit_verwerken", methoden=("maak",),
            hint=(
                "Open Zaak-specifieke actie: registreert in één verzoek een besluit + de "
                "gekoppelde documenten — een alternatief voor los een Besluit aanmaken en "
                "dan Besluit-informatieobject-koppelingen."
            ),
            velden=(
                Veld("besluit", "Besluit (JSON)", "json", verplicht=True),
                Veld("besluitinformatieobjecten", "Documentkoppelingen (JSON-lijst)", "lijst",
                     verplicht=True),
            ),
        ),
        # ── Autorisaties ────────────────────────────────────────────────────
        Resource(
            key="applicaties", label="Applicatie", label_mv="Applicaties",
            api="autorisaties", pad="/applicaties", titel_veld="label",
            hint=(
                "Elke applicatie die OpenZaak aanroept heeft hier een rij met client-id's en "
                "autorisaties. Let op: 'heeft alle autorisaties' geeft volledige toegang tot "
                "alle zaakgegevens."
            ),
            velden=(
                UUID, URL,
                Veld("label", "Label", verplicht=True, in_lijst=True),
                Veld("clientIds", "Client-id's", "lijst", verplicht=True, in_lijst=True),
                Veld("heeftAlleAutorisaties", "Heeft alle autorisaties", "bool", in_lijst=True),
                Veld("autorisaties", "Autorisaties", "json",
                     hint="Lijst met {component, scopes, zaaktype, maxVertrouwelijkheidaanduiding}."),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Notificaties
#  api_root /api/v1 geverifieerd tegen KubeManager (_notifApiRequest).
# ═══════════════════════════════════════════════════════════════════════════

NOTIFICATIES = Component(
    key="notificaties",
    label="Open Notificaties",
    subdomein="notificaties",
    auth="zgw-jwt",
    volgorde=20,
    beschrijving="Publiceert gebeurtenissen op kanalen en levert ze af bij abonnees.",
    probe="/api/v1/kanaal",
    apis=(ApiGroep("nrc", "Notificaties API", "/api/v1"),),
    resources=(
        Resource(
            key="kanaal", label="Kanaal", label_mv="Kanalen",
            api="nrc", pad="/kanaal", titel_veld="naam", gepagineerd=False,
            # Geverifieerd tegen de officiële Open Notificaties-OpenAPI-spec:
            # /kanaal/{uuid} kent GET en PUT, maar geen DELETE.
            methoden=("lijst", "detail", "maak", "wijzig"),
            hint=(
                "Kanalen worden normaal door de bronapplicatie zelf geregistreerd. Eenmaal "
                "aangemaakt is een kanaal niet meer te verwijderen via de API."
            ),
            velden=(
                UUID, URL,
                Veld("naam", "Naam", verplicht=True, in_lijst=True),
                Veld("documentatieLink", "Documentatielink", "url", in_lijst=True),
                Veld("filters", "Filters", "lijst",
                     hint="Namen van de kenmerken waarop abonnees mogen filteren."),
            ),
        ),
        Resource(
            key="abonnement", label="Abonnement", label_mv="Abonnementen",
            api="nrc", pad="/abonnement", titel_veld="callbackUrl", gepagineerd=False,
            hint=(
                "Een abonnement is een webhook: bij elke gebeurtenis op het gekozen kanaal "
                "doet Open Notificaties een POST naar de callback-URL."
            ),
            velden=(
                UUID, URL,
                Veld("callbackUrl", "Callback-URL", "url", verplicht=True, in_lijst=True),
                Veld("auth", "Autorisatieheader", verplicht=True,
                     hint="Wordt letterlijk als Authorization-header meegestuurd."),
                Veld("kanalen", "Kanalen", "json", verplicht=True,
                     hint='[{"naam": "zaken", "filters": {}}]'),
            ),
        ),
        # ⚠ Geen VNG-standaard-uitbreiding maar de kernactie zelf: dit IS wat
        # de Notificaties API doet. Geen eigen lijst/detail — publiceren is
        # eenmalig, er is niets om terug op te vragen. Bewust zonder
        # verwijst_naar op 'kanaal': dat veld verwacht de NAAM van het kanaal
        # (KANAAL.naam), geen URL — kijk in de Kanalen-tab voor de juiste naam.
        Resource(
            key="notificaties", label="Notificatie publiceren", label_mv="Notificatie publiceren",
            api="nrc", pad="/notificaties", methoden=("maak",),
            hint=(
                "Publiceert direct een notificatie op een kanaal — hetzelfde als wat een "
                "aangesloten component doet bij een wijziging. Vooral nuttig om een "
                "abonnee-koppeling te testen."
            ),
            velden=(
                Veld("kanaal", "Kanaal (naam)", verplicht=True,
                     hint="De NAAM van het kanaal (KANAAL.naam), geen URL — zie de Kanalen-tab."),
                Veld("hoofdObject", "Hoofdobject (URL)", "url", verplicht=True),
                Veld("resource", "Resourcenaam", verplicht=True,
                     hint="Bijvoorbeeld 'zaak' — de publicerende API bepaalt de toegestane waarden."),
                Veld("resourceUrl", "Resource-URL", "url", verplicht=True),
                Veld("actie", "Actie", verplicht=True,
                     hint="Bijvoorbeeld 'create'/'update'/'destroy' — de publicerende API bepaalt dit."),
                Veld("aanmaakdatum", "Aanmaakdatum", "datumtijd", verplicht=True),
                Veld("source", "Bron (systeem/organisatie)"),
                Veld("kenmerken", "Kenmerken (JSON)", "json",
                     hint='Sleutel/waarde, bijvoorbeeld {"bron": "openzaak"}.'),
            ),
        ),
        # ⚠ Bewust NIET gebouwd: /cloudevents is door Open Notificaties zelf
        # als EXPERIMENTEEL gemarkeerd én gebruikt een ander content-type
        # (application/cloudevents+json i.p.v. application/json). CommonControl's
        # HTTP-client stuurt altijd JSON; dit zou een eigen contenttype-pad in
        # de client vereisen voor één experimentele endpoint. Zie
        # OpenZaak-API-Overzicht.md voor vergelijkbare bewuste keuzes.
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Objecttypen API — token-auth, /api/v2 (geverifieerd in de OpenAPI-spec)
# ═══════════════════════════════════════════════════════════════════════════

OBJECTTYPEN = Component(
    key="objecttypen",
    label="Objecttypen API",
    subdomein="objecttypen",
    auth="token",
    volgorde=30,
    beschrijving="Beheert de definities (JSON-schema's) van objecttypen.",
    probe="/api/v2/objecttypes",
    apis=(ApiGroep("v2", "Objecttypen API", "/api/v2"),),
    resources=(
        Resource(
            key="objecttypes", label="Objecttype", label_mv="Objecttypen",
            api="v2", pad="/objecttypes", titel_veld="name",
            velden=(
                UUID, URL,
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("namePlural", "Naam meervoud", verplicht=True, in_lijst=True),
                Veld("description", "Omschrijving", "tekstlang"),
                Veld("dataClassification", "Dataclassificatie", "keuze",
                     keuzes=("open", "intern", "gesloten"), in_lijst=True),
                Veld("maintainerOrganization", "Beherende organisatie"),
                Veld("maintainerDepartment", "Beherende afdeling"),
                Veld("contactPerson", "Contactpersoon"),
                Veld("contactEmail", "Contact-e-mail", "email"),
                Veld("providerOrganization", "Leverende organisatie"),
                Veld("documentationUrl", "Documentatie-URL", "url"),
                Veld("labels", "Labels", "json"),
                Veld("allowGeometry", "Geometrie toegestaan", "bool"),
                Veld("versions", "Versies", "lijst", alleen_lezen=True),
            ),
        ),
        Resource(
            key="versions", label="Objecttypeversie", label_mv="Versies",
            api="v2", pad="/objecttypes/{ouder}/versions", ouder="objecttypes",
            id_veld="version", titel_veld="version",
            hint=(
                "Alleen een versie met status 'draft' is nog te wijzigen. Publiceren is "
                "onomkeerbaar: gepubliceerde schema's worden door Objecten gebruikt om "
                "bestaande records te valideren."
            ),
            velden=(
                Veld("version", "Versie", "getal", alleen_lezen=True, in_lijst=True),
                Veld("status", "Status", "keuze", keuzes=("draft", "published", "deprecated"),
                     in_lijst=True),
                Veld("jsonSchema", "JSON-schema", "json", verplicht=True),
                Veld("publishedAt", "Gepubliceerd op", "datum", alleen_lezen=True, in_lijst=True),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Objecten API (Open Object) — token-auth, /api/v2
# ═══════════════════════════════════════════════════════════════════════════

OBJECTEN = Component(
    key="objecten",
    label="Objecten API",
    subdomein="objecten",
    auth="token",
    volgorde=40,
    beschrijving="Bewaart de objecten zelf, gevalideerd tegen een objecttype-versie.",
    probe="/api/v2/objects",
    let_op=(
        "Een token in de Objecten API heeft per objecttype een expliciete permissie. "
        "Zie je een leeg overzicht terwijl er wél objecten zijn, controleer dan de "
        "permissies van dit token onder 'Permissies'."
    ),
    apis=(ApiGroep("v2", "Objecten API", "/api/v2"),),
    resources=(
        Resource(
            key="objects", label="Object", label_mv="Objecten",
            api="v2", pad="/objects", titel_veld="uuid",
            filters=(Veld("type", "Objecttype", "url"),
                     Veld("data_attrs", "Data-filter",
                          hint="Bijvoorbeeld: naam__exact__Jan")),
            velden=(
                UUID, URL,
                Veld("type", "Objecttype", "url", verplicht=True, in_lijst=True),
                Veld("record", "Record", "json", verplicht=True,
                     hint='{"typeVersion": 1, "data": {...}, "startAt": "2026-01-01"}'),
            ),
        ),
        Resource(
            key="permissions", label="Permissie", label_mv="Permissies",
            api="v2", pad="/permissions", titel_veld="objectType",
            methoden=("lijst",),
            hint="Alleen-lezen: laat zien op welke objecttypen dit token rechten heeft.",
            velden=(
                Veld("objectType", "Objecttype", "url", alleen_lezen=True, in_lijst=True),
                Veld("mode", "Modus", alleen_lezen=True, in_lijst=True),
                Veld("useFields", "Veldbeperking", "bool", alleen_lezen=True),
                Veld("fields", "Velden", "json", alleen_lezen=True),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Klant — /klantinteracties/api/v1 (geverifieerd in KubeManager) en
#  /contactgegevens/api/v1 (geverifieerd in de OpenAPI-spec).
# ═══════════════════════════════════════════════════════════════════════════

def _ok_resource(key, label, label_mv, pad, titel="uuid", velden=()):
    return Resource(
        key=key, label=label, label_mv=label_mv, api="klantinteracties", pad=pad,
        titel_veld=titel,
        velden=(UUID, URL, *velden),
    )


OPENKLANT = Component(
    key="openklant",
    label="Open Klant",
    subdomein="klant",
    auth="token",
    volgorde=50,
    beschrijving="Klantinteracties en contactgegevens: partijen, adressen en klantcontacten.",
    probe="/klantinteracties/api/v1/partijen",
    apis=(
        ApiGroep("klantinteracties", "Klantinteracties API", "/klantinteracties/api/v1"),
        ApiGroep("contactgegevens", "Contactgegevens API", "/contactgegevens/api/v1"),
    ),
    resources=(
        _ok_resource(
            "partijen", "Partij", "Partijen", "/partijen", "nummer",
            velden=(
                Veld("nummer", "Nummer", in_lijst=True),
                Veld("soortPartij", "Soort partij", "keuze", verplicht=True, in_lijst=True,
                     keuzes=("persoon", "organisatie", "contactpersoon")),
                Veld("indicatieActief", "Actief", "bool", in_lijst=True),
                Veld("indicatieGeheimhouding", "Geheimhouding", "bool"),
                Veld("interneNotitie", "Interne notitie", "tekstlang"),
                Veld("partijIdentificatie", "Partij-identificatie", "json",
                     hint="Vorm hangt af van soortPartij (persoon/organisatie/contactpersoon)."),
                Veld("digitaleAdressen", "Digitale adressen", "json"),
                Veld("voorkeursDigitaalAdres", "Voorkeursadres", "json"),
                Veld("rekeningnummers", "Rekeningnummers", "json"),
                Veld("voorkeurstaal", "Voorkeurstaal"),
                Veld("bezoekadres", "Bezoekadres", "json"),
                Veld("correspondentieadres", "Correspondentieadres", "json"),
            ),
        ),
        _ok_resource(
            "digitaleadressen", "Digitaal adres", "Digitale adressen", "/digitaleadressen",
            "adres",
            velden=(
                Veld("adres", "Adres", verplicht=True, in_lijst=True),
                Veld("soortDigitaalAdres", "Soort", verplicht=True, in_lijst=True,
                     hint="Bijvoorbeeld 'email' of 'telefoonnummer'."),
                Veld("omschrijving", "Omschrijving", in_lijst=True),
                Veld("isStandaardAdres", "Standaardadres", "bool"),
                Veld("verstrektDoorPartij", "Verstrekt door partij", "json"),
                Veld("verstrektDoorBetrokkene", "Verstrekt door betrokkene", "json"),
            ),
        ),
        _ok_resource(
            "klantcontacten", "Klantcontact", "Klantcontacten", "/klantcontacten", "nummer",
            velden=(
                Veld("nummer", "Nummer", in_lijst=True),
                Veld("kanaal", "Kanaal", verplicht=True, in_lijst=True),
                Veld("onderwerp", "Onderwerp", verplicht=True, in_lijst=True),
                Veld("inhoud", "Inhoud", "tekstlang"),
                Veld("indicatieContactGelukt", "Contact gelukt", "bool"),
                Veld("taal", "Taal"),
                Veld("vertrouwelijk", "Vertrouwelijk", "bool", verplicht=True),
                Veld("plaatsgevondenOp", "Plaatsgevonden op", "datumtijd", in_lijst=True),
            ),
        ),
        _ok_resource(
            "betrokkenen", "Betrokkene", "Betrokkenen", "/betrokkenen", "uuid",
            velden=(
                Veld("hadKlantcontact", "Klantcontact", "json", verplicht=True),
                Veld("wasPartij", "Partij", "json"),
                Veld("rol", "Rol", "keuze", keuzes=("klant", "vertegenwoordiger"),
                     verplicht=True, in_lijst=True),
                Veld("organisatienaam", "Organisatienaam", in_lijst=True),
                Veld("initiator", "Initiator", "bool", verplicht=True),
                Veld("contactnaam", "Contactnaam", "json"),
            ),
        ),
        _ok_resource(
            "actoren", "Actor", "Actoren", "/actoren", "naam",
            velden=(
                Veld("naam", "Naam", verplicht=True, in_lijst=True),
                Veld("soortActor", "Soort actor", "keuze", verplicht=True, in_lijst=True,
                     keuzes=("medewerker", "geautomatiseerde_actor", "organisatorische_eeenheid")),
                Veld("indicatieActief", "Actief", "bool", in_lijst=True),
                Veld("actoridentificator", "Identificator", "json"),
            ),
        ),
        _ok_resource(
            "internetaken", "Interne taak", "Interne taken", "/internetaken", "nummer",
            velden=(
                Veld("nummer", "Nummer", in_lijst=True),
                Veld("gevraagdeHandeling", "Gevraagde handeling", verplicht=True, in_lijst=True),
                Veld("toegewezenAanActor", "Toegewezen aan actor", "json"),
                Veld("aanleidinggevendKlantcontact", "Aanleiding (klantcontact)", "json"),
                Veld("toelichting", "Toelichting", "tekstlang"),
                Veld("status", "Status", "keuze", keuzes=("te_verwerken", "verwerkt"),
                     verplicht=True, in_lijst=True),
            ),
        ),
        _ok_resource(
            "categorieen", "Categorie", "Categorieën", "/categorieen", "naam",
            velden=(Veld("naam", "Naam", verplicht=True, in_lijst=True),),
        ),
        Resource(
            key="personen", label="Persoon", label_mv="Personen",
            api="contactgegevens", pad="/persoon", titel_veld="uuid",
            velden=(
                UUID, URL,
                Veld("geboortedatum", "Geboortedatum", "datum", in_lijst=True),
                Veld("overlijdensdatum", "Overlijdensdatum", "datum"),
                Veld("geslachtsnaam", "Geslachtsnaam", in_lijst=True),
                Veld("voorvoegsel", "Voorvoegsel"),
                Veld("voornamen", "Voornamen", in_lijst=True),
                Veld("geslacht", "Geslacht", "keuze", keuzes=("m", "v", "o")),
                Veld("land", "Land"),
            ),
        ),
        Resource(
            key="organisaties", label="Organisatie", label_mv="Organisaties",
            api="contactgegevens", pad="/organisatie", titel_veld="handelsnaam",
            velden=(
                UUID, URL,
                Veld("handelsnaam", "Handelsnaam", in_lijst=True),
                Veld("oprichtingsdatum", "Oprichtingsdatum", "datum"),
                Veld("opheffingsdatum", "Opheffingsdatum", "datum"),
                Veld("land", "Land"),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Product — /producttypen/api/v1 en /producten/api/v1
#  (paden en Token-prefix geverifieerd in de OpenAPI-specs en settings)
# ═══════════════════════════════════════════════════════════════════════════

def _op_resource(key, label, label_mv, pad, titel, velden=(), api="producttypen"):
    return Resource(
        key=key, label=label, label_mv=label_mv, api=api, pad=pad, titel_veld=titel,
        velden=(UUID, *velden),
    )


OPENPRODUCT = Component(
    key="openproduct",
    label="Open Product",
    subdomein="product",
    auth="token",
    volgorde=60,
    beschrijving="Producttypen (het aanbod) en producten (de afgenomen exemplaren).",
    probe="/producttypen/api/v1/producttypen",
    token_hint=(
        "KubeManager legt voor dit component geen token vast. Maak er een aan in de eigen beheeromgeving onder Auth Token → Tokens (/admin/authtoken/), gekoppeld aan een eigen serviceaccount — een token erft de rechten van die gebruiker."
    ),
    apis=(
        ApiGroep("producttypen", "Producttypen API", "/producttypen/api/v1"),
        ApiGroep("producten", "Producten API", "/producten/api/v1"),
    ),
    resources=(
        _op_resource(
            "producttypen", "Producttype", "Producttypen", "/producttypen", "naam",
            velden=(
                Veld("code", "Code", verplicht=True, in_lijst=True),
                Veld("naam", "Naam", in_lijst=True),
                Veld("samenvatting", "Samenvatting", "tekstlang"),
                Veld("uniformeProductnaam", "Uniforme productnaam", "url", verplicht=True,
                     in_lijst=True,
                     hint="URI uit de landelijke UPL-lijst; die wordt bij het opstarten geladen."),
                Veld("toegestaneStatussen", "Toegestane statussen", "lijst"),
                Veld("gepubliceerd", "Gepubliceerd", "bool", in_lijst=True),
                Veld("themaIds", "Thema's", "lijst"),
                Veld("organisatieIds", "Organisaties", "lijst"),
                Veld("keywords", "Trefwoorden", "lijst"),
                Veld("interneOpmerkingen", "Interne opmerkingen", "tekstlang"),
                Veld("verbruiksobject", "Verbruiksobject-schema", "json"),
                Veld("dataObject", "Dataobject-schema", "json"),
            ),
        ),
        _op_resource("themas", "Thema", "Thema's", "/themas", "naam",
                     velden=(Veld("naam", "Naam", verplicht=True, in_lijst=True),
                             Veld("beschrijving", "Beschrijving", "tekstlang"),
                             Veld("gepubliceerd", "Gepubliceerd", "bool", in_lijst=True),
                             Veld("hoofdThemaId", "Hoofdthema", "getal"))),
        _op_resource("organisaties", "Organisatie", "Organisaties", "/organisaties", "naam",
                     velden=(Veld("naam", "Naam", verplicht=True, in_lijst=True),
                             Veld("code", "Code", in_lijst=True),
                             Veld("email", "E-mail", "email"),
                             Veld("telefoonnummer", "Telefoon"))),
        _op_resource("prijzen", "Prijs", "Prijzen", "/prijzen", "actiefVanaf",
                     velden=(Veld("productTypeId", "Producttype", "tekst", verplicht=True,
                                  in_lijst=True),
                             Veld("actiefVanaf", "Actief vanaf", "datum", verplicht=True,
                                  in_lijst=True),
                             Veld("prijsopties", "Prijsopties", "json"),
                             Veld("prijsregels", "Prijsregels", "json"))),
        _op_resource("links", "Link", "Links", "/links", "naam",
                     velden=(Veld("productTypeId", "Producttype", "tekst", verplicht=True),
                             Veld("naam", "Naam", verplicht=True, in_lijst=True),
                             Veld("url", "URL", "url", verplicht=True, in_lijst=True))),
        _op_resource("contacten", "Contact", "Contacten", "/contacten", "achternaam",
                     velden=(Veld("organisatieId", "Organisatie", "tekst"),
                             Veld("voornaam", "Voornaam", in_lijst=True),
                             Veld("achternaam", "Achternaam", verplicht=True, in_lijst=True),
                             Veld("email", "E-mail", "email", in_lijst=True),
                             Veld("telefoonnummer", "Telefoon"),
                             Veld("rol", "Rol"))),
        _op_resource("content", "Contentblok", "Content", "/content", "labels",
                     velden=(Veld("productTypeId", "Producttype", "tekst", verplicht=True),
                             Veld("labels", "Labels", "lijst", in_lijst=True),
                             Veld("tekst", "Tekst", "tekstlang", verplicht=True))),
        _op_resource("acties", "Actie", "Acties", "/acties", "naam",
                     velden=(Veld("naam", "Naam", verplicht=True, in_lijst=True),
                             Veld("productTypeId", "Producttype", "tekst"),
                             Veld("dmnConfigId", "DMN-configuratie", "tekst"),
                             Veld("dmnTabelId", "DMN-tabel", "tekst"))),
        _op_resource(
            "producten", "Product", "Producten", "/producten", "uuid", api="producten",
            velden=(
                Veld("productTypeId", "Producttype", "tekst", verplicht=True, in_lijst=True),
                Veld("status", "Status", "keuze", in_lijst=True,
                     keuzes=("initieel", "gereed", "actief", "ingetrokken", "geweigerd",
                             "verlopen")),
                Veld("start_datum", "Startdatum", "datum", in_lijst=True),
                Veld("eind_datum", "Einddatum", "datum"),
                Veld("prijs", "Prijs", "tekst"),
                Veld("frequentie", "Frequentie", "keuze",
                     keuzes=("eenmalig", "maandelijks", "jaarlijks")),
                Veld("verbruiksobject", "Verbruiksobject", "json"),
                Veld("dataObject", "Dataobject", "json"),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Formulieren — /api/v2 (router-prefixen geverifieerd in v2_urls.py)
# ═══════════════════════════════════════════════════════════════════════════

OPENFORMS = Component(
    key="openforms",
    label="Open Formulieren",
    subdomein="forms",
    auth="token",
    volgorde=70,
    beschrijving="Formulierdefinities, hergebruikbare stappen en de ingezonden formulieren.",
    probe="/api/v2/forms",
    token_hint=(
        "KubeManager legt voor dit component geen token vast. Maak er een aan in de eigen beheeromgeving onder Auth Token → Tokens (/admin/authtoken/), gekoppeld aan een eigen serviceaccount — een token erft de rechten van die gebruiker."
    ),
    # ⚠ Voor wie deze lijst uitbreidt: /api/v2/services en /api/v2/submissions
    # bestaan wel, maar zijn met een API-token principieel onbereikbaar. Beide
    # viewsets overschrijven de projectstandaard TokenAuthentication:
    #   ServiceViewSet     -> (SessionAuthentication,) + IsAdminUser
    #   SubmissionViewSet  -> (AnonCSRFSessionAuthentication,) + ActiveSubmissionPermission
    # Die laatste geeft bovendien alleen de inzendingen uit de eigen browsersessie
    # van de invuller terug — het is de endpoint van het invulformulier, geen
    # beheeroverzicht. Geen enkel token of rechtenniveau helpt daar.
    apis=(ApiGroep("v2", "Open Formulieren API", "/api/v2"),),
    resources=(
        Resource(
            key="forms", label="Formulier", label_mv="Formulieren",
            api="v2", pad="/forms", id_veld="uuid", titel_veld="name",
            velden=(
                UUID, URL,
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("slug", "Slug", in_lijst=True),
                Veld("internalName", "Interne naam"),
                Veld("active", "Actief", "bool", in_lijst=True),
                Veld("maintenanceMode", "Onderhoudsmodus", "bool", in_lijst=True),
                Veld("category", "Categorie", "url", verwijst_naar="categories"),
                Veld("theme", "Thema", "url", verwijst_naar="themes"),
                Veld("authenticationBackends", "Authenticatie", "lijst"),
                Veld("paymentRequired", "Betaling vereist", "bool", alleen_lezen=True),
                Veld("submissionAllowed", "Inzenden toegestaan", "keuze",
                     keuzes=("yes", "no_with_overview", "no_without_overview")),
                Veld("explanationTemplate", "Toelichting", "tekstlang"),
                Veld("submissionConfirmationTemplate", "Bevestigingstekst", "tekstlang"),
                Veld("steps", "Stappen", "json", alleen_lezen=True),
            ),
        ),
        Resource(
            key="form-definitions", label="Formulierdefinitie", label_mv="Formulierdefinities",
            api="v2", pad="/form-definitions", titel_veld="name",
            hint="Hergebruikbare formulierstappen.",
            velden=(
                UUID, URL,
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("internalName", "Interne naam"),
                Veld("slug", "Slug", in_lijst=True),
                Veld("isReusable", "Herbruikbaar", "bool", in_lijst=True),
                Veld("configuration", "Formio-configuratie", "json"),
            ),
        ),
        Resource(
            key="categories", label="Categorie", label_mv="Categorieën",
            api="v2", pad="/categories", titel_veld="name",
            velden=(UUID, URL, Veld("name", "Naam", verplicht=True, in_lijst=True)),
        ),
        Resource(
            key="themes", label="Thema", label_mv="Thema's",
            api="v2", pad="/themes", titel_veld="name",
            velden=(UUID, URL, Veld("name", "Naam", verplicht=True, in_lijst=True)),
        ),
        Resource(
            key="products", label="Product", label_mv="Producten",
            api="v2", pad="/products", titel_veld="name",
            velden=(
                UUID, URL,
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("price", "Prijs", in_lijst=True),
                Veld("informationUrl", "Informatie-URL", "url"),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Inwoner — /api (categories + products, geverifieerd in api/urls.py)
# ═══════════════════════════════════════════════════════════════════════════

OPENINWONER = Component(
    key="openinwoner",
    label="Open Inwoner",
    subdomein="mijn",
    auth="token",
    volgorde=80,
    beschrijving="Inwonersportaal: de producten- en dienstencatalogus (PDC).",
    probe="/api/products",
    token_hint=(
        "KubeManager legt voor dit component geen token vast. Maak er een aan in de eigen beheeromgeving onder Auth Token → Tokens (/admin/authtoken/), gekoppeld aan een eigen serviceaccount — een token erft de rechten van die gebruiker."
    ),
    let_op=(
        "Open Inwoner biedt bewust maar een klein deel van zijn beheer via een API aan: "
        "de PDC (categorieën en producten). Gebruikersbeheer, thema's en de inhoud van het "
        "portaal blijven in de eigen beheeromgeving van Open Inwoner."
    ),
    apis=(ApiGroep("api", "Open Inwoner API", "/api"),),
    resources=(
        Resource(
            key="categories", label="Categorie", label_mv="Categorieën",
            api="api", pad="/categories", id_veld="slug", titel_veld="name",
            velden=(
                Veld("slug", "Slug", alleen_lezen=True, in_lijst=True),
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("description", "Omschrijving", "tekstlang"),
            ),
        ),
        Resource(
            key="products", label="Product", label_mv="Producten",
            api="api", pad="/products", id_veld="slug", titel_veld="name",
            velden=(
                Veld("slug", "Slug", alleen_lezen=True, in_lijst=True),
                Veld("name", "Naam", verplicht=True, in_lijst=True),
                Veld("summary", "Samenvatting", "tekstlang"),
                Veld("content", "Inhoud", "tekstlang"),
                Veld("categories", "Categorieën", "lijst"),
            ),
        ),
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
#  Open Archiefbeheer — /api/v1 (routes geverifieerd in api/urls.py)
# ═══════════════════════════════════════════════════════════════════════════

OPENARCHIEFBEHEER = Component(
    key="openarchiefbeheer",
    label="Open Archiefbeheer",
    subdomein="archiefbeheer",
    auth="sessie",
    volgorde=90,
    beschrijving="Vernietigingslijsten: selecteren, beoordelen en vernietigen van zaken.",
    probe="/api/v1/health-check",
    let_op=(
        "Open Archiefbeheer kent geen machine-credentials: zijn API is bedoeld voor de eigen "
        "webinterface en werkt met een sessie-login. CommonControl logt daarom in met een "
        "gebruikersnaam en wachtwoord van een Open Archiefbeheer-account. Maak daarvoor een "
        "apart serviceaccount aan, zodat de handelingen in hun eigen logboek herleidbaar "
        "blijven. Vernietigen zelf gebeurt bewust in Open Archiefbeheer, met het "
        "vier-ogenprincipe dat daar is ingebouwd."
    ),
    apis=(ApiGroep("v1", "Open Archiefbeheer API", "/api/v1"),),
    resources=(
        Resource(
            key="destruction-lists", label="Vernietigingslijst", label_mv="Vernietigingslijsten",
            api="v1", pad="/destruction-lists", titel_veld="name",
            methoden=("lijst", "detail"),
            hint="Alleen-lezen in CommonControl; beoordelen en vernietigen gebeurt in de app zelf.",
            velden=(
                UUID, URL,
                Veld("name", "Naam", alleen_lezen=True, in_lijst=True),
                Veld("status", "Status", alleen_lezen=True, in_lijst=True),
                Veld("author", "Auteur", "json", alleen_lezen=True),
                Veld("created", "Aangemaakt", "datumtijd", alleen_lezen=True, in_lijst=True),
                Veld("plannedDestructionDate", "Geplande vernietiging", "datum",
                     alleen_lezen=True, in_lijst=True),
            ),
        ),
        Resource(
            key="destruction-list-items", label="Lijstregel", label_mv="Lijstregels",
            api="v1", pad="/destruction-list-items", titel_veld="pk", id_veld="pk",
            methoden=("lijst", "detail"),
            filters=(Veld("destruction_list", "Vernietigingslijst"),),
            velden=(
                Veld("pk", "Nummer", "getal", alleen_lezen=True, in_lijst=True),
                Veld("status", "Status", alleen_lezen=True, in_lijst=True),
                Veld("zaak", "Zaak", "json", alleen_lezen=True),
                Veld("extraZaakData", "Extra zaakgegevens", "json", alleen_lezen=True),
            ),
        ),
        Resource(
            key="reviews", label="Beoordeling", label_mv="Beoordelingen",
            api="v1", pad="/destruction-list-reviews", titel_veld="pk", id_veld="pk",
            methoden=("lijst", "detail"),
            velden=(
                Veld("pk", "Nummer", "getal", alleen_lezen=True, in_lijst=True),
                Veld("destructionList", "Vernietigingslijst", alleen_lezen=True, in_lijst=True),
                Veld("author", "Beoordelaar", "json", alleen_lezen=True),
                Veld("decision", "Besluit", alleen_lezen=True, in_lijst=True),
                Veld("listFeedback", "Toelichting", "tekstlang", alleen_lezen=True),
                Veld("created", "Aangemaakt", "datumtijd", alleen_lezen=True, in_lijst=True),
            ),
        ),
        Resource(
            key="users", label="Gebruiker", label_mv="Gebruikers",
            api="v1", pad="/users", titel_veld="username", id_veld="pk",
            methoden=("lijst",),
            velden=(
                Veld("pk", "Nummer", "getal", alleen_lezen=True),
                Veld("username", "Gebruikersnaam", alleen_lezen=True, in_lijst=True),
                Veld("email", "E-mail", "email", alleen_lezen=True, in_lijst=True),
                Veld("role", "Rol", "json", alleen_lezen=True),
            ),
        ),
        Resource(
            key="archive-config", label="Archiefconfiguratie", label_mv="Archiefconfiguratie",
            api="v1", pad="/archive-config", id_veld="", titel_veld="bronorganisatie",
            methoden=("detail", "wijzig"),
            hint=(
                "De zaaktypen hieronder moeten al in de catalogus van OpenZaak bestaan — "
                "Open Archiefbeheer maakt bij een vernietiging zelf een rapportagezaak aan."
            ),
            velden=(
                Veld("bronorganisatie", "Bronorganisatie (RSIN)"),
                Veld("zaaktype", "Zaaktype vernietigingsrapport", "url"),
                Veld("statustype", "Statustype", "url"),
                Veld("resultaattype", "Resultaattype", "url"),
                Veld("informatieobjecttype", "Informatieobjecttype", "url"),
                Veld("selectielijstklasseProcestermijnNul", "Selectielijstklasse", "url"),
            ),
        ),
    ),
)


# ── Alles bij elkaar ─────────────────────────────────────────────────────────

COMPONENTEN: tuple[Component, ...] = tuple(
    sorted(
        (
            OPENZAAK, NOTIFICATIES, OBJECTTYPEN, OBJECTEN, OPENKLANT,
            OPENPRODUCT, OPENFORMS, OPENINWONER, OPENARCHIEFBEHEER,
        ),
        key=lambda c: c.volgorde,
    )
)

PER_SLEUTEL: dict[str, Component] = {c.key: c for c in COMPONENTEN}
SLEUTELS: list[str] = [c.key for c in COMPONENTEN]


def component(sleutel: str) -> Component:
    try:
        return PER_SLEUTEL[sleutel]
    except KeyError:
        raise KeyError(f"Onbekend component: {sleutel}") from None


def als_dict(sleutels: list[str] | None = None) -> list[dict]:
    """De registry als JSON voor de interface, eventueel gefilterd op rechten."""
    return [
        c.als_dict() for c in COMPONENTEN if sleutels is None or c.key in sleutels
    ]
