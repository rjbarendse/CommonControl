"""
Tests voor de kern van CommonControl: versleuteling, ZGW-JWT, rechten, padopbouw,
foutvertaling en het inlezen van een KubeManager-configuratie.

Dit zijn precies de plekken waar een stille fout duur is: een verkeerd JWT geeft
een onbegrijpelijke 403, een verkeerd pad raakt de verkeerde resource, en een
rechtenfout geeft iemand toegang die hij niet hoort te hebben.
"""

from __future__ import annotations

import base64
import json
import pathlib

import jwt as pyjwt
from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings

from commoncontrol import crypto
from commoncontrol.beheer import registry
from commoncontrol.beheer.views import _filters, bouw_pad
from commoncontrol.toegang import rechten
from commoncontrol.toegang.models import ComponentToegang
from commoncontrol.verbindingen.client import zgw_jwt


class VersleutelingTest(TestCase):
    def test_heen_en_weer(self):
        geheim = "een-secret-met-'quotes\"-en-üñïcode"
        versleuteld = crypto.versleutel(geheim)
        self.assertTrue(versleuteld.startswith("enc:v1:"))
        self.assertNotIn(geheim, versleuteld)
        self.assertEqual(crypto.ontsleutel(versleuteld), geheim)

    def test_leeg_blijft_leeg(self):
        self.assertEqual(crypto.versleutel(""), "")
        self.assertEqual(crypto.ontsleutel(""), "")

    def test_klare_tekst_blijft_leesbaar(self):
        """Een bestaande onversleutelde waarde moet gewoon werken (migratiepad)."""
        self.assertEqual(crypto.ontsleutel("nog-niet-versleuteld"), "nog-niet-versleuteld")

    def test_andere_sleutel_geeft_leeg_in_plaats_van_crash(self):
        versleuteld = crypto.versleutel("geheim")
        with override_settings(SECRET_KEY="een-heel-andere-sleutel", COMMONCONTROL_ENCRYPTIE_SLEUTEL=""):
            self.assertEqual(crypto.ontsleutel(versleuteld), "")

    def test_twee_keer_versleutelen_geeft_verschillende_uitkomst(self):
        """Fernet gebruikt een willekeurige IV; identieke ciphertext zou lekken."""
        self.assertNotEqual(crypto.versleutel("zelfde"), crypto.versleutel("zelfde"))


class ZgwJwtTest(TestCase):
    def test_vorm_en_handtekening(self):
        token = zgw_jwt("commoncontrol", "supergeheim", "rob", "Rob")

        kop = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
        # vng-api-common leest de client uit de HEADER; staat die er niet in,
        # dan weigert OpenZaak het token met een nietszeggende 403.
        self.assertEqual(kop["client_identifier"], "commoncontrol")
        self.assertEqual(kop["alg"], "HS256")

        payload = pyjwt.decode(token, "supergeheim", algorithms=["HS256"])
        self.assertEqual(payload["client_id"], "commoncontrol")
        self.assertEqual(payload["iss"], "commoncontrol")
        self.assertEqual(payload["user_id"], "rob")
        self.assertEqual(payload["user_representation"], "Rob")
        self.assertIn("iat", payload)

    def test_verkeerd_secret_valideert_niet(self):
        token = zgw_jwt("commoncontrol", "geheim-a")
        with self.assertRaises(pyjwt.InvalidSignatureError):
            pyjwt.decode(token, "geheim-b", algorithms=["HS256"])


class RechtenTest(TestCase):
    def setUp(self):
        self.gebruiker = User.objects.create_user("teun", password="x")
        self.groep = Group.objects.create(name="Zaakbeheer")

    def test_superuser_mag_alles(self):
        baas = User.objects.create_superuser("baas", password="x")
        self.assertTrue(rechten.mag_schrijven(baas, "openzaak"))
        self.assertEqual(
            rechten.zichtbare_componenten(baas, registry.SLEUTELS), registry.SLEUTELS
        )

    def test_zonder_rechten_geen_toegang(self):
        self.assertFalse(rechten.mag_lezen(self.gebruiker, "openzaak"))
        self.assertEqual(rechten.zichtbare_componenten(self.gebruiker, registry.SLEUTELS), [])

    def test_persoonlijk_recht(self):
        ComponentToegang.objects.create(
            gebruiker=self.gebruiker, component="openzaak", niveau="lezen"
        )
        self.assertTrue(rechten.mag_lezen(self.gebruiker, "openzaak"))
        self.assertFalse(rechten.mag_schrijven(self.gebruiker, "openzaak"))

    def test_sterkste_recht_wint_over_gebruiker_en_groep(self):
        """Persoonlijk schrijfrecht mag niet worden teruggedrukt door groepsleesrecht."""
        ComponentToegang.objects.create(
            gebruiker=self.gebruiker, component="openzaak", niveau="schrijven"
        )
        ComponentToegang.objects.create(groep=self.groep, component="openzaak", niveau="lezen")
        self.gebruiker.groups.add(self.groep)
        self.assertTrue(rechten.mag_schrijven(self.gebruiker, "openzaak"))

    def test_groepsrecht_alleen_geldt_ook_los(self):
        ComponentToegang.objects.create(groep=self.groep, component="objecten", niveau="schrijven")
        self.gebruiker.groups.add(self.groep)
        self.assertTrue(rechten.mag_schrijven(self.gebruiker, "objecten"))
        self.assertFalse(rechten.mag_lezen(self.gebruiker, "openzaak"))


class PadOpbouwTest(TestCase):
    def test_gewoon_pad(self):
        comp = registry.component("openzaak")
        res = comp.resource("zaaktypen")
        self.assertEqual(bouw_pad(comp, res), "/catalogi/api/v1/zaaktypen")
        self.assertEqual(
            bouw_pad(comp, res, object_id="abc-123"), "/catalogi/api/v1/zaaktypen/abc-123"
        )

    def test_identificatie_wordt_gecodeerd(self):
        """Een identificatie met een schuine streep mag het pad nooit veranderen."""
        comp = registry.component("openzaak")
        res = comp.resource("zaken")
        pad = bouw_pad(comp, res, object_id="../../autorisaties/api/v1/applicaties")
        self.assertNotIn("../", pad)
        self.assertTrue(pad.startswith("/zaken/api/v1/zaken/"))

    def test_geneste_resource(self):
        comp = registry.component("objecttypen")
        res = comp.resource("versions")
        pad = bouw_pad(comp, res, ouder_id="ot-1", object_id="2")
        self.assertEqual(pad, "/api/v2/objecttypes/ot-1/versions/2")

    def test_geneste_resource_zonder_ouder_faalt_netjes(self):
        from commoncontrol.api import Ongeldig

        comp = registry.component("objecttypen")
        res = comp.resource("versions")
        with self.assertRaises(Ongeldig):
            bouw_pad(comp, res)

    def test_singleton_zonder_identificatie(self):
        comp = registry.component("openarchiefbeheer")
        res = comp.resource("archive-config")
        self.assertEqual(bouw_pad(comp, res), "/api/v1/archive-config")


class FilterTest(TestCase):
    """Alleen bekende filters worden doorgegeven aan het component."""

    def test_onbekende_parameters_worden_geweerd(self):
        from django.test import RequestFactory

        comp = registry.component("openzaak")
        res = comp.resource("zaken")
        verzoek = RequestFactory().get(
            "/", {"identificatie": "ZAAK-1", "page": "3", "iets_geks": "x", "zaaktype": ""}
        )
        resultaat = _filters(verzoek, res)
        self.assertEqual(resultaat, {"identificatie": "ZAAK-1", "page": "3"})


class FoutVertalingTest(TestCase):
    def test_invalid_params_worden_per_veld_uitgelezen(self):
        import httpx

        from commoncontrol.verbindingen.client import _fout_uit_antwoord

        antwoord = httpx.Response(
            400,
            json={
                "type": "http://x/fout",
                "title": "Ongeldige invoer",
                "status": 400,
                "invalidParams": [
                    {"name": "identificatie", "code": "unique", "reason": "Bestaat al."},
                    {"name": "startdatum", "code": "invalid", "reason": "Geen geldige datum."},
                ],
            },
            request=httpx.Request("POST", "https://voorbeeld.nl/zaken/api/v1/zaken"),
        )
        fout = _fout_uit_antwoord(antwoord)
        self.assertEqual(fout.status, 400)
        self.assertEqual(fout.velden["identificatie"], "Bestaat al.")
        self.assertEqual(fout.velden["startdatum"], "Geen geldige datum.")
        self.assertIn("Bestaat al.", fout.melding)

    def test_drf_stijl_fouten(self):
        import httpx

        from commoncontrol.verbindingen.client import _fout_uit_antwoord

        antwoord = httpx.Response(
            400,
            json={"name": ["Dit veld is vereist."]},
            request=httpx.Request("POST", "https://voorbeeld.nl/api/v2/objecttypes"),
        )
        fout = _fout_uit_antwoord(antwoord)
        self.assertEqual(fout.velden["name"], "Dit veld is vereist.")

    def test_401_krijgt_bruikbare_uitleg(self):
        import httpx

        from commoncontrol.verbindingen.client import _fout_uit_antwoord

        antwoord = httpx.Response(
            401, text="", request=httpx.Request("GET", "https://voorbeeld.nl/api/v2/objects")
        )
        self.assertIn("credentials", _fout_uit_antwoord(antwoord).melding)


class RegistryIntegriteitTest(TestCase):
    """
    De registry is de bron van waarheid voor de hele applicatie; een verwijzing
    die nergens heen wijst zou pas bij gebruik opvallen.
    """

    def test_alle_resources_verwijzen_naar_een_bestaande_api(self):
        for comp in registry.COMPONENTEN:
            for res in comp.resources:
                comp.api(res.api)  # gooit KeyError als de groep niet bestaat

    def test_ouderverwijzingen_bestaan(self):
        for comp in registry.COMPONENTEN:
            sleutels = {r.key for r in comp.resources}
            for res in comp.resources:
                if res.ouder:
                    self.assertIn(res.ouder, sleutels, f"{comp.key}/{res.key}")

    def test_geneste_resources_hebben_een_ouderplaatshouder(self):
        for comp in registry.COMPONENTEN:
            for res in comp.resources:
                if res.ouder:
                    self.assertIn("{ouder}", res.pad, f"{comp.key}/{res.key}")
                else:
                    self.assertNotIn("{ouder}", res.pad, f"{comp.key}/{res.key}")

    def test_sleutels_zijn_uniek(self):
        self.assertEqual(len(registry.SLEUTELS), len(set(registry.SLEUTELS)))
        for comp in registry.COMPONENTEN:
            sleutels = [r.key for r in comp.resources]
            self.assertEqual(len(sleutels), len(set(sleutels)), comp.key)

    def test_openbeheer_zit_er_bewust_niet_in(self):
        self.assertNotIn("openbeheer", registry.SLEUTELS)

    def test_negen_componenten(self):
        self.assertEqual(len(registry.COMPONENTEN), 9)

    def test_veldtypen_zijn_bekend(self):
        for comp in registry.COMPONENTEN:
            for res in comp.resources:
                for veld in (*res.velden, *res.filters):
                    self.assertIn(veld.type, registry.VELDTYPEN, f"{comp.key}/{res.key}/{veld.naam}")

    def test_elke_resource_heeft_een_titelveld_dat_bestaat(self):
        for comp in registry.COMPONENTEN:
            for res in comp.resources:
                namen = {v.naam for v in res.velden}
                titel = res.als_dict()["titelVeld"]
                self.assertTrue(
                    titel in namen or titel == res.id_veld,
                    f"{comp.key}/{res.key}: titelveld '{titel}' bestaat niet",
                )

    def test_verwijst_naar_wijst_naar_een_lijstbare_resource_in_hetzelfde_component(self):
        """
        `verwijst_naar` voedt de dropdown-voorstellen in een url-veld (zie
        opentFormulier in app.js) met een live opgehaalde lijst van die
        resource. Wijst het naar een niet-bestaande of niet-lijstbare
        resource, dan faalt die ophaal-actie stil bij elke gebruiker die het
        veld opent — vandaar deze harde registry-check.
        """
        for comp in registry.COMPONENTEN:
            sleutels = {r.key: r for r in comp.resources}
            for res in comp.resources:
                for veld in (*res.velden, *res.filters):
                    if not veld.verwijst_naar:
                        continue
                    plek = f"{comp.key}/{res.key}/{veld.naam}"
                    self.assertIn(veld.verwijst_naar, sleutels, plek)
                    doel = sleutels[veld.verwijst_naar]
                    self.assertIn("lijst", doel.methoden, plek)
                    self.assertEqual(veld.type, "url", plek)

    def test_catalogus_en_kanaal_bieden_geen_bewerkingen_aan_die_de_api_weigert(self):
        """
        Bugmelding (live gemeten tegen OpenZaak/Open Notificaties, niet
        aangenomen): de knoppen "Bewerken"/"Verwijderen" stonden aan terwijl
        de onderliggende API-endpoints die methoden niet kennen — het
        component antwoordde met "Methode 'DELETE' niet toegestaan."
        Geverifieerd tegen de officiële OpenAPI-specs: /catalogussen/{uuid}
        kent alleen GET, /kanaal/{uuid} kent GET+PUT maar geen DELETE.
        """
        oz = registry.component("openzaak")
        catalogussen = next(r for r in oz.resources if r.key == "catalogussen")
        self.assertEqual(set(catalogussen.methoden), {"lijst", "detail", "maak"})

        notif = registry.component("notificaties")
        kanaal = next(r for r in notif.resources if r.key == "kanaal")
        self.assertEqual(set(kanaal.methoden), {"lijst", "detail", "maak", "wijzig"})

    def test_nieuwe_zgw_standaard_resources_hebben_de_gemeten_methoden(self):
        """
        Live gemeten tegen openzaak.demomeer.nl (OpenAPI-specs van alle vijf
        API-groepen), niet aangenomen: acht resources die eerder ontbraken in
        CommonControl, elk met precies de methoden die de API daadwerkelijk
        aanbiedt — een deel biedt bewust geen PUT/PATCH ('wijzig') aan.
        """
        oz = registry.component("openzaak")
        VERWACHT = {
            "klantcontacten": {"lijst", "detail", "maak"},
            "zaakcontactmomenten": {"lijst", "detail", "maak", "verwijder"},
            "zaakobjecten": {"lijst", "detail", "maak", "wijzig", "verwijder"},
            "zaakverzoeken": {"lijst", "detail", "maak", "verwijder"},
            "objectinformatieobjecten": {"lijst", "detail", "maak", "verwijder"},
            "verzendingen": {"lijst", "detail", "maak", "wijzig", "verwijder"},
            "besluitinformatieobjecten": {"lijst", "detail", "maak", "verwijder"},
            "zaakobjecttypen": {"lijst", "detail", "maak", "wijzig", "verwijder"},
        }
        for sleutel, verwacht in VERWACHT.items():
            res = next(
                (r for r in oz.resources if r.key == sleutel), None
            )
            self.assertIsNotNone(res, f"resource ontbreekt: {sleutel}")
            self.assertEqual(set(res.methoden), verwacht, sleutel)

    def test_open_zaak_specifieke_acties_hebben_geen_eigen_lijst(self):
        """
        De vendor-specifieke aanmaak-acties (bv. reserveer_zaaknummer) bestaan
        niet in de VNG-standaardspec en hebben geen eigen GET-lijst/-detail —
        ze zijn de actie zelf. methoden mag dus alleen 'maak' bevatten, anders
        zou de interface een lijst proberen op te halen die niet bestaat.
        """
        # Allemaal onder het ÉÉN OpenZaak-component (dat vijf api-groepen
        # bundelt: catalogi/zaken/documenten/besluiten/autorisaties) — geen
        # aparte componenten per api-groep.
        oz = registry.component("openzaak")
        for sleutel in ("zaak_registreren", "reserveer_zaaknummer",
                        "document_registreren", "documentnummer_reserveren",
                        "besluit_verwerken"):
            res = next((r for r in oz.resources if r.key == sleutel), None)
            self.assertIsNotNone(res, f"resource ontbreekt: openzaak/{sleutel}")
            self.assertEqual(set(res.methoden), {"maak"}, sleutel)

    def test_publiceer_actie_zit_op_de_drie_conceptresources(self):
        """
        publish is een kale POST zonder body (geverifieerd: requestBody is
        None in de live spec) op precies deze drie resources.
        """
        oz = registry.component("openzaak")
        for sleutel in ("zaaktypen", "besluittypen", "informatieobjecttypen"):
            res = next(r for r in oz.resources if r.key == sleutel)
            sleutels = [a.sleutel for a in res.acties]
            self.assertIn("publish", sleutels, sleutel)
            publish = next(a for a in res.acties if a.sleutel == "publish")
            self.assertEqual(publish.velden, ())
            self.assertTrue(publish.bevestiging, "publiceren moet om bevestiging vragen")

    def test_zaak_workflow_acties_bestaan(self):
        """
        Vier Open Zaak-specifieke acties op een BESTAANDE zaak (in tegen-
        stelling tot zaak_registreren, dat een nieuwe zaak aanmaakt en dus
        een aparte resource is, geen Actie op 'zaken').
        """
        oz = registry.component("openzaak")
        zaken = next(r for r in oz.resources if r.key == "zaken")
        sleutels = {a.sleutel for a in zaken.acties}
        self.assertEqual(
            sleutels,
            {"zaak_afsluiten", "zaak_bijwerken", "zaak_opschorten", "zaak_verlengen"},
        )


class UitrolbaarheidTest(TestCase):
    """
    Twee controles die voortkomen uit een echte crashloop op het cluster.

    Beide fouten waren op een Windows-werkplek onzichtbaar en kwamen pas boven
    water in de Linux-container — precies het soort fout dat in een test hoort
    en niet in een uitrol.
    """

    def _wortel(self):
        from django.conf import settings

        return pathlib.Path(settings.BASE_DIR).parent

    def test_shellscripts_hebben_unix_regeleindes(self):
        """
        Een script met CRLF geeft de shebang '#!/bin/sh\r'. De kernel zoekt dan
        naar een interpreter die letterlijk zo heet en faalt met
        'no such file or directory' — een melding die naar het script lijkt te
        wijzen, maar over de interpreter gaat.
        """
        scripts = list(self._wortel().glob("*.sh"))
        self.assertTrue(scripts, "verwachtte minstens docker_start.sh")
        for script in scripts:
            ruw = script.read_bytes()
            self.assertNotIn(b"\r\n", ruw, f"{script.name} heeft CRLF-regeleindes")
            self.assertTrue(ruw.startswith(b"#!"), f"{script.name} mist een shebang")
            eerste = ruw.split(b"\n", 1)[0]
            self.assertFalse(eerste.endswith(b"\r"), f"{script.name}: shebang eindigt op CR")

    def test_hidden_attribuut_wordt_niet_overruled(self):
        """
        `element.hidden = true` werkt alleen als geen eigen CSS-regel display zet.

        De browser verbergt [hidden] via zijn eigen standaardstylesheet, maar élke
        author-regel die display zet wint daarvan — ongeacht specificiteit. De
        demobalk had `display: flex` en bleef daardoor ook voor beheerders staan,
        terwijl de code hem netjes op hidden zette. Een uitvoeringstest merkt dat
        niet: die kijkt naar de property, niet naar de opmaak. Vandaar deze
        controle op het vangnet.
        """
        from django.conf import settings

        css = (pathlib.Path(settings.BASE_DIR)
               / "static/commoncontrol/css/commoncontrol.css").read_text(encoding="utf-8")
        self.assertRegex(
            css, r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important",
            "stylesheet mist het vangnet [hidden] { display: none !important; }",
        )

    def test_alle_static_verwijzingen_bestaan(self):
        """
        In productie draait CommonControl met de manifest-opslag van WhiteNoise:
        een verwijzing naar een bestand dat niet bestaat is daar geen stille 404
        maar een harde fout op élke pagina.
        """
        import re

        from django.conf import settings
        from django.contrib.staticfiles import finders

        templates = pathlib.Path(settings.BASE_DIR) / "templates"
        patroon = re.compile(r"{%\s*static\s+[\'\"]([^\'\"]+)[\'\"]")
        gevonden = 0
        for template in templates.rglob("*.html"):
            for verwijzing in patroon.findall(template.read_text(encoding="utf-8")):
                gevonden += 1
                self.assertIsNotNone(
                    finders.find(verwijzing),
                    f"{template.name} verwijst naar '{verwijzing}', dat bestaat niet",
                )
        self.assertGreater(gevonden, 0, "geen enkele static-verwijzing gevonden")

class PagineringTest(TestCase):
    """
    Aanleiding: de verbindingstest van Open Notificaties faalde met
    "Onbekende query parameters: page". De ZGW-componenten (vng-api-common)
    wijzen een queryparameter die het endpoint niet kent hard af — en
    /api/v1/kanaal pagineert niet. Een blind meegestuurde ?page=1 sloopt dus
    het hele verzoek.
    """

    def test_notificaties_resources_pagineren_niet(self):
        nrc = registry.component("notificaties")
        for sleutel in ("kanaal", "abonnement"):
            self.assertFalse(nrc.resource(sleutel).gepagineerd, sleutel)

    def test_zgw_lijsten_pagineren_wel(self):
        oz = registry.component("openzaak")
        for sleutel in ("zaken", "zaaktypen", "applicaties"):
            self.assertTrue(oz.resource(sleutel).gepagineerd, sleutel)

    def test_filters_laten_page_weg_bij_een_niet_gepagineerde_resource(self):
        from django.test import RequestFactory

        nrc = registry.component("notificaties")
        verzoek = RequestFactory().get("/", {"page": "2", "search": "x"})
        resultaat = _filters(verzoek, nrc.resource("kanaal"))
        self.assertNotIn("page", resultaat)
        self.assertEqual(resultaat.get("search"), "x")

    def test_filters_sturen_page_wel_waar_het_kan(self):
        from django.test import RequestFactory

        oz = registry.component("openzaak")
        verzoek = RequestFactory().get("/", {"page": "2"})
        self.assertEqual(_filters(verzoek, oz.resource("zaken")).get("page"), "2")

    def test_verbindingstest_stuurt_geen_queryparameters(self):
        """
        De probe hoeft niet te pagineren. Stuurt hij toch iets mee, dan faalt
        hij op precies de endpoints die het strengst zijn.
        """
        from commoncontrol.verbindingen.client import ComponentClient
        from commoncontrol.verbindingen.models import Omgeving, Verbinding

        omgeving = Omgeving.objects.create(naam="Demo", slug="demo")
        verbinding = Verbinding(
            omgeving=omgeving, component="notificaties",
            basis_url="https://notificaties.demo.nl", auth_type="zgw-jwt",
            client_id="commoncontrol",
        )
        verbinding.secret = "geheim"
        verbinding.save()

        gezien = {}

        class Bespied(ComponentClient):
            def verzoek(self, methode, pad, *, params=None, body=None, geo=False):
                gezien["params"] = params
                gezien["pad"] = pad
                # Een niet-gepagineerde ZGW-endpoint geeft een kale lijst terug.
                return 200, [{"naam": "zaken"}, {"naam": "documenten"}]

        uitkomst = Bespied(verbinding).test(registry.component("notificaties").probe)

        self.assertTrue(uitkomst["ok"], uitkomst.get("melding"))
        self.assertFalse(gezien["params"], f"probe stuurde toch parameters: {gezien['params']}")
        self.assertEqual(gezien["pad"], "/api/v1/kanaal")
        # Ook zonder 'count' moet het aantal kloppen.
        self.assertIn("2 resultaten", uitkomst["melding"])
