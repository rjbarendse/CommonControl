"""
Versleuteling van opgeslagen geheimen (API-secrets, tokens, OIDC client-secret,
TOTP-sleutels).

Waarom niet gewoon in klare tekst in de database: CommonControl bewaart de sleutels
waarmee je zaken kunt aanmaken en vernietigingslijsten kunt goedkeuren. Een
databasedump (back-up, restore naar een testomgeving, een `pg_dump` in een
ticket) mag die niet zomaar prijsgeven.

Wat dit WEL is: bescherming tegen het uitlekken van de database.
Wat dit NIET is: bescherming tegen iemand die de applicatieserver zelf beheert —
die kan de sleutel lezen en dus ook de waarden. Dat is inherent: de applicatie
moet de geheimen kunnen gebruiken.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    """
    Bouwt de Fernet-sleutel.

    Expliciet ingesteld (ENCRYPTION_KEY) heeft voorrang. Anders wordt hij
    deterministisch afgeleid uit SECRET_KEY, zodat een standaardinstallatie
    zonder extra configuratie werkt. Die afleiding gebruikt HKDF-SHA256 met een
    vaste 'info'-string, zodat dezelfde SECRET_KEY altijd dezelfde sleutel geeft
    en er nooit een verkeerd formaat ontstaat als iemand een korte SECRET_KEY
    kiest.
    """
    ingesteld = (getattr(settings, "COMMONCONTROL_ENCRYPTIE_SLEUTEL", "") or "").strip()
    if ingesteld:
        return Fernet(ingesteld.encode("ascii"))

    ruw = hashlib.pbkdf2_hmac(
        "sha256",
        settings.SECRET_KEY.encode("utf-8"),
        b"commoncontrol-secret-encryptie-v1",
        200_000,
        dklen=32,
    )
    return Fernet(base64.urlsafe_b64encode(ruw))


def versleutel(waarde: str | None) -> str:
    """Versleutelt een tekstwaarde. Leeg blijft leeg (geen nutteloze ciphertext)."""
    if not waarde:
        return ""
    return PREFIX + _fernet().encrypt(waarde.encode("utf-8")).decode("ascii")


def ontsleutel(waarde: str | None) -> str:
    """
    Ontsleutelt een eerder versleutelde waarde.

    Een waarde zonder onze prefix wordt ongewijzigd teruggegeven: dat maakt de
    overgang van een bestaande klare-tekstwaarde naar versleutelde opslag
    naadloos (bij de eerstvolgende save wordt hij alsnog versleuteld).

    Kan de waarde niet ontsleuteld worden (andere SECRET_KEY, beschadigde rij),
    dan geeft dit een lege string terug in plaats van een uitzondering. De
    beheerder ziet dan "geen secret ingesteld" en voert 'm opnieuw in, wat
    begrijpelijker is dan een crash op elke pagina die de verbinding gebruikt.
    """
    if not waarde:
        return ""
    if not waarde.startswith(PREFIX):
        return waarde
    try:
        return _fernet().decrypt(waarde[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def is_versleuteld(waarde: str | None) -> bool:
    return bool(waarde) and waarde.startswith(PREFIX)


def gelijk(a: str, b: str) -> bool:
    """Constante-tijd vergelijking, voor het vergelijken van geheimen."""
    return hmac.compare_digest(a or "", b or "")
