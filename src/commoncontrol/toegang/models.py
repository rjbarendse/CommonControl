"""
Toegangsmodel van CommonControl.

Drie lagen, bewust gescheiden:
  1. authenticatie  — wie ben je (wachtwoord + TOTP, of SSO)
  2. autorisatie    — wat mag je (per CommonGround-component: lezen of schrijven)
  3. verantwoording — wat heb je gedaan (zie de auditlog-app)
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

from commoncontrol import crypto

NIVEAU_GEEN = "geen"
NIVEAU_LEZEN = "lezen"
NIVEAU_SCHRIJVEN = "schrijven"

NIVEAU_KEUZES = [
    (NIVEAU_GEEN, "Geen toegang"),
    (NIVEAU_LEZEN, "Alleen lezen"),
    (NIVEAU_SCHRIJVEN, "Lezen en wijzigen"),
]

# Volgorde van zwak naar sterk. Gebruikt om het sterkste recht te kiezen als
# iemand via meerdere wegen (persoonlijk én via een groep) toegang heeft.
NIVEAU_RANG = {NIVEAU_GEEN: 0, NIVEAU_LEZEN: 1, NIVEAU_SCHRIJVEN: 2}


class Gebruikersprofiel(models.Model):
    """Extra gegevens bij een Django-gebruiker: MFA-status en herkomst."""

    gebruiker = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profiel"
    )
    # Versleuteld opgeslagen: met dit geheim kan iemand geldige TOTP-codes maken.
    totp_geheim_versleuteld = models.CharField(max_length=255, blank=True, default="")
    mfa_ingesteld = models.BooleanField(
        default=False, help_text="Heeft de gebruiker een authenticator-app gekoppeld?"
    )
    via_sso = models.BooleanField(
        default=False,
        help_text="Aangemaakt via de identity provider. MFA wordt dan door de IdP afgedwongen.",
    )
    demo = models.BooleanField(
        default=False,
        help_text=(
            "Demo-account: mag alle componenten inzien maar niets wijzigen. "
            "Aan- en uit te zetten door een beheerder."
        ),
    )
    laatste_login = models.DateTimeField(null=True, blank=True)
    laatste_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "gebruikersprofiel"
        verbose_name_plural = "gebruikersprofielen"

    def __str__(self) -> str:
        return f"Profiel van {self.gebruiker}"

    # ── TOTP-geheim ──────────────────────────────────────────────────────────
    @property
    def totp_geheim(self) -> str:
        return crypto.ontsleutel(self.totp_geheim_versleuteld)

    @totp_geheim.setter
    def totp_geheim(self, waarde: str) -> None:
        self.totp_geheim_versleuteld = crypto.versleutel(waarde)

    def mfa_vereist(self) -> bool:
        """
        Twee uitzonderingen op de verplichte tweede factor.

        SSO-gebruikers krijgen die van de identity provider; nog een eigen TOTP
        laten instellen levert twee losse registraties op zonder extra veiligheid.

        Een demo-account is bewust drempelloos: het bestaat om de applicatie te
        laten zien en wordt na afloop op inactief gezet. Let wel: zo'n account
        kan alleen lezen, maar kijkt daarbij in echte zaakgegevens. Zonder
        tweede factor is het wachtwoord de enige drempel — zet het account dus
        uit zodra de demo voorbij is, en geef het geen wachtwoord dat elders
        ook in gebruik is.
        """
        return not (self.via_sso or self.demo)


class ComponentToegang(models.Model):
    """
    Recht op één CommonGround-component, voor een gebruiker óf een groep.

    Precies één van `gebruiker`/`groep` is gevuld — afgedwongen met een
    database-constraint, niet alleen in de formulierlaag, zodat een rij die
    buiten de UI om wordt aangemaakt niet stilzwijgend voor iedereen of voor
    niemand geldt.
    """

    gebruiker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="component_rechten",
    )
    groep = models.ForeignKey(
        Group, on_delete=models.CASCADE, null=True, blank=True, related_name="component_rechten"
    )
    component = models.CharField(
        max_length=64,
        help_text="Sleutel uit de componentregistry, bijvoorbeeld 'openzaak'.",
    )
    niveau = models.CharField(max_length=16, choices=NIVEAU_KEUZES, default=NIVEAU_LEZEN)

    class Meta:
        verbose_name = "componenttoegang"
        verbose_name_plural = "componenttoegang"
        constraints = [
            models.UniqueConstraint(
                fields=["gebruiker", "component"],
                condition=models.Q(gebruiker__isnull=False),
                name="uniek_recht_per_gebruiker_component",
            ),
            models.UniqueConstraint(
                fields=["groep", "component"],
                condition=models.Q(groep__isnull=False),
                name="uniek_recht_per_groep_component",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(gebruiker__isnull=False, groep__isnull=True)
                    | models.Q(gebruiker__isnull=True, groep__isnull=False)
                ),
                name="recht_hoort_bij_gebruiker_of_groep",
            ),
        ]

    def __str__(self) -> str:
        houder = self.gebruiker or self.groep
        return f"{houder} → {self.component}: {self.niveau}"


class OIDCInstelling(models.Model):
    """
    Eén rij (singleton) met de SSO-configuratie.

    Bewust in de database en niet in environment-variabelen: een beheerder moet
    dit vanuit de app kunnen instellen en testen zonder een herstart of een
    nieuwe uitrol — precies zoals de CommonGround-componenten hun OIDC-config
    ook in de database hebben.
    """

    actief = models.BooleanField(default=False)
    knop_label = models.CharField(max_length=64, default="Inloggen met SSO")
    discovery_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="Issuer-URL of volledige .well-known/openid-configuration-URL.",
    )
    client_id = models.CharField(max_length=255, blank=True, default="")
    client_secret_versleuteld = models.CharField(max_length=1024, blank=True, default="")
    scopes = models.CharField(max_length=255, default="openid email profile")

    claim_gebruikersnaam = models.CharField(max_length=64, default="preferred_username")
    claim_email = models.CharField(max_length=64, default="email")
    claim_groepen = models.CharField(max_length=64, default="groups")

    groep_beheerders = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Leden van deze IdP-groep worden beheerder (volledige rechten).",
    )
    gebruikers_aanmaken = models.BooleanField(
        default=True,
        help_text="Onbekende gebruikers automatisch aanmaken bij een geslaagde SSO-login.",
    )

    gewijzigd_op = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SSO-instelling"
        verbose_name_plural = "SSO-instellingen"

    def __str__(self) -> str:
        return "SSO-instellingen"

    @property
    def client_secret(self) -> str:
        return crypto.ontsleutel(self.client_secret_versleuteld)

    @client_secret.setter
    def client_secret(self, waarde: str) -> None:
        self.client_secret_versleuteld = crypto.versleutel(waarde)

    @classmethod
    def huidige(cls) -> "OIDCInstelling":
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    def is_bruikbaar(self) -> bool:
        return bool(self.actief and self.discovery_url and self.client_id)
