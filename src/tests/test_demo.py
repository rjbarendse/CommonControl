"""
Het demo-account: alles inzien, niets wijzigen.

De nadruk ligt op wat het níét mag. Een leesrol die per ongeluk toch ergens kan
schrijven is erger dan geen leesrol: hij wordt uitgedeeld aan mensen die je
bewust géén schrijfrechten geeft.
"""

from __future__ import annotations

from unittest.mock import patch

import pyotp
from django.contrib.auth.models import Group, User
from django.test import TestCase

from commoncontrol.beheer import registry
from commoncontrol.toegang import rechten
from commoncontrol.toegang.models import Gebruikersprofiel
from commoncontrol.verbindingen.models import Omgeving, Verbinding

WACHTWOORD = "een-lang-genoeg-wachtwoord"


def _maak_profiel(gebruiker, *, demo=False):
    profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
    profiel.demo = demo
    profiel.totp_geheim = pyotp.random_base32()
    profiel.mfa_ingesteld = True
    profiel.save()
    return profiel


def _log_in_met_mfa(testcase, gebruiker):
    profiel = Gebruikersprofiel.objects.get(gebruiker=gebruiker)
    testcase.client.post(
        "/inloggen/", {"gebruikersnaam": gebruiker.get_username(), "wachtwoord": WACHTWOORD}
    )
    testcase.client.post("/mfa/controle/", {"code": pyotp.TOTP(profiel.totp_geheim).now()})


class StubClient:
    laatste = {}

    def __init__(self, *args, **kwargs):
        pass

    def verzoek(self, methode, pad, *, params=None, body=None, geo=False):
        StubClient.laatste = {"methode": methode, "pad": pad}
        return 200, {"count": 0, "results": []}


class DemoRechtenTest(TestCase):
    def setUp(self):
        self.gebruiker = User.objects.create_user("kijker", password=WACHTWOORD)
        _maak_profiel(self.gebruiker, demo=True)

    def test_leesrecht_op_alle_componenten(self):
        for sleutel in registry.SLEUTELS:
            with self.subTest(component=sleutel):
                self.assertTrue(rechten.mag_lezen(self.gebruiker, sleutel))
                self.assertFalse(rechten.mag_schrijven(self.gebruiker, sleutel))

    def test_ziet_ook_een_component_dat_later_wordt_toegevoegd(self):
        """
        Het recht is een jokerteken, geen lijst. Anders zou bij elk nieuw
        component iemand moeten onthouden de demo-rechten bij te werken.
        """
        self.assertEqual(rechten.rechten_van(self.gebruiker), {"*": "lezen"})
        self.assertEqual(
            rechten.zichtbare_componenten(self.gebruiker, registry.SLEUTELS),
            registry.SLEUTELS,
        )

    def test_zonder_de_vlag_geen_rechten(self):
        gewoon = User.objects.create_user("teun", password=WACHTWOORD)
        _maak_profiel(gewoon, demo=False)
        self.assertEqual(rechten.rechten_van(gewoon), {})


class DemoMagLezenTest(TestCase):
    def setUp(self):
        omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(omgeving=omgeving, component="openzaak",
                                basis_url="https://openzaak.demo.nl", auth_type="zgw-jwt",
                                client_id="commoncontrol")
        verbinding.secret = "geheim"
        verbinding.save()
        self.gebruiker = User.objects.create_user("kijker", password=WACHTWOORD)
        _maak_profiel(self.gebruiker, demo=True)
        _log_in_met_mfa(self, self.gebruiker)

    def test_kan_inloggen_en_de_tweede_factor_doen(self):
        self.assertTrue(self.client.session.get("mfa_ok"))

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_kan_een_lijst_ophalen(self):
        antwoord = self.client.get("/api/beheer/demo/openzaak/zaaktypen")
        self.assertEqual(antwoord.status_code, 200)

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_kan_een_detail_ophalen(self):
        self.assertEqual(
            self.client.get("/api/beheer/demo/openzaak/zaaktypen/abc").status_code, 200)

    def test_ziet_alle_componenten_in_de_registry(self):
        gegevens = self.client.get("/api/registry?omgeving=demo").json()["data"]
        self.assertEqual(len(gegevens["componenten"]), len(registry.SLEUTELS))
        self.assertTrue(gegevens["gebruiker"]["demo"])
        self.assertFalse(gegevens["gebruiker"]["beheerder"])
        for component in gegevens["componenten"]:
            self.assertEqual(component["niveau"], "lezen", component["key"])

    def test_kan_de_auditlog_inzien(self):
        self.assertEqual(self.client.get("/api/auditlog").status_code, 200)

    def test_kan_uitloggen(self):
        self.assertEqual(self.client.post("/uitloggen/").status_code, 302)


class DemoMagNietSchrijvenTest(TestCase):
    def setUp(self):
        omgeving = Omgeving.objects.create(naam="Demo", slug="demo", is_standaard=True)
        verbinding = Verbinding(omgeving=omgeving, component="openzaak",
                                basis_url="https://openzaak.demo.nl", auth_type="zgw-jwt",
                                client_id="commoncontrol")
        verbinding.secret = "geheim"
        verbinding.save()
        self.gebruiker = User.objects.create_user("kijker", password=WACHTWOORD)
        _maak_profiel(self.gebruiker, demo=True)
        _log_in_met_mfa(self, self.gebruiker)

    @patch("commoncontrol.beheer.views.client_voor", StubClient)
    def test_elke_schrijfmethode_wordt_geweigerd(self):
        StubClient.laatste = {}
        gevallen = [
            ("post", "/api/beheer/demo/openzaak/zaaktypen"),
            ("put", "/api/beheer/demo/openzaak/zaaktypen/abc"),
            ("patch", "/api/beheer/demo/openzaak/zaaktypen/abc"),
            ("delete", "/api/beheer/demo/openzaak/zaaktypen/abc"),
        ]
        for methode, pad in gevallen:
            with self.subTest(methode=methode):
                antwoord = getattr(self.client, methode)(
                    pad, data={}, content_type="application/json")
                self.assertEqual(antwoord.status_code, 403, f"{methode} {pad}")
                self.assertEqual(antwoord.json()["code"], "demo")
        # En er is nooit een aanroep naar het component gedaan.
        self.assertEqual(StubClient.laatste, {})

    def test_kan_geen_verbinding_testen(self):
        """Ook een test doet een uitgaande aanroep namens deze installatie."""
        antwoord = self.client.post("/api/omgevingen/demo/verbindingen/openzaak/test")
        self.assertEqual(antwoord.status_code, 403)
        self.assertEqual(antwoord.json()["code"], "demo")

    def test_kan_geen_configuratie_wijzigen(self):
        antwoord = self.client.put("/api/omgevingen/demo/configuratie",
                                   data={"domein": "x.nl", "componenten": []},
                                   content_type="application/json")
        self.assertEqual(antwoord.status_code, 403)

    def test_kan_geen_gebruikers_beheren(self):
        self.assertEqual(self.client.get("/api/gebruikers").status_code, 403)
        self.assertEqual(
            self.client.post("/api/gebruikers", data={"gebruikersnaam": "x"},
                             content_type="application/json").status_code, 403)

    def test_kan_geen_omgeving_aanmaken(self):
        antwoord = self.client.post("/api/omgevingen", data={"naam": "Nieuw"},
                                    content_type="application/json")
        self.assertEqual(antwoord.status_code, 403)
        self.assertEqual(Omgeving.objects.count(), 1)

    def test_kan_sso_niet_wijzigen(self):
        self.assertEqual(
            self.client.put("/api/sso", data={"actief": True},
                            content_type="application/json").status_code, 403)


class DemoBeheerTest(TestCase):
    """Een beheerder zet het demo-account aan en uit."""

    def setUp(self):
        self.beheerder = User.objects.create_superuser("baas", password=WACHTWOORD)
        _maak_profiel(self.beheerder)
        self.kijker = User.objects.create_user("kijker", password=WACHTWOORD)
        _maak_profiel(self.kijker)
        _log_in_met_mfa(self, self.beheerder)

    def test_aanzetten_en_weer_uit(self):
        antwoord = self.client.patch(f"/api/gebruikers/{self.kijker.pk}",
                                     data={"demo": True}, content_type="application/json")
        self.assertEqual(antwoord.status_code, 200)
        self.assertTrue(antwoord.json()["data"]["demo"])
        self.assertTrue(Gebruikersprofiel.objects.get(gebruiker=self.kijker).demo)

        self.client.patch(f"/api/gebruikers/{self.kijker.pk}",
                          data={"demo": False}, content_type="application/json")
        self.assertFalse(Gebruikersprofiel.objects.get(gebruiker=self.kijker).demo)

    def test_uitschakelen_van_het_account_blokkeert_inloggen(self):
        """'In- en uitschakelen' kan ook op accountniveau."""
        self.client.patch(f"/api/gebruikers/{self.kijker.pk}",
                          data={"demo": True, "actief": False},
                          content_type="application/json")
        self.client.post("/uitloggen/")

        self.client.post("/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertEqual(self.client.get("/api/registry").status_code, 401)

    def test_demo_aanmaken_in_een_keer(self):
        antwoord = self.client.post(
            "/api/gebruikers",
            data={"gebruikersnaam": "demo", "wachtwoord": WACHTWOORD, "demo": True},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 200)
        nieuw = User.objects.get(username="demo")
        self.assertTrue(Gebruikersprofiel.objects.get(gebruiker=nieuw).demo)
        self.assertTrue(rechten.mag_lezen(nieuw, "openzaak"))
        self.assertFalse(rechten.mag_schrijven(nieuw, "openzaak"))

    def test_demo_en_beheerder_sluiten_elkaar_uit(self):
        """De een mag alles wijzigen, de ander niets; samen is dat onzin."""
        antwoord = self.client.post(
            "/api/gebruikers",
            data={"gebruikersnaam": "raar", "wachtwoord": WACHTWOORD,
                  "demo": True, "beheerder": True},
            content_type="application/json",
        )
        self.assertEqual(antwoord.status_code, 400)
        self.assertFalse(User.objects.filter(username="raar").exists())

    def test_bestaande_beheerder_kan_niet_zomaar_demo_worden(self):
        andere = User.objects.create_superuser("baas2", password=WACHTWOORD)
        _maak_profiel(andere)
        antwoord = self.client.patch(f"/api/gebruikers/{andere.pk}",
                                     data={"demo": True}, content_type="application/json")
        self.assertEqual(antwoord.status_code, 400)
        self.assertIn("beheerdersrol", antwoord.json()["fout"])

    def test_demo_negeert_persoonlijke_rechten_niet_stiekem(self):
        """
        Een demo-account houdt leesrecht op alles, ook als er losse rijen staan.
        Belangrijk: die losse rijen mogen het nooit optillen naar schrijven.
        """
        from commoncontrol.toegang.models import ComponentToegang

        _maak_profiel(self.kijker, demo=True)
        ComponentToegang.objects.create(
            gebruiker=self.kijker, component="openzaak", niveau="schrijven")
        # Vers ophalen: get_or_create in setUp heeft de omgekeerde relatie in de
        # cache gezet, dus het object in het geheugen kent de nieuwe vlag nog niet.
        # In de applicatie speelt dat niet — daar komt de gebruiker per verzoek
        # opnieuw uit de database.
        kijker = User.objects.get(pk=self.kijker.pk)
        self.assertFalse(rechten.mag_schrijven(kijker, "openzaak"))
        self.assertTrue(rechten.mag_lezen(kijker, "openzaak"))

    def test_groepsrechten_tillen_een_demo_account_niet_op(self):
        from commoncontrol.toegang.models import ComponentToegang

        _maak_profiel(self.kijker, demo=True)
        groep = Group.objects.create(name="Schrijvers")
        ComponentToegang.objects.create(groep=groep, component="objecten", niveau="schrijven")
        self.kijker.groups.add(groep)
        kijker = User.objects.get(pk=self.kijker.pk)
        self.assertFalse(rechten.mag_schrijven(kijker, "objecten"))

class DemoZonderTweedeFactorTest(TestCase):
    """
    Een demo-account hoeft geen authenticator in te stellen.

    Bewuste versoepeling: het account bestaat om de applicatie te laten zien en
    gaat daarna op inactief. Het wachtwoord is dan wel de enige drempel, terwijl
    het account in echte gegevens kijkt — vandaar dat de rest (alleen lezen,
    pogingenlimiet, uit te schakelen) onverkort blijft gelden.
    """

    def setUp(self):
        self.demo = User.objects.create_user("kijker", password=WACHTWOORD)
        Gebruikersprofiel.objects.create(gebruiker=self.demo, demo=True)
        self.gewoon = User.objects.create_user("teun", password=WACHTWOORD)
        Gebruikersprofiel.objects.create(gebruiker=self.gewoon)

    def test_vlag_bepaalt_of_mfa_nodig_is(self):
        self.assertFalse(Gebruikersprofiel.objects.get(gebruiker=self.demo).mfa_vereist())
        self.assertTrue(Gebruikersprofiel.objects.get(gebruiker=self.gewoon).mfa_vereist())

    def test_sso_blijft_een_eigen_uitzondering(self):
        profiel = Gebruikersprofiel.objects.get(gebruiker=self.gewoon)
        profiel.via_sso = True
        profiel.save()
        self.assertFalse(profiel.mfa_vereist())

    def test_inloggen_met_alleen_een_wachtwoord(self):
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertEqual(antwoord.status_code, 302)
        self.assertNotIn("/mfa/", antwoord["Location"])
        self.assertTrue(self.client.session["mfa_ok"])
        self.assertEqual(self.client.get("/api/registry").status_code, 200)

    def test_een_gewone_gebruiker_moet_nog_steeds_langs_de_tweede_factor(self):
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "teun", "wachtwoord": WACHTWOORD})
        self.assertEqual(antwoord["Location"], "/mfa/instellen/")
        self.assertEqual(self.client.get("/api/registry").status_code, 401)

    def test_demo_uitzetten_maakt_de_tweede_factor_weer_verplicht(self):
        """Anders zou 'even demo aan' een blijvende versoepeling opleveren."""
        profiel = Gebruikersprofiel.objects.get(gebruiker=self.demo)
        profiel.demo = False
        profiel.save()

        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertEqual(antwoord["Location"], "/mfa/instellen/")

    def test_een_reeds_ingestelde_authenticator_wordt_niet_meer_gevraagd(self):
        profiel = Gebruikersprofiel.objects.get(gebruiker=self.demo)
        profiel.totp_geheim = pyotp.random_base32()
        profiel.mfa_ingesteld = True
        profiel.save()

        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertNotIn("/mfa/", antwoord["Location"])

    def test_zonder_tweede_factor_nog_steeds_alleen_lezen(self):
        self.client.post("/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        antwoord = self.client.post("/api/omgevingen", data={"naam": "X"},
                                    content_type="application/json")
        self.assertEqual(antwoord.status_code, 403)

    def test_de_pogingenlimiet_blijft_gelden(self):
        for _ in range(10):
            self.client.post("/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": "fout"})
        antwoord = self.client.post(
            "/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertEqual(antwoord.status_code, 429)

    def test_inactief_zetten_blokkeert_ook_zonder_mfa(self):
        self.demo.is_active = False
        self.demo.save()
        self.client.post("/inloggen/", {"gebruikersnaam": "kijker", "wachtwoord": WACHTWOORD})
        self.assertEqual(self.client.get("/api/registry").status_code, 401)
