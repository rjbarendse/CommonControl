"""
Beveiligingsregressies.

Deze tests leggen vast wat er tijdens de beveiligingsronde vóór publicatie is
rechtgezet. Ze zijn er niet om aan te tonen dat de code veilig is — dat kan een
test niet — maar om te voorkomen dat precies deze fouten terugkomen.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pyotp
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from commoncontrol.toegang.models import ComponentToegang, Gebruikersprofiel
from commoncontrol.verbindingen.client import ApiFout, _volg_omleidingen
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


class SleutelbeheerTest(TestCase):
    """De broncode is openbaar; er mag geen bruikbare sleutel in staan."""

    def test_settings_bevat_geen_standaardsleutel(self):
        bron = (Path(settings.BASE_DIR) / "commoncontrol/settings.py").read_text(encoding="utf-8")
        self.assertNotIn('_env("SECRET_KEY", "onveilige', bron)
        self.assertIn('_env("SECRET_KEY", "")', bron)

    def test_start_weigert_zonder_secret_key(self):
        """
        Zonder SECRET_KEY hoort de applicatie niet te starten. Anders draait een
        installatie op een sleutel die in de broncode staat — en daarmee zijn
        sessies te vervalsen en opgeslagen API-credentials te ontsleutelen.
        """
        omgeving = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
        omgeving.update({
            "DJANGO_SETTINGS_MODULE": "commoncontrol.settings",
            "DB_ENGINE": "django.db.backends.sqlite3",
            "DEBUG": "false",
            "PYTHONIOENCODING": "utf-8",
        })
        resultaat = subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=str(settings.BASE_DIR), env=omgeving, capture_output=True, text=True,
        )
        self.assertNotEqual(resultaat.returncode, 0, "startte zonder SECRET_KEY")
        self.assertIn("SECRET_KEY", resultaat.stderr)


class OmleidingNaInloggenTest(TestCase):
    """?next= mag nooit buiten de applicatie wijzen."""

    def setUp(self):
        User.objects.create_user("anne", password=WACHTWOORD)

    def _login_met_next(self, doel):
        return self.client.post(
            "/inloggen/", {"gebruikersnaam": "anne", "wachtwoord": WACHTWOORD, "next": doel}
        )

    def test_externe_bestemmingen_worden_geweigerd(self):
        # '/\\evil.com' is de klassieke omzeiling: browsers lezen de backslash
        # als schuine streep, dus het wordt '//evil.com' -> een andere site.
        for kwaad in ["https://evil.com/", "//evil.com/", "/\\evil.com",
                      "/\\/evil.com", "http:/evil.com", "javascript:alert(1)"]:
            with self.subTest(doel=kwaad):
                antwoord = self._login_met_next(kwaad)
                self.assertEqual(antwoord["Location"], "/mfa/instellen/")
                self.assertNotIn("evil.com", self.client.session.get("mfa_doel", ""))

    def test_eigen_pad_blijft_werken(self):
        self._login_met_next("/c/openzaak/zaaktypen")
        self.assertEqual(self.client.session.get("mfa_doel"), "/c/openzaak/zaaktypen")


class VrijePadenTest(TestCase):
    """
    De vrije paden worden exact vergeleken, niet als prefix.

    Met "/gezond" als prefix zou een later toegevoegde "/gezondheidsrapport"
    ongemerkt zonder inloggen bereikbaar zijn.
    """

    def test_alleen_het_exacte_pad_is_vrij(self):
        self.assertEqual(self.client.get("/gezond/").status_code, 200)
        for bijna in ["/gezondheidsrapport", "/inloggen-audit", "/favicon-export"]:
            with self.subTest(pad=bijna):
                antwoord = self.client.get(bijna)
                self.assertEqual(antwoord.status_code, 302, bijna)
                self.assertTrue(antwoord["Location"].startswith("/inloggen/"), bijna)


class OmleidingsbewakerTest(TestCase):
    """Een component mag ons niet naar een ander adres sturen."""

    class _Client:
        def __init__(self, antwoorden):
            self.antwoorden = list(antwoorden)
            self.gevraagd = []

        def request(self, methode, url, **kwargs):
            self.gevraagd.append(url)
            return self.antwoorden.pop(0)

    @staticmethod
    def _omleiding(naar, code=302):
        return httpx.Response(code, headers={"location": naar},
                              request=httpx.Request("GET", "https://oz.gemeente.nl/x"))

    @staticmethod
    def _ok():
        return httpx.Response(200, json={"count": 0},
                              request=httpx.Request("GET", "https://oz.gemeente.nl/x"))

    def test_omleiding_binnen_dezelfde_host_wordt_gevolgd(self):
        """DRF stuurt /pad vaak door naar /pad/; dat moet gewoon werken."""
        client = self._Client([self._omleiding("/zaken/api/v1/zaken/"), self._ok()])
        antwoord = _volg_omleidingen(client, "GET", "https://oz.gemeente.nl/zaken/api/v1/zaken",
                                     "https://oz.gemeente.nl")
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(len(client.gevraagd), 2)

    def test_omleiding_naar_een_ander_adres_wordt_geweigerd(self):
        """Denk aan een metadata-endpoint van een cloud: dat halen we niet op."""
        client = self._Client([self._omleiding("http://169.254.169.254/latest/meta-data/")])
        with self.assertRaises(ApiFout) as ctx:
            _volg_omleidingen(client, "GET", "https://oz.gemeente.nl/zaken",
                              "https://oz.gemeente.nl")
        self.assertIn("169.254.169.254", str(ctx.exception))
        # Belangrijk: het tweede verzoek is nooit gedaan.
        self.assertEqual(len(client.gevraagd), 1)

    def test_omleidingslus_stopt(self):
        client = self._Client([self._omleiding("/a"), self._omleiding("/b"),
                               self._omleiding("/c"), self._omleiding("/d")])
        with self.assertRaises(ApiFout):
            _volg_omleidingen(client, "GET", "https://oz.gemeente.nl/a", "https://oz.gemeente.nl")


class VerbindingsgegevensRechtenTest(TestCase):
    """Verbindingsgegevens en -tests horen achter het recht op dat component."""

    def setUp(self):
        self.omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(omgeving=self.omgeving, component="openzaak",
                                basis_url="https://openzaak.demo.nl", auth_type="zgw-jwt",
                                client_id="commoncontrol")
        verbinding.secret = "geheim"
        verbinding.save()
        self.buitenstaander = User.objects.create_user("niemand", password=WACHTWOORD)

    def test_zonder_recht_geen_inzage_in_de_verbinding(self):
        _log_in_met_mfa(self, self.buitenstaander)
        antwoord = self.client.get("/api/omgevingen/demo/verbindingen/openzaak")
        self.assertEqual(antwoord.status_code, 403)

    def test_zonder_recht_geen_verbindingstest(self):
        """Anders kan iedereen de applicatie een uitgaande aanroep laten doen."""
        _log_in_met_mfa(self, self.buitenstaander)
        antwoord = self.client.post("/api/omgevingen/demo/verbindingen/openzaak/test")
        self.assertEqual(antwoord.status_code, 403)

    def test_met_leesrecht_wel_inzage_maar_zonder_geheimen(self):
        ComponentToegang.objects.create(
            gebruiker=self.buitenstaander, component="openzaak", niveau="lezen"
        )
        _log_in_met_mfa(self, self.buitenstaander)
        antwoord = self.client.get("/api/omgevingen/demo/verbindingen/openzaak")
        self.assertEqual(antwoord.status_code, 200)
        self.assertNotIn("geheim", antwoord.content.decode())
        self.assertTrue(antwoord.json()["data"]["heeftSecret"])

    def test_alles_testen_slaat_componenten_zonder_recht_over(self):
        _log_in_met_mfa(self, self.buitenstaander)
        with patch("commoncontrol.verbindingen.views.client_voor") as nep:
            antwoord = self.client.post("/api/omgevingen/demo/test")
        self.assertEqual(antwoord.status_code, 200)
        self.assertEqual(antwoord.json()["data"], {})
        nep.assert_not_called()


class GeheimenNietInAntwoordenTest(TestCase):
    """Opgeslagen geheimen mogen nooit terug naar de browser."""

    def test_verbinding_als_dict_bevat_geen_waarden(self):
        omgeving = Omgeving.objects.create(naam="Demo", slug="demo")
        v = Verbinding(omgeving=omgeving, component="objecten",
                       basis_url="https://objecten.demo.nl", auth_type="token")
        v.token = "zeer-geheim-token"
        v.secret = "zeer-geheim-secret"
        v.wachtwoord = "zeer-geheim-wachtwoord"
        v.save()
        weergave = str(v.als_dict())
        for geheim in ("zeer-geheim-token", "zeer-geheim-secret", "zeer-geheim-wachtwoord"):
            self.assertNotIn(geheim, weergave)
        self.assertTrue(v.als_dict()["heeftToken"])

    def test_sso_instellingen_geven_het_clientsecret_niet_terug(self):
        beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _log_in_met_mfa(self, beheerder)
        self.client.put(
            "/api/sso",
            data={"actief": False, "discoveryUrl": "https://idp.example/",
                  "clientId": "cc", "clientSecret": "zeer-geheim-oidc"},
            content_type="application/json",
        )
        antwoord = self.client.get("/api/sso")
        self.assertNotIn("zeer-geheim-oidc", antwoord.content.decode())
        self.assertTrue(antwoord.json()["data"]["heeftClientSecret"])
