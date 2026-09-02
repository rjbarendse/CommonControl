"""
Tests voor de toegangspoort: inloggen, verplichte tweede factor, en de
rechtencontrole op de beheer-API.

Dit is de laag waar een fout het duurst is — iemand die zonder tweede factor of
zonder rechten bij zaakgegevens kan. Daarom wordt hier niet alleen het gelukte
pad getest, maar vooral wat er gebeurt als iemand een stap probeert over te
slaan.
"""

from __future__ import annotations

from unittest.mock import patch

import pyotp
from django.contrib.auth.models import User
from django.test import Client, TestCase

from commoncontrol.auditlog.models import Gebeurtenis
from commoncontrol.toegang.models import ComponentToegang, Gebruikersprofiel
from commoncontrol.verbindingen.models import Omgeving, Verbinding

WACHTWOORD = "een-lang-genoeg-wachtwoord"


class NietIngelogdTest(TestCase):
    def test_pagina_stuurt_naar_inloggen(self):
        antwoord = self.client.get("/")
        self.assertEqual(antwoord.status_code, 302)
        self.assertTrue(antwoord["Location"].startswith("/inloggen/"))

    def test_api_geeft_json_en_geen_omleiding(self):
        """Een fetch() heeft niets aan een 302 naar een HTML-pagina."""
        antwoord = self.client.get("/api/registry")
        self.assertEqual(antwoord.status_code, 401)
        self.assertEqual(antwoord.json()["code"], "niet_ingelogd")

    def test_inlogpagina_is_bereikbaar(self):
        self.assertEqual(self.client.get("/inloggen/").status_code, 200)

    def test_gezondheidscontrole_heeft_geen_sessie_nodig(self):
        antwoord = self.client.get("/gezond/")
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(antwoord.json()["status"], "ok")


class InloggenTest(TestCase):
    def setUp(self):
        self.gebruiker = User.objects.create_user("anne", password=WACHTWOORD)

    def test_fout_wachtwoord_wordt_gelogd_en_geeft_geen_hint(self):
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": "fout"}
        )
        self.assertEqual(antwoord.status_code, 401)
        self.assertContains(antwoord, "klopt niet", status_code=401)
        # Geen onderscheid tussen 'onbekende gebruiker' en 'fout wachtwoord'.
        onbekend = self.client.post(
            "/inloggen/", {"gebruikersnaam": "bestaat-niet", "wachtwoord": "fout"}
        )
        self.assertContains(onbekend, "klopt niet", status_code=401)
        self.assertEqual(Gebeurtenis.objects.filter(soort="login_mislukt").count(), 2)

    def test_geslaagde_login_stuurt_naar_mfa_instellen(self):
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD}
        )
        self.assertEqual(antwoord.status_code, 302)
        self.assertEqual(antwoord["Location"], "/mfa/instellen/")
        self.assertTrue(Gebeurtenis.objects.filter(soort="login", gelukt=True).exists())

    def test_zonder_tweede_factor_geen_toegang_tot_de_api(self):
        self.client.post("/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD})
        antwoord = self.client.get("/api/registry")
        self.assertEqual(antwoord.status_code, 401)
        self.assertEqual(antwoord.json()["code"], "mfa_vereist")

    def test_zonder_tweede_factor_geen_toegang_tot_de_interface(self):
        self.client.post("/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD})
        antwoord = self.client.get("/")
        self.assertEqual(antwoord.status_code, 302)
        self.assertEqual(antwoord["Location"], "/mfa/instellen/")

    def test_pogingenlimiet(self):
        for _ in range(10):
            self.client.post("/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": "fout"})
        # Ook mét het juiste wachtwoord blijft het geblokkeerd.
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD}
        )
        self.assertEqual(antwoord.status_code, 429)

    def test_uitloggen_kan_alleen_met_post(self):
        """Een GET-logout zou via een plaatje of link uitgevoerd kunnen worden."""
        self.assertEqual(self.client.get("/uitloggen/").status_code, 405)

    def test_next_alleen_binnen_de_applicatie(self):
        antwoord = self.client.post(
            "/inloggen/",
            {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD, "next": "https://kwaad.nl/"},
        )
        self.assertEqual(antwoord["Location"], "/mfa/instellen/")
        self.assertNotIn("kwaad.nl", self.client.session.get("mfa_doel", ""))


class TweedeFactorTest(TestCase):
    def setUp(self):
        self.gebruiker = User.objects.create_user("bram", password=WACHTWOORD)
        self.client.post("/inloggen/", {"gebruikersnaam": "bram", "wachtwoord": WACHTWOORD})

    def test_inschrijven_en_daarna_toegang(self):
        pagina = self.client.get("/mfa/instellen/")
        self.assertEqual(pagina.status_code, 200)
        geheim = self.client.session["mfa_nieuw_geheim"]

        fout = self.client.post("/mfa/instellen/", {"code": "000000"})
        self.assertEqual(fout.status_code, 200)
        self.assertFalse(self.client.session.get("mfa_ok"))

        goed = self.client.post("/mfa/instellen/", {"code": pyotp.TOTP(geheim).now()})
        self.assertEqual(goed.status_code, 302)
        self.assertTrue(self.client.session["mfa_ok"])

        profiel = Gebruikersprofiel.objects.get(gebruiker=self.gebruiker)
        self.assertTrue(profiel.mfa_ingesteld)
        # Het geheim staat versleuteld in de database, niet leesbaar.
        self.assertTrue(profiel.totp_geheim_versleuteld.startswith("enc:v1:"))
        self.assertEqual(profiel.totp_geheim, geheim)

        self.assertEqual(self.client.get("/api/registry").status_code, 200)

    def test_bij_een_volgende_sessie_alleen_de_code(self):
        self.client.get("/mfa/instellen/")
        geheim = self.client.session["mfa_nieuw_geheim"]
        self.client.post("/mfa/instellen/", {"code": pyotp.TOTP(geheim).now()})
        self.client.logout()

        self.client.post("/inloggen/", {"gebruikersnaam": "bram", "wachtwoord": WACHTWOORD})
        self.assertEqual(self.client.get("/")["Location"], "/mfa/controle/")

        verkeerd = self.client.post("/mfa/controle/", {"code": "123456"})
        self.assertEqual(verkeerd.status_code, 401)
        self.assertTrue(Gebeurtenis.objects.filter(soort="mfa_mislukt").exists())

        goed = self.client.post("/mfa/controle/", {"code": pyotp.TOTP(geheim).now()})
        self.assertEqual(goed.status_code, 302)
        self.assertTrue(self.client.session["mfa_ok"])


def _log_in_met_mfa(testcase, gebruiker) -> None:
    """Logt in en rondt de tweede factor af, zodat een test verder kan."""
    profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    geheim = pyotp.random_base32()
    profiel.totp_geheim = geheim
    profiel.mfa_ingesteld = True
    profiel.save()
    testcase.client.post(
        "/inloggen/", {"gebruikersnaam": gebruiker.get_username(), "wachtwoord": WACHTWOORD}
    )
    testcase.client.post("/mfa/controle/", {"code": pyotp.TOTP(geheim).now()})


class StubClient:
    """Vervangt de HTTP-client, zodat er in tests geen netwerk aan te pas komt."""

    laatste = {}

    def __init__(self, *args, **kwargs):
        pass

    def verzoek(self, methode, pad, *, params=None, body=None, geo=False):
        StubClient.laatste = {
            "methode": methode, "pad": pad, "params": params, "body": body, "geo": geo
        }
        if methode == "GET":
            return 200, {"count": 1, "results": [{"uuid": "abc", "omschrijving": "Test"}]}
        return 201, {"uuid": "nieuw"}


class BeheerApiRechtenTest(TestCase):
    def setUp(self):
        self.omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(
            omgeving=self.omgeving,
            component="openzaak",
            basis_url="https://openzaak.demo.nl",
            auth_type="zgw-jwt",
            client_id="commoncontrol",
        )
        verbinding.secret = "geheim"
        verbinding.save()

        self.lezer = User.objects.create_user("lezer", password=WACHTWOORD)
        ComponentToegang.objects.create(gebruiker=self.lezer, component="openzaak", niveau="lezen")

        self.schrijver = User.objects.create_user("schrijver", password=WACHTWOORD)
        ComponentToegang.objects.create(
            gebruiker=self.schrijver, component="openzaak", niveau="schrijven"
        )

        self.buitenstaander = User.objects.create_user("niemand", password=WACHTWOORD)

    def test_zonder_rechten_geen_lijst(self):
        _log_in_met_mfa(self, self.buitenstaander)
        antwoord = self.client.get("/api/beheer/demo/openzaak/zaaktypen")
        self.assertEqual(antwoord.status_code, 403)

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_lezer_mag_lezen(self):
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.get("/api/beheer/demo/openzaak/zaaktypen")
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(StubClient.laatste["pad"], "/catalogi/api/v1/zaaktypen")

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_lezer_mag_niet_schrijven(self):
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.post(
            "/api/beheer/demo/openzaak/zaaktypen",
            data={"omschrijving": "x"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 403)
        self.assertFalse(Gebeurtenis.objects.filter(soort="wijziging").exists())

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_schrijver_mag_aanmaken_en_dat_wordt_gelogd(self):
        _log_in_met_mfa(self, self.schrijver)
        antwoord = self.client.post(
            "/api/beheer/demo/openzaak/zaaktypen",
            data={"omschrijving": "Nieuw zaaktype"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(StubClient.laatste["methode"], "POST")

        regel = Gebeurtenis.objects.get(soort="wijziging")
        self.assertEqual(regel.component, "openzaak")
        self.assertEqual(regel.actie, "aanmaken")
        self.assertEqual(regel.gebruikersnaam, "schrijver")

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_zaken_krijgen_de_geo_headers_mee(self):
        """Zonder Accept-Crs weigert de ZGW Zaken API het verzoek met HTTP 412."""
        _log_in_met_mfa(self, self.lezer)
        self.client.get("/api/beheer/demo/openzaak/zaken")
        self.assertTrue(StubClient.laatste["geo"])

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_onbekende_resource_geeft_404(self):
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.get("/api/beheer/demo/openzaak/verzonnen")
        self.assertEqual(antwoord.status_code, 404)

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_alleen_lezen_resource_weigert_verwijderen(self):
        """Een status in een zaak hoort niet verwijderd te worden; alleen toegevoegd."""
        _log_in_met_mfa(self, self.schrijver)
        antwoord = self.client.delete("/api/beheer/demo/openzaak/statussen/abc")
        self.assertEqual(antwoord.status_code, 405)

    def test_zonder_verbinding_een_bruikbare_melding(self):
        ComponentToegang.objects.create(
            gebruiker=self.lezer, component="objecten", niveau="lezen"
        )
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.get("/api/beheer/demo/objecten/objects")
        self.assertEqual(antwoord.status_code, 409)
        self.assertIn("Verbindingen", antwoord.json()["fout"])

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_rauwe_url_buiten_het_component_wordt_geweigerd(self):
        """Anders zou de doorgeefluik-route elke host kunnen benaderen."""
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.get(
            "/api/beheer/demo/openzaak/rauw?url=https://ergens-anders.nl/geheim"
        )
        self.assertEqual(antwoord.status_code, 403)

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_rauwe_url_binnen_het_component_mag(self):
        _log_in_met_mfa(self, self.lezer)
        antwoord = self.client.get(
            "/api/beheer/demo/openzaak/rauw?url=https://openzaak.demo.nl/catalogi/api/v1/zaaktypen/1"
        )
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(StubClient.laatste["pad"], "/catalogi/api/v1/zaaktypen/1")


class BeheerdersApiTest(TestCase):
    def setUp(self):
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        self.gewoon = User.objects.create_user("gewoon", password=WACHTWOORD)

    def test_gewone_gebruiker_mag_geen_gebruikers_beheren(self):
        _log_in_met_mfa(self, self.gewoon)
        self.assertEqual(self.client.get("/api/gebruikers").status_code, 403)
        self.assertEqual(self.client.get("/api/sso").status_code, 403)

    def test_beheerder_kan_gebruiker_met_rechten_aanmaken(self):
        """
        Rechten die bij het aanmaken worden meegegeven moeten ook echt gelden.

        Ze werden eerder stilzwijgend genegeerd — en een test legde dat vast als
        bedoeld gedrag. Wie een formulier invult verwacht niet dat een deel van
        zijn invoer verdwijnt omdat de gebruiker toevallig nieuw is.
        """
        _log_in_met_mfa(self, self.beheerder)
        antwoord = self.client.post(
            "/api/gebruikers",
            data={
                "gebruikersnaam": "nieuw",
                "wachtwoord": WACHTWOORD,
                "rechten": {"openzaak": "lezen", "objecten": "schrijven"},
            },
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 200)
        nieuw = User.objects.get(username="nieuw")
        rechten = {
            r.component: r.niveau
            for r in ComponentToegang.objects.filter(gebruiker=nieuw)
        }
        self.assertEqual(rechten, {"openzaak": "lezen", "objecten": "schrijven"})

    def test_gebruiker_aan_een_groep_toevoegen(self):
        """Kon niet via de interface: het formulier stuurde 'groepen' nooit mee."""
        from django.contrib.auth.models import Group

        Group.objects.create(name="Zaakbeheer")
        Group.objects.create(name="Archivarissen")
        _log_in_met_mfa(self, self.beheerder)

        antwoord = self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"groepen": ["Zaakbeheer"]},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(
            list(self.gewoon.groups.values_list("name", flat=True)), ["Zaakbeheer"]
        )
        self.assertEqual(antwoord.json()["data"]["groepen"], ["Zaakbeheer"])

        # Uitvinken haalt hem er ook weer uit.
        self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"groepen": []},
            content_type="application/json",
        )
        self.assertEqual(self.gewoon.groups.count(), 0)

    def test_gebruiker_aanmaken_met_groep(self):
        from django.contrib.auth.models import Group

        Group.objects.create(name="Zaakbeheer")
        _log_in_met_mfa(self, self.beheerder)
        self.client.post(
            "/api/gebruikers",
            data={"gebruikersnaam": "teun", "wachtwoord": WACHTWOORD,
                  "groepen": ["Zaakbeheer"]},
            content_type="application/json",
        )
        teun = User.objects.get(username="teun")
        self.assertEqual(list(teun.groups.values_list("name", flat=True)), ["Zaakbeheer"])

    def test_onbekende_groep_wordt_genegeerd(self):
        """Een tikfout mag geen groep aanmaken; welke groepen bestaan is een keuze."""
        from django.contrib.auth.models import Group

        _log_in_met_mfa(self, self.beheerder)
        self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"groepen": ["BestaatNiet"]},
            content_type="application/json",
        )
        self.assertEqual(self.gewoon.groups.count(), 0)
        self.assertFalse(Group.objects.filter(name="BestaatNiet").exists())

    def test_te_kort_wachtwoord_wordt_geweigerd(self):
        _log_in_met_mfa(self, self.beheerder)
        antwoord = self.client.post(
            "/api/gebruikers",
            data={"gebruikersnaam": "kort", "wachtwoord": "kort"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 400)
        self.assertFalse(User.objects.filter(username="kort").exists())

    def test_onbekend_component_in_rechten_wordt_geweigerd(self):
        _log_in_met_mfa(self, self.beheerder)
        antwoord = self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"rechten": {"verzonnen-component": "lezen"}},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 400)

    def test_rechten_toekennen_en_weer_intrekken(self):
        _log_in_met_mfa(self, self.beheerder)
        self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"rechten": {"openzaak": "schrijven"}},
            content_type="application/json",
        )
        self.assertEqual(ComponentToegang.objects.filter(gebruiker=self.gewoon).count(), 1)

        self.client.patch(
            f"/api/gebruikers/{self.gewoon.pk}",
            data={"rechten": {"openzaak": "geen"}},
            content_type="application/json",
        )
        self.assertEqual(ComponentToegang.objects.filter(gebruiker=self.gewoon).count(), 0)

    def test_beheerder_kan_zichzelf_niet_buitensluiten(self):
        _log_in_met_mfa(self, self.beheerder)
        antwoord = self.client.patch(
            f"/api/gebruikers/{self.beheerder.pk}",
            data={"beheerder": False},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 400)
        self.beheerder.refresh_from_db()
        self.assertTrue(self.beheerder.is_superuser)


class VerbindingOpslaanTest(TestCase):
    def setUp(self):
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        _log_in_met_mfa(self, self.beheerder)

    def test_geheim_wordt_versleuteld_en_niet_teruggegeven(self):
        antwoord = self.client.put(
            "/api/omgevingen/demo/verbindingen/objecten",
            data={"basisUrl": "https://objecten.demo.nl", "authType": "token",
                  "token": "geheim-token"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 200)
        gegevens = antwoord.json()["data"]
        self.assertTrue(gegevens["heeftToken"])
        self.assertNotIn("geheim-token", antwoord.content.decode())

        verbinding = Verbinding.objects.get(component="objecten")
        self.assertTrue(verbinding.token_versleuteld.startswith("enc:v1:"))
        self.assertEqual(verbinding.token, "geheim-token")

    def test_leeg_laten_betekent_ongewijzigd(self):
        self.client.put(
            "/api/omgevingen/demo/verbindingen/objecten",
            data={"basisUrl": "https://objecten.demo.nl", "authType": "token",
                  "token": "eerste-token"},
            content_type="application/json",
        )
        self.client.put(
            "/api/omgevingen/demo/verbindingen/objecten",
            data={"basisUrl": "https://objecten-nieuw.demo.nl", "authType": "token", "token": ""},
            content_type="application/json",
        )
        verbinding = Verbinding.objects.get(component="objecten")
        self.assertEqual(verbinding.basis_url, "https://objecten-nieuw.demo.nl")
        self.assertEqual(verbinding.token, "eerste-token")

    def test_adres_zonder_schema_krijgt_https(self):
        self.client.put(
            "/api/omgevingen/demo/verbindingen/objecten",
            data={"basisUrl": "objecten.demo.nl", "authType": "token", "token": "t"},
            content_type="application/json",
        )
        self.assertEqual(
            Verbinding.objects.get(component="objecten").basis_url, "https://objecten.demo.nl"
        )

    def test_wisselen_van_authenticatievorm_ruimt_het_oude_geheim_op(self):
        self.client.put(
            "/api/omgevingen/demo/verbindingen/openzaak",
            data={"basisUrl": "https://openzaak.demo.nl", "authType": "token", "token": "t"},
            content_type="application/json",
        )
        self.client.put(
            "/api/omgevingen/demo/verbindingen/openzaak",
            data={"basisUrl": "https://openzaak.demo.nl", "authType": "zgw-jwt",
                  "clientId": "commoncontrol", "secret": "s"},
            content_type="application/json",
        )
        verbinding = Verbinding.objects.get(component="openzaak")
        self.assertEqual(verbinding.token_versleuteld, "")
        self.assertEqual(verbinding.secret, "s")

    def test_onbekend_component_wordt_geweigerd(self):
        antwoord = self.client.put(
            "/api/omgevingen/demo/verbindingen/openbeheer",
            data={"basisUrl": "https://openbeheer.demo.nl"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 404)

class FoutafhandelingApiTest(TestCase):
    """
    Onder /api/ moet ELK antwoord JSON zijn, ook een 404.

    Aanleiding: de interface toonde 'De server gaf HTTP 404.' Dat is de
    terugval als het antwoord geen JSON bevat — en Django's get_object_or_404
    stuurt standaard een HTML-pagina. De gebruiker kreeg zo een status zonder
    enige uitleg, terwijl de oorzaak (nog geen omgeving gekozen) prima te
    benoemen is.
    """

    def setUp(self):
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.beheerder)

    def test_zonder_omgeving_json_met_uitleg(self):
        for pad in [
            "/api/omgevingen/null/test",
            "/api/beheer/null/openzaak/zaaktypen",
        ]:
            antwoord = self.client.get(pad) if "beheer" in pad else self.client.post(pad)
            self.assertEqual(antwoord.status_code, 404, pad)
            self.assertEqual(antwoord.headers["Content-Type"], "application/json", pad)
            melding = antwoord.json()["fout"]
            self.assertIn("omgeving", melding.lower(), pad)
            self.assertIn("Verbindingen", melding, pad)

    def test_onbekende_omgeving_noemt_de_naam(self):
        antwoord = self.client.post("/api/omgevingen/bestaat-niet/test")
        self.assertEqual(antwoord.status_code, 404)
        self.assertIn("bestaat-niet", antwoord.json()["fout"])

    def test_configuratie_zonder_omgeving(self):
        """
        Wees eerder naar /importeren; die route bestaat niet meer, waardoor de
        test slaagde op de handler404-melding in plaats van op de bedoelde
        uitleg. Nu op een route die er wél is.
        """
        antwoord = self.client.put(
            "/api/omgevingen/undefined/configuratie",
            data={"domein": "gemeente.nl", "componenten": []},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 404)
        self.assertIn("Verbindingen", antwoord.json()["fout"])

    def test_onbekend_api_pad_geeft_json(self):
        """Ook een pad dat geen enkele route raakt mag geen HTML teruggeven."""
        antwoord = self.client.get("/api/bestaat-echt-niet")
        self.assertEqual(antwoord.status_code, 404)
        self.assertEqual(antwoord.headers["Content-Type"], "application/json")
        self.assertIn("Onbekend API-pad", antwoord.json()["fout"])

    def test_verbinding_van_onbekende_omgeving(self):
        antwoord = self.client.put(
            "/api/omgevingen/null/verbindingen/openzaak",
            data={"basisUrl": "https://x.nl"},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 404)
        self.assertEqual(antwoord.headers["Content-Type"], "application/json")

class ComponentFoutTest(TestCase):
    """
    Een fout van een component moet als leesbare 502 bij de gebruiker aankomen.

    Aanleiding: `fout(exc.melding, 502, **exc.als_dict())` gaf 'status' twee
    keer mee — één keer als parameter, één keer in de uitgeklapte dict. Dat
    wierp een TypeError midden in het foutpad, waardoor Django een HTML-500
    terugstuurde en de interface alleen "De server gaf HTTP 500" kon tonen.
    Elke componentfout was daarmee onleesbaar; het viel pas op bij een resource
    die daadwerkelijk een fout gaf.
    """

    def setUp(self):
        self.omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(
            omgeving=self.omgeving, component="openforms",
            basis_url="https://forms.demo.nl", auth_type="token",
        )
        verbinding.token = "geheim"
        verbinding.save()
        self.gebruiker = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.gebruiker)

    def _weigerende_client(self, status=403, velden=None):
        from commoncontrol.verbindingen.client import ApiFout

        class Weigert:
            def __init__(self, *a, **k):
                pass

            def verzoek(self, methode, pad, *, params=None, body=None, geo=False):
                raise ApiFout("Geen rechten — de credentials mogen dit niet",
                              status=status, velden=velden or {},
                              body={"detail": "verboden"})

        return Weigert

    def test_componentfout_wordt_een_leesbare_502(self):
        with patch("commoncontrol.beheer.views.client_voor", self._weigerende_client()):
            antwoord = self.client.get("/api/beheer/demo/openforms/forms")
        self.assertEqual(antwoord.status_code, 502)
        self.assertEqual(antwoord.headers["Content-Type"], "application/json")
        lichaam = antwoord.json()
        self.assertIn("Geen rechten", lichaam["fout"])
        # De status van het component zelf blijft beschikbaar, maar onder een
        # naam die niet botst met de parameters van fout().
        self.assertEqual(lichaam["componentStatus"], 403)

    def test_veldfouten_blijven_doorkomen(self):
        """De interface kleurt hiermee het juiste invoerveld rood."""
        velden = {"identificatie": "Bestaat al."}
        with patch("commoncontrol.beheer.views.client_voor",
                   self._weigerende_client(status=400, velden=velden)):
            antwoord = self.client.post(
                "/api/beheer/demo/openforms/forms",
                data={"name": "x"}, content_type="application/json",
            )
        self.assertEqual(antwoord.status_code, 502)
        self.assertEqual(antwoord.json()["velden"], velden)

    def test_onverwachte_uitzondering_geeft_json(self):
        """Vangnet: ook een bug in onszelf mag geen HTML onder /api/ opleveren."""

        class Ontploft:
            def __init__(self, *a, **k):
                pass

            def verzoek(self, *a, **k):
                raise RuntimeError("iets onverwachts")

        klant = Client(raise_request_exception=False)
        klant.cookies = self.client.cookies
        with patch("commoncontrol.beheer.views.client_voor", Ontploft):
            antwoord = klant.get("/api/beheer/demo/openforms/forms")
        self.assertEqual(antwoord.status_code, 500)
        self.assertEqual(antwoord.headers["Content-Type"], "application/json")
        self.assertIn("logboek", antwoord.json()["fout"])


class OpenFormulierenBereikbaarheidTest(TestCase):
    """
    Twee endpoints van Open Formulieren staan bewust niet in de registry.

    ServiceViewSet en SubmissionViewSet overschrijven de authenticatie van het
    project en eisen een browsersessie in plaats van een API-token. Ze zijn dus
    met geen enkel token te benaderen; ze aanbieden zou een menu-item opleveren
    dat altijd faalt.
    """

    def test_services_en_inzendingen_ontbreken(self):
        from commoncontrol.beheer import registry

        sleutels = [r.key for r in registry.component("openforms").resources]
        self.assertNotIn("services", sleutels)
        self.assertNotIn("submissions", sleutels)

    def test_geen_lange_toelichting_boven_elk_scherm(self):
        """
        De uitleg waarom die twee ontbreken hoort in de code en de documentatie,
        niet als banner boven elke pagina van dit component.
        """
        from commoncontrol.beheer import registry

        self.assertEqual(registry.component("openforms").let_op, "")
