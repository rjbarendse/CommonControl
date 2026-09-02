"""
HTTP-client naar de CommonGround-componenten.

Eén plek waar alle vier de authenticatievormen worden afgehandeld, zodat de rest
van de applicatie alleen nog "haal dit pad op" hoeft te zeggen.

Ontwerpkeuze: geen enkele component-specifieke code buiten de registry en dit
bestand. Wat per component verschilt (pad, auth, verplichte headers) is data;
hoe je een verzoek doet is overal hetzelfde.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import time
from hashlib import sha256
from typing import Any

import httpx
from django.conf import settings

from .models import AUTH_GEEN, AUTH_SESSIE, AUTH_TOKEN, AUTH_ZGW, Verbinding

logger = logging.getLogger(__name__)

# Sessiecookies van een sessie-login hergebruiken; opnieuw inloggen bij elk
# verzoek zou elke paginaweergave verdubbelen in roundtrips.
_SESSIE_CACHE: dict[int, tuple[float, httpx.Cookies]] = {}
_SESSIE_TTL = 600  # seconden


class ApiFout(Exception):
    """Een fout van (of onderweg naar) een component, klaar om te tonen."""

    def __init__(self, melding: str, *, status: int = 0, body: Any = None,
                 velden: dict | None = None):
        super().__init__(melding)
        self.melding = melding
        self.status = status
        self.body = body
        self.velden = velden or {}

    def details(self) -> dict:
        """
        Extra context voor de interface.

        Bewust ZONDER de sleutels 'melding'/'status': die botsen met de
        parameters van fout(), en zo'n botsing gaf een TypeError midden in het
        foutpad — waardoor elke componentfout als een onleesbare HTTP 500 bij de
        gebruiker aankwam in plaats van als de melding die er al lag.
        """
        return {
            "velden": self.velden,
            "componentStatus": self.status,
            "body": self.body if isinstance(self.body, (dict, list)) else str(self.body or "")[:2000],
        }


# ── ZGW-JWT ──────────────────────────────────────────────────────────────────


def _b64url(ruw: bytes) -> str:
    return base64.urlsafe_b64encode(ruw).decode("ascii").rstrip("=")


def zgw_jwt(client_id: str, secret: str, user_id: str = "", user_weergave: str = "") -> str:
    """
    Bouwt een ZGW-JWT in het formaat van vng-api-common.

    Twee eigenaardigheden die je moet volgen, anders weigert OpenZaak het token:
    de `client_identifier` staat in de HEADER (niet alleen in de payload), en de
    payload heeft naast `client_id` ook `user_id`/`user_representation` — die
    komen in de auditlog van OpenZaak terecht.

    Dit formaat is overgenomen uit de werkende KubeManager-implementatie
    (`_zgwJwt` in main.js), niet uit een specificatie die er misschien naast zit.
    """
    header = _b64url(
        json.dumps(
            {"alg": "HS256", "typ": "JWT", "client_identifier": client_id},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    payload = _b64url(
        json.dumps(
            {
                "iss": client_id,
                "iat": int(time.time()),
                "client_id": client_id,
                "user_id": user_id or settings.COMMONCONTROL_ZGW_USER_ID,
                "user_representation": user_weergave or settings.COMMONCONTROL_ZGW_USER_WEERGAVE,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    handtekening = _b64url(
        hmac.new(secret.encode("utf-8"), f"{header}.{payload}".encode("ascii"), sha256).digest()
    )
    return f"{header}.{payload}.{handtekening}"


# ── Foutvertaling ────────────────────────────────────────────────────────────


def _fout_uit_antwoord(antwoord: httpx.Response) -> ApiFout:
    """
    Maakt van een foutantwoord een bruikbare melding.

    ZGW-componenten geven RFC 7807-fouten terug met een `invalidParams`-lijst die
    per veld zegt wat er mis is. Dat is precies wat een beheerder moet zien —
    "HTTP 400" alleen is nutteloos.
    """
    body: Any
    try:
        body = antwoord.json()
    except ValueError:
        body = antwoord.text[:2000]

    velden: dict[str, str] = {}
    delen: list[str] = []

    if isinstance(body, dict):
        for parameter in body.get("invalidParams") or []:
            naam = parameter.get("name") or "onbekend veld"
            reden = parameter.get("reason") or parameter.get("code") or "ongeldig"
            velden[naam] = reden
            delen.append(f"{naam}: {reden}")

        hoofd = body.get("detail") or body.get("title") or body.get("error")
        if not hoofd and not velden:
            # DRF-stijl: {"veld": ["melding", ...]}
            for sleutel, waarde in body.items():
                if isinstance(waarde, list) and waarde and isinstance(waarde[0], str):
                    velden[sleutel] = waarde[0]
                    delen.append(f"{sleutel}: {waarde[0]}")
        if hoofd:
            delen.insert(0, str(hoofd))
    elif body:
        delen.append(str(body)[:300])

    uitleg = {
        400: "Het component wees de gegevens af",
        401: "Niet geautoriseerd — controleer de credentials van deze verbinding",
        403: "Geen rechten — de credentials kloppen, maar mogen dit niet",
        404: "Niet gevonden",
        405: "Deze bewerking is op dit endpoint niet toegestaan",
        409: "Conflict met de huidige toestand",
        429: "Te veel verzoeken",
    }.get(antwoord.status_code, f"Het component gaf HTTP {antwoord.status_code}")

    melding = uitleg if not delen else f"{uitleg}: {' | '.join(delen)}"
    return ApiFout(melding, status=antwoord.status_code, body=body, velden=velden)


# ── Client ───────────────────────────────────────────────────────────────────


MAX_OMLEIDINGEN = 4


def _zelfde_herkomst(a: str, b: str) -> bool:
    ua, ub = httpx.URL(a), httpx.URL(b)
    return (ua.scheme, ua.host, ua.port) == (ub.scheme, ub.host, ub.port)


def _volg_omleidingen(client, methode, url, basis, **kwargs):
    """
    Volgt omleidingen, maar alleen binnen dezelfde host als de verbinding.

    Waarom niet gewoon follow_redirects=True: dan bepaalt de tegenpartij waar
    wij naartoe gaan. Een component dat (bijvoorbeeld na een inbraak) omleidt
    naar een intern adres — denk aan het metadata-endpoint van een cloud — zou
    ons dat laten ophalen en de inhoud aan de beheerder tonen. Een omleiding
    binnen dezelfde host is normaal (DRF stuurt vaak /pad naar /pad/), dus die
    volgen we wel.
    """
    for _ in range(MAX_OMLEIDINGEN):
        antwoord = client.request(methode, url, **kwargs)
        if antwoord.status_code not in (301, 302, 303, 307, 308):
            return antwoord
        locatie = antwoord.headers.get("location")
        if not locatie:
            return antwoord
        volgende = str(httpx.URL(url).join(locatie))
        if not _zelfde_herkomst(volgende, basis):
            raise ApiFout(
                "Het component leidde om naar een ander adres "
                f"({httpx.URL(volgende).host}). Dat wordt geweigerd: alleen "
                "omleidingen binnen het ingestelde adres worden gevolgd.",
                status=antwoord.status_code,
            )
        if antwoord.status_code == 303:
            methode, kwargs = "GET", {k: v for k, v in kwargs.items() if k != "json"}
        url = volgende
    raise ApiFout("Te veel omleidingen bij het benaderen van dit component.")


class ComponentClient:
    """Voert HTTP-verzoeken uit namens één verbinding."""

    def __init__(self, verbinding: Verbinding, *, user_id: str = "", user_weergave: str = ""):
        self.verbinding = verbinding
        self.user_id = user_id
        self.user_weergave = user_weergave

    # ── headers ──────────────────────────────────────────────────────────────
    def _auth_headers(self) -> dict[str, str]:
        v = self.verbinding
        if v.auth_type == AUTH_ZGW:
            token = zgw_jwt(v.client_id, v.secret, self.user_id, self.user_weergave)
            return {"Authorization": f"Bearer {token}"}
        if v.auth_type == AUTH_TOKEN:
            prefix = (v.token_prefix or "").strip()
            return {"Authorization": f"{prefix} {v.token}".strip()}
        return {}

    def _basis_headers(self, resource_geo: bool, heeft_body: bool) -> dict[str, str]:
        headers = {"Accept": "application/json", **self._auth_headers()}
        if heeft_body:
            headers["Content-Type"] = "application/json"
        if resource_geo:
            # De ZGW Zaken API eist een coördinatenstelsel op elk verzoek met
            # geo-gegevens; zonder deze headers antwoordt hij met HTTP 412.
            headers["Accept-Crs"] = "EPSG:4326"
            if heeft_body:
                headers["Content-Crs"] = "EPSG:4326"
        return headers

    # ── sessie-login ─────────────────────────────────────────────────────────
    def _sessie_cookies(self, client: httpx.Client) -> None:
        """
        Logt in met gebruikersnaam/wachtwoord en zet de sessiecookies op de client.

        Nodig voor Open Archiefbeheer, dat geen machine-credentials kent. De
        CSRF-token wordt eerst opgehaald met een gewoon GET-verzoek: Django zet
        die cookie, en DRF's sessie-authenticatie eist hem bij een POST.
        """
        v = self.verbinding
        gecachet = _SESSIE_CACHE.get(v.pk)
        if gecachet and time.time() - gecachet[0] < _SESSIE_TTL:
            client.cookies = gecachet[1]
            return

        basis = v.basis
        try:
            # Hier gaat geen geheim over de lijn, alleen het ophalen van een
            # csrftoken-cookie; een omleiding volgen mag daarom.
            client.get(f"{basis}/api/v1/health-check", follow_redirects=True)
        except httpx.HTTPError:
            pass  # alleen bedoeld om een csrftoken-cookie te krijgen

        csrf = client.cookies.get("csrftoken")
        headers = {"Content-Type": "application/json", "Referer": basis}
        if csrf:
            headers["X-CSRFToken"] = csrf

        try:
            # Bewust ZONDER omleidingen te volgen: bij een 307/308 zou httpx
            # het wachtwoord opnieuw versturen naar het omleidingsdoel.
            antwoord = client.post(
                f"{basis}/api/v1/auth/login/",
                json={"username": v.gebruikersnaam, "password": v.wachtwoord},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiFout(f"Kan niet inloggen bij {basis}: {exc}") from exc

        if antwoord.status_code >= 400:
            raise ApiFout(
                "Inloggen bij Open Archiefbeheer mislukte. Controleer de gebruikersnaam "
                "en het wachtwoord van het serviceaccount.",
                status=antwoord.status_code,
                body=antwoord.text[:500],
            )

        _SESSIE_CACHE[v.pk] = (time.time(), client.cookies)

    # ── verzoek ──────────────────────────────────────────────────────────────
    def verzoek(
        self,
        methode: str,
        pad: str,
        *,
        params: dict | None = None,
        body: Any = None,
        geo: bool = False,
    ) -> tuple[int, Any]:
        """
        Voert één verzoek uit. Geeft (status, geparste body) terug.

        Gooit ApiFout bij netwerkproblemen én bij HTTP >= 400, zodat een
        aanroeper nooit per ongeluk een foutantwoord als gegevens verwerkt.
        """
        v = self.verbinding
        if not v.is_ingevuld():
            raise ApiFout(
                f"De verbinding met {v.component} is niet volledig ingevuld. "
                "Vul de gegevens aan onder Verbindingen."
            )

        url = f"{v.basis}{pad}" if pad.startswith("/") else f"{v.basis}/{pad}"
        heeft_body = body is not None
        headers = self._basis_headers(geo, heeft_body)

        try:
            with httpx.Client(
                timeout=settings.COMMONCONTROL_HTTP_TIMEOUT,
                verify=settings.COMMONCONTROL_VERIFY_TLS,
                follow_redirects=False,   # zelf afgehandeld, zie _volg_omleidingen
            ) as client:
                if v.auth_type == AUTH_SESSIE:
                    self._sessie_cookies(client)
                    csrf = client.cookies.get("csrftoken")
                    if csrf:
                        headers["X-CSRFToken"] = csrf
                        headers["Referer"] = v.basis

                antwoord = _volg_omleidingen(
                    client, methode.upper(), url, v.basis,
                    params=params or None,
                    json=body if heeft_body else None,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise ApiFout(
                f"Time-out na {settings.COMMONCONTROL_HTTP_TIMEOUT:.0f} seconden bij {url}."
            ) from exc
        except httpx.HTTPError as exc:
            raise ApiFout(f"Kan {url} niet bereiken: {exc}") from exc

        if antwoord.status_code >= 400:
            raise _fout_uit_antwoord(antwoord)

        if antwoord.status_code == 204 or not antwoord.content:
            return antwoord.status_code, None
        try:
            return antwoord.status_code, antwoord.json()
        except ValueError:
            return antwoord.status_code, antwoord.text

    # ── verbindingstest ──────────────────────────────────────────────────────
    def test(self, probe_pad: str) -> dict:
        """
        Controleert de verbinding empirisch en stelt het token-voorvoegsel zo
        nodig bij.

        Achtergrond: de Maykin-componenten gebruiken in de praktijk
        `Authorization: Token <sleutel>`, maar de gegenereerde OpenAPI van Open
        Klant beschrijft een bearer-schema. In plaats van te kiezen welke bron
        gelijk heeft, proberen we het gewoon: eerst het ingestelde voorvoegsel,
        bij HTTP 401/403 de andere. Werkt de andere wél, dan wordt dat opgeslagen
        en gemeld — dan hoeft niemand dit te weten.
        """
        v = self.verbinding
        pogingen = [v.token_prefix or "Token"]
        if v.auth_type == AUTH_TOKEN:
            for alternatief in ("Token", "Bearer"):
                if alternatief not in pogingen:
                    pogingen.append(alternatief)

        laatste: ApiFout | None = None
        for prefix in pogingen:
            v.token_prefix = prefix
            try:
                # Bewust zonder queryparameters: een probe hoeft niet te
                # pagineren, en een niet-gepagineerde endpoint wijst ?page af.
                status, body = self.verzoek("GET", probe_pad)
            except ApiFout as exc:
                laatste = exc
                if exc.status in (401, 403) and v.auth_type == AUTH_TOKEN:
                    continue    # volgende voorvoegsel proberen
                break
            if isinstance(body, dict):
                aantal = body.get("count")
            elif isinstance(body, list):
                aantal = len(body)          # niet-gepagineerde endpoint
            else:
                aantal = None
            return {
                "ok": True,
                "status": status,
                "melding": (
                    f"Verbinding werkt (HTTP {status}"
                    + (f", {aantal} resultaten" if aantal is not None else "")
                    + (f", voorvoegsel '{prefix}'" if v.auth_type == AUTH_TOKEN else "")
                    + ")."
                ),
                "tokenPrefix": prefix,
            }

        return {
            "ok": False,
            "status": laatste.status if laatste else 0,
            "melding": laatste.melding if laatste else "Onbekende fout.",
            "tokenPrefix": v.token_prefix,
        }


def client_voor(verbinding: Verbinding, gebruiker=None) -> ComponentClient:
    """
    Client met de identiteit van de ingelogde beheerder erin.

    Zo staat in de auditlog van OpenZaak zelf wie de handeling deed, en niet
    alleen dat 'commoncontrol' het was.
    """
    if gebruiker is not None and getattr(gebruiker, "is_authenticated", False):
        naam = gebruiker.get_full_name() or gebruiker.get_username()
        return ComponentClient(
            verbinding,
            user_id=gebruiker.get_username(),
            user_weergave=f"CommonControl — {naam}"[:150],
        )
    return ComponentClient(verbinding)
