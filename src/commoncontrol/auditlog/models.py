"""
Auditlog: wie deed wat, wanneer, met welk resultaat.

CommonControl kan zaken aanmaken, autorisaties uitdelen en vernietigingslijsten
raken. Elke schrijfactie moet dus herleidbaar zijn — óók als de actie zelf
mislukte, want een reeks mislukte pogingen is precies wat je wilt kunnen zien.

Lezen wordt bewust NIET gelogd: dat zou de tabel per beheersessie met honderden
regels vullen en de echt interessante regels onvindbaar maken. Inlogpogingen
worden wél altijd gelogd (geslaagd én mislukt).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

SOORT_KEUZES = [
    ("login", "Inloggen"),
    ("login_mislukt", "Inloggen mislukt"),
    ("mfa", "Tweede factor"),
    ("mfa_mislukt", "Tweede factor mislukt"),
    ("sso", "SSO-login"),
    ("sso_mislukt", "SSO-login mislukt"),
    ("uitloggen", "Uitloggen"),
    ("wijziging", "Wijziging in een component"),
    ("verbinding", "Verbindingsbeheer"),
    ("instelling", "Instelling gewijzigd"),
]


class Gebeurtenis(models.Model):
    tijdstip = models.DateTimeField(auto_now_add=True, db_index=True)
    soort = models.CharField(max_length=32, choices=SOORT_KEUZES, db_index=True)

    gebruiker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    # Los veld naast de FK: bij een mislukte login bestaat de gebruiker mogelijk
    # niet, en na het verwijderen van een account moet de regel leesbaar blijven.
    gebruikersnaam = models.CharField(max_length=150, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)

    omgeving = models.CharField(max_length=100, blank=True, default="")
    component = models.CharField(max_length=64, blank=True, default="", db_index=True)
    resource = models.CharField(max_length=64, blank=True, default="")
    actie = models.CharField(max_length=32, blank=True, default="")
    doel = models.CharField(max_length=500, blank=True, default="")

    gelukt = models.BooleanField(default=True)
    detail = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "gebeurtenis"
        verbose_name_plural = "gebeurtenissen"
        ordering = ("-tijdstip",)
        indexes = [models.Index(fields=["-tijdstip", "soort"])]

    def __str__(self) -> str:
        return f"{self.tijdstip:%Y-%m-%d %H:%M} {self.soort} {self.gebruikersnaam}"


def ip_van(request) -> str | None:
    """
    Het IP van de client. Achter Traefik/nginx staat het echte adres vooraan in
    X-Forwarded-For; REMOTE_ADDR is dan de proxy zelf.
    """
    doorgestuurd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if doorgestuurd:
        return doorgestuurd.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def log(request, soort: str, *, gelukt: bool = True, **velden) -> Gebeurtenis:
    """
    Schrijft één auditregel. Bewust foutbestendig: als loggen faalt mag dat de
    onderliggende handeling nooit laten mislukken.
    """
    gebruiker = getattr(request, "user", None)
    if gebruiker is not None and not getattr(gebruiker, "is_authenticated", False):
        gebruiker = None

    gegevens = {
        "soort": soort,
        "gelukt": gelukt,
        "gebruiker": gebruiker,
        "gebruikersnaam": velden.pop("gebruikersnaam", "")
        or (gebruiker.get_username() if gebruiker else ""),
        "ip": ip_van(request) if request is not None else None,
    }
    gegevens.update(velden)

    try:
        return Gebeurtenis.objects.create(**gegevens)
    except Exception:  # noqa: BLE001 — loggen mag nooit de actie breken
        import logging

        logging.getLogger(__name__).exception("Auditregel kon niet worden weggeschreven")
        return Gebeurtenis(**{k: v for k, v in gegevens.items() if k != "gebruiker"})


def mislukte_pogingen(gebruikersnaam: str, ip: str | None, minuten: int = 15) -> int:
    """
    Aantal mislukte inlogpogingen in het recente verleden, voor de eenvoudige
    rem op brute force. Telt op gebruikersnaam ÓF IP: zo helpt het zowel tegen
    het bestoken van één account als tegen één bron die accounts afgaat.
    """
    from datetime import timedelta

    from django.utils import timezone

    vanaf = timezone.now() - timedelta(minutes=minuten)
    query = Gebeurtenis.objects.filter(
        tijdstip__gte=vanaf, soort__in=("login_mislukt", "mfa_mislukt")
    )
    filter_q = models.Q(gebruikersnaam=gebruikersnaam)
    if ip:
        filter_q = filter_q | models.Q(ip=ip)
    return query.filter(filter_q).count()
