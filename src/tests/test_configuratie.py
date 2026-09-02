"""
Tests voor het Configuratie-scherm: hoofddomein, componentkeuze en DNS-controle.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pyotp
from django.contrib.auth.models import User
from django.test import TestCase

from commoncontrol.toegang.models import ComponentToegang, Gebruikersprofiel
from commoncontrol.verbindingen.models import Omgeving, Verbinding

WACHTWOORD = "een-lang-genoeg-wachtwoord"


def _log_in_met_mfa(testcase, gebruiker):
    profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    geheim = pyotp.random_base32()
    profiel.totp_geheim = geheim
    profiel.mfa_ingesteld = True
    profiel.save()
    testcase.client.post(
        "/inloggen/", {"gebruikersnaam": gebruiker.get_username(), "wachtwoord": WACHTWOORD}
    )
    testcase.client.post("/mfa/controle/", {"code": pyotp.TOTP(geheim).now()})


class ConfiguratieRechtenTest(TestCase):
    def setUp(self):
        Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        self.gewoon = User.objects.create_user("teun", password=WACHTWOORD)
        ComponentToegang.objects.create(
            gebruiker=self.gewoon, component="openzaak", niveau="schrijven"
        )

    def test_alleen_beheerders(self):
        _log_in_met_mfa(self, self.gewoon)
        self.assertEqual(self.client.get("/api/omgevingen/demo/configuratie").status_code, 403)
        self.assertEqual(
            self.client.post("/api/dns-check", data={"hostnaam": "example.org"},
                             content_type="application/json").status_code, 403)


class ConfiguratieTest(TestCase):
    def setUp(self):
        self.omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.beheerder)

    def _configuratie(self):
        return self.client.get("/api/omgevingen/demo/configuratie").json()["data"]

    def _bewaar(self, **body):
        return self.client.put("/api/omgevingen/demo/configuratie",
                               data=body, content_type="application/json")

    def test_toont_alle_componenten_met_een_voorstel(self):
        self.omgeving.domein = "gemeente.nl"
        self.omgeving.save()
        gegevens = self._configuratie()
        self.assertEqual(len(gegevens["componenten"]), 9)
        openzaak = next(c for c in gegevens["componenten"] if c["component"] == "openzaak")
        self.assertEqual(openzaak["voorstel"], "openzaak.gemeente.nl")
        self.assertFalse(openzaak["gebruikt"])

    def test_component_aanzetten_maakt_een_verbinding(self):
        antwoord = self._bewaar(
            domein="gemeente.nl",
            componenten=[{"component": "openzaak", "gebruikt": True,
                          "hostnaam": "openzaak.gemeente.nl"}],
        )
        self.assertEqual(antwoord.status_code, 200)
        verbinding = Verbinding.objects.get(component="openzaak")
        self.assertEqual(verbinding.basis_url, "https://openzaak.gemeente.nl")
        self.assertTrue(verbinding.actief)
        # De authenticatievorm komt uit de registry, niet uit het formulier.
        self.assertEqual(verbinding.auth_type, "zgw-jwt")

    def test_hostnaam_mag_met_schema_en_pad_worden_geplakt(self):
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": True,
                                   "hostnaam": "https://objecten.gemeente.nl/api/v2/"}])
        self.assertEqual(
            Verbinding.objects.get(component="objecten").basis_url,
            "https://objecten.gemeente.nl",
        )

    def test_uitvinken_bewaart_de_inloggegevens(self):
        """Anders zou even uitzetten betekenen: token opnieuw aanvragen."""
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": True,
                                   "hostnaam": "objecten.gemeente.nl"}])
        verbinding = Verbinding.objects.get(component="objecten")
        verbinding.token = "geheim-token"
        verbinding.save()

        self._bewaar(componenten=[{"component": "objecten", "gebruikt": False}])
        verbinding.refresh_from_db()
        self.assertFalse(verbinding.actief)
        self.assertEqual(verbinding.token, "geheim-token")

    def test_opnieuw_aanzetten_werkt(self):
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": True,
                                   "hostnaam": "objecten.gemeente.nl"}])
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": False}])
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": True,
                                   "hostnaam": "objecten.gemeente.nl"}])
        self.assertTrue(Verbinding.objects.get(component="objecten").actief)

    def test_verwijderen_wist_alles(self):
        self._bewaar(componenten=[{"component": "objecten", "gebruikt": True,
                                   "hostnaam": "objecten.gemeente.nl"}])
        self._bewaar(componenten=[{"component": "objecten", "verwijderen": True}])
        self.assertFalse(Verbinding.objects.filter(component="objecten").exists())

    def test_aanvinken_zonder_hostnaam_wordt_geweigerd(self):
        antwoord = self._bewaar(
            componenten=[{"component": "openzaak", "gebruikt": True, "hostnaam": ""}])
        self.assertEqual(antwoord.status_code, 400)
        self.assertIn("hostnaam", antwoord.json()["fout"].lower())
        self.assertFalse(Verbinding.objects.filter(component="openzaak").exists())

    def test_onzinnige_hostnaam_wordt_geweigerd(self):
        for slecht in ["geen punt", "http://", "openzaak", "-fout.nl", "a..b.nl"]:
            with self.subTest(hostnaam=slecht):
                antwoord = self._bewaar(
                    componenten=[{"component": "openzaak", "gebruikt": True,
                                  "hostnaam": slecht}])
                self.assertEqual(antwoord.status_code, 400, slecht)

    def test_onbekend_component_wordt_genegeerd(self):
        antwoord = self._bewaar(
            componenten=[{"component": "openbeheer", "gebruikt": True,
                          "hostnaam": "openbeheer.gemeente.nl"}])
        self.assertEqual(antwoord.status_code, 200)
        self.assertFalse(Verbinding.objects.filter(component="openbeheer").exists())

    def test_domein_wordt_opgeslagen_en_genormaliseerd(self):
        self._bewaar(domein="HTTPS://Gemeente.NL/pad", componenten=[])
        self.omgeving.refresh_from_db()
        self.assertEqual(self.omgeving.domein, "gemeente.nl")

    def test_wijziging_komt_in_de_auditlog(self):
        from commoncontrol.auditlog.models import Gebeurtenis

        self._bewaar(domein="gemeente.nl",
                     componenten=[{"component": "openzaak", "gebruikt": True,
                                   "hostnaam": "openzaak.gemeente.nl"}])
        regel = Gebeurtenis.objects.filter(actie="configuratie").first()
        self.assertIsNotNone(regel)
        self.assertIn("openzaak", regel.doel)


class UitgeschakeldComponentTest(TestCase):
    """Een component dat niet in gebruik is, is ook via een #-link niet te openen."""

    def setUp(self):
        omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(omgeving=omgeving, component="openzaak",
                                basis_url="https://openzaak.demo.nl", auth_type="zgw-jwt",
                                client_id="commoncontrol", actief=False)
        verbinding.secret = "geheim"
        verbinding.save()
        self.gebruiker = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.gebruiker)

    def test_resource_ophalen_geeft_een_bruikbare_melding(self):
        antwoord = self.client.get("/api/beheer/demo/openzaak/zaaktypen")
        self.assertEqual(antwoord.status_code, 409)
        self.assertIn("Configuratie", antwoord.json()["fout"])

    def test_registry_meldt_dat_het_component_uit_staat(self):
        gegevens = self.client.get("/api/registry?omgeving=demo").json()["data"]
        openzaak = next(c for c in gegevens["componenten"] if c["key"] == "openzaak")
        self.assertFalse(openzaak["verbinding"]["actief"])


class DnsControleTest(TestCase):
    def setUp(self):
        Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.beheerder)

    def _check(self, hostnaam):
        return self.client.post("/api/dns-check", data={"hostnaam": hostnaam},
                                content_type="application/json")

    def test_gevonden_hostnaam(self):
        nep = [(socket.AF_INET, None, None, "", ("192.0.2.10", 0)),
               (socket.AF_INET, None, None, "", ("192.0.2.11", 0))]
        with patch("commoncontrol.verbindingen.views.socket.getaddrinfo", return_value=nep):
            antwoord = self._check("openzaak.gemeente.nl")
        gegevens = antwoord.json()["data"]
        self.assertTrue(gegevens["ok"])
        self.assertEqual(gegevens["adressen"], ["192.0.2.10", "192.0.2.11"])

    def test_niet_gevonden_is_geen_serverfout(self):
        """Een onbekende naam is een normale uitkomst, geen storing."""
        with patch("commoncontrol.verbindingen.views.socket.getaddrinfo",
                   side_effect=socket.gaierror(-2, "Name or service not known")):
            antwoord = self._check("bestaat-niet.gemeente.nl")
        self.assertEqual(antwoord.status_code, 200)
        gegevens = antwoord.json()["data"]
        self.assertFalse(gegevens["ok"])
        self.assertIn("DNS", gegevens["melding"])

    def test_hostnaam_wordt_uitgepakt_uit_een_volledige_url(self):
        with patch("commoncontrol.verbindingen.views.socket.getaddrinfo",
                   return_value=[(socket.AF_INET, None, None, "", ("192.0.2.10", 0))]) as nep:
            self._check("https://openzaak.gemeente.nl:8443/api/v1/")
        self.assertEqual(nep.call_args[0][0], "openzaak.gemeente.nl")

    def test_onzin_wordt_geweigerd(self):
        for slecht in ["", "geen punt", "../etc/passwd", "a b.nl"]:
            with self.subTest(hostnaam=slecht):
                self.assertEqual(self._check(slecht).status_code, 400, slecht)

    def test_trage_resolver_loopt_niet_vast(self):
        import time

        def traag(*_a, **_k):
            time.sleep(2)

        with patch("commoncontrol.verbindingen.views.DNS_TIMEOUT", 0.2), \
                patch("commoncontrol.verbindingen.views.socket.getaddrinfo", side_effect=traag):
            antwoord = self._check("traag.gemeente.nl")
        gegevens = antwoord.json()["data"]
        self.assertFalse(gegevens["ok"])
        self.assertIn("Geen antwoord", gegevens["melding"])

class GeenVerkeerNaarUitgeschakeldeComponentenTest(TestCase):
    """
    Uitvinken onder Configuratie moet ook het verkéér stoppen.

    Aanleiding: 'Alle verbindingen testen' filterde alleen op rechten, niet op
    'in gebruik'. Een component dat de beheerder bewust had uitgezet werd dus
    alsnog benaderd — en leverde een foutmelding op over iets wat niet in gebruik
    is.
    """

    def setUp(self):
        self.omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        self.aan = Verbinding(omgeving=self.omgeving, component="openzaak",
                              basis_url="https://openzaak.demo.nl", auth_type="zgw-jwt",
                              client_id="commoncontrol", actief=True)
        self.aan.secret = "geheim"
        self.aan.save()
        self.uit = Verbinding(omgeving=self.omgeving, component="objecten",
                              basis_url="https://objecten.demo.nl", auth_type="token",
                              actief=False,
                              laatste_test_ok=False,
                              laatste_test_melding="oude fout uit een eerdere test")
        self.uit.token = "token"
        self.uit.save()

        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, self.beheerder)

    def test_alles_testen_slaat_een_uitgeschakeld_component_over(self):
        benaderd = []

        class Stub:
            def __init__(self, verbinding, *a, **k):
                self.verbinding = verbinding

            def test(self, probe):
                benaderd.append(self.verbinding.component)
                return {"ok": True, "status": 200, "melding": "werkt"}

        with patch("commoncontrol.verbindingen.views.client_voor", Stub):
            antwoord = self.client.post("/api/omgevingen/demo/test")

        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(benaderd, ["openzaak"])
        self.assertNotIn("objecten", antwoord.json()["data"])

    def test_losse_test_weigert_een_uitgeschakeld_component(self):
        benaderd = []

        class Stub:
            def __init__(self, *a, **k):
                pass

            def test(self, probe):
                benaderd.append(probe)
                return {"ok": True, "status": 200, "melding": "werkt"}

        with patch("commoncontrol.verbindingen.views.client_voor", Stub):
            antwoord = self.client.post("/api/omgevingen/demo/verbindingen/objecten/test")

        self.assertEqual(antwoord.status_code, 409)
        self.assertIn("Configuratie", antwoord.json()["fout"])
        self.assertEqual(benaderd, [], "er is toch verkeer naar het component gegaan")

    def test_uitvinken_wist_de_vorige_uitslag(self):
        """Anders blijft er een rode melding staan over iets wat uitstaat."""
        self.aan.laatste_test_ok = False
        self.aan.laatste_test_melding = "certificaat klopt niet"
        self.aan.save()

        self.client.put("/api/omgevingen/demo/configuratie",
                        data={"componenten": [{"component": "openzaak", "gebruikt": False}]},
                        content_type="application/json")

        self.aan.refresh_from_db()
        self.assertFalse(self.aan.actief)
        self.assertIsNone(self.aan.laatste_test_ok)
        self.assertEqual(self.aan.laatste_test_melding, "")

    def test_gegevens_blijven_wel_bewaard(self):
        self.client.put("/api/omgevingen/demo/configuratie",
                        data={"componenten": [{"component": "openzaak", "gebruikt": False}]},
                        content_type="application/json")
        self.aan.refresh_from_db()
        self.assertEqual(self.aan.secret, "geheim")
        self.assertEqual(self.aan.basis_url, "https://openzaak.demo.nl")
