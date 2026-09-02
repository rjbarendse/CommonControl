"""
Verbindingen naar de CommonGround-componenten.

Kern van de platform-onafhankelijkheid: CommonControl praat uitsluitend HTTP tegen
de publieke API's van de componenten. Het weet niets van Kubernetes, Helm of
SSH, dus het maakt niet uit of een component op k3s, AKS, EKS, een VM of bij een
hostingpartij draait — alleen de URL en de credentials tellen.
"""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models

from commoncontrol import crypto

AUTH_ZGW = "zgw-jwt"
AUTH_TOKEN = "token"
AUTH_SESSIE = "sessie"
AUTH_GEEN = "geen"

AUTH_KEUZES = [
    (AUTH_ZGW, "ZGW-JWT (client-id + secret)"),
    (AUTH_TOKEN, "Statisch token in de Authorization-header"),
    (AUTH_SESSIE, "Sessie-login (gebruikersnaam + wachtwoord)"),
    (AUTH_GEEN, "Geen authenticatie"),
]

slug_validator = RegexValidator(
    r"^[a-z0-9][a-z0-9-]*$",
    "Alleen kleine letters, cijfers en koppeltekens.",
)


class Omgeving(models.Model):
    """
    Eén samenhangende CommonGround-installatie — in de praktijk één gemeente.

    Eén CommonControl kan er meerdere bedienen; de gebruiker kiest bovenin welke
    omgeving hij beheert, net als de clusterkeuze in KubeManager.
    """

    naam = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True, validators=[slug_validator])
    domein = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Basisdomein, bijvoorbeeld 'gemeente.nl'. Gebruikt bij automatisch zoeken.",
    )
    opmerking = models.TextField(blank=True, default="")
    is_standaard = models.BooleanField(
        default=False, help_text="Wordt geopend als er geen omgeving gekozen is."
    )
    aangemaakt_op = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "omgeving"
        verbose_name_plural = "omgevingen"
        ordering = ("naam",)

    def __str__(self) -> str:
        return self.naam

    def save(self, *args, **kwargs):
        # Precies één standaard: anders is "welke opent er" afhankelijk van de
        # toevallige rijvolgorde.
        super().save(*args, **kwargs)
        if self.is_standaard:
            Omgeving.objects.exclude(pk=self.pk).filter(is_standaard=True).update(
                is_standaard=False
            )


class Verbinding(models.Model):
    """Verbinding naar één component binnen één omgeving."""

    omgeving = models.ForeignKey(
        Omgeving, on_delete=models.CASCADE, related_name="verbindingen"
    )
    component = models.CharField(
        max_length=64, help_text="Sleutel uit de componentregistry, bijvoorbeeld 'openzaak'."
    )
    basis_url = models.URLField(
        max_length=500,
        help_text="Zonder API-pad, bijvoorbeeld https://openzaak.gemeente.nl",
    )
    actief = models.BooleanField(default=True)

    auth_type = models.CharField(max_length=16, choices=AUTH_KEUZES, default=AUTH_ZGW)

    # ZGW-JWT
    client_id = models.CharField(max_length=200, blank=True, default="")
    secret_versleuteld = models.CharField(max_length=1024, blank=True, default="")

    # Statisch token
    token_versleuteld = models.CharField(max_length=2048, blank=True, default="")
    token_prefix = models.CharField(
        max_length=20,
        default="Token",
        help_text=(
            "Voorvoegsel in de Authorization-header. De meeste Maykin-componenten "
            "gebruiken 'Token', sommige 'Bearer'. De verbindingstest stelt dit zo nodig "
            "zelf bij."
        ),
    )

    # Sessie-login (Open Archiefbeheer heeft geen machine-credentials)
    gebruikersnaam = models.CharField(max_length=200, blank=True, default="")
    wachtwoord_versleuteld = models.CharField(max_length=1024, blank=True, default="")

    laatste_test_op = models.DateTimeField(null=True, blank=True)
    laatste_test_ok = models.BooleanField(null=True, blank=True)
    laatste_test_melding = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "verbinding"
        verbose_name_plural = "verbindingen"
        ordering = ("omgeving__naam", "component")
        constraints = [
            models.UniqueConstraint(
                fields=["omgeving", "component"], name="uniek_component_per_omgeving"
            )
        ]

    def __str__(self) -> str:
        return f"{self.omgeving.naam} / {self.component}"

    # ── versleutelde velden ──────────────────────────────────────────────────
    @property
    def secret(self) -> str:
        return crypto.ontsleutel(self.secret_versleuteld)

    @secret.setter
    def secret(self, waarde: str) -> None:
        self.secret_versleuteld = crypto.versleutel(waarde)

    @property
    def token(self) -> str:
        return crypto.ontsleutel(self.token_versleuteld)

    @token.setter
    def token(self, waarde: str) -> None:
        self.token_versleuteld = crypto.versleutel(waarde)

    @property
    def wachtwoord(self) -> str:
        return crypto.ontsleutel(self.wachtwoord_versleuteld)

    @wachtwoord.setter
    def wachtwoord(self, waarde: str) -> None:
        self.wachtwoord_versleuteld = crypto.versleutel(waarde)

    # ── hulpfuncties ─────────────────────────────────────────────────────────
    @property
    def basis(self) -> str:
        """basis_url zonder afsluitende slash, zodat samenstellen voorspelbaar is."""
        return (self.basis_url or "").rstrip("/")

    def is_ingevuld(self) -> bool:
        """Zijn de gegevens compleet genoeg om een aanroep te kunnen doen?"""
        if not self.basis:
            return False
        if self.auth_type == AUTH_ZGW:
            return bool(self.client_id and self.secret)
        if self.auth_type == AUTH_TOKEN:
            return bool(self.token)
        if self.auth_type == AUTH_SESSIE:
            return bool(self.gebruikersnaam and self.wachtwoord)
        return True

    def als_dict(self) -> dict:
        """Weergave voor de UI — nooit met de geheimen erin."""
        return {
            "id": self.pk,
            "component": self.component,
            "basisUrl": self.basis,
            "actief": self.actief,
            "authType": self.auth_type,
            "clientId": self.client_id,
            "tokenPrefix": self.token_prefix,
            "gebruikersnaam": self.gebruikersnaam,
            "heeftSecret": bool(self.secret_versleuteld),
            "heeftToken": bool(self.token_versleuteld),
            "heeftWachtwoord": bool(self.wachtwoord_versleuteld),
            "ingevuld": self.is_ingevuld(),
            "laatsteTestOp": self.laatste_test_op.isoformat() if self.laatste_test_op else None,
            "laatsteTestOk": self.laatste_test_ok,
            "laatsteTestMelding": self.laatste_test_melding,
        }
