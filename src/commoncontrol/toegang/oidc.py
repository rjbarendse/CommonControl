"""
Zelfstandige OIDC-koppeling (Authorization Code flow).

Provider-agnostisch: Entra ID, Keycloak, of elke andere OpenID Connect-provider
werkt, doordat alle endpoints uit het discovery-document komen in plaats van
hardgecodeerd te zijn.

Bewust geen mozilla-django-oidc(-db): CommonControl heeft maar één OIDC-client
nodig, wil die vanuit zijn eigen instellingenscherm kunnen beheren, en wil geen
extra template-/URL-integratie meeslepen. Dit bestand is klein genoeg om
volledig te doorgronden en te testen.
"""

from __future__ import annotations

import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

_DISCOVERY_CACHE: dict[str, tuple[float, dict]] = {}
_DISCOVERY_TTL = 300  # seconden


class OIDCFout(Exception):
    """Nette, aan de gebruiker toonbare fout in de SSO-flow."""


def discovery_url(basis: str) -> str:
    """Accepteert zowel een issuer-URL als een volledige well-known-URL."""
    basis = (basis or "").strip().rstrip("/")
    if not basis:
        raise OIDCFout("Geen discovery-URL ingesteld.")
    if basis.endswith("openid-configuration"):
        return basis
    return f"{basis}/.well-known/openid-configuration"


def haal_discovery(instelling, forceer: bool = False) -> dict:
    url = discovery_url(instelling.discovery_url)
    nu = time.time()
    if not forceer:
        gecachet = _DISCOVERY_CACHE.get(url)
        if gecachet and nu - gecachet[0] < _DISCOVERY_TTL:
            return gecachet[1]

    try:
        antwoord = httpx.get(
            url,
            timeout=settings.COMMONCONTROL_HTTP_TIMEOUT,
            verify=settings.COMMONCONTROL_VERIFY_TLS,
            follow_redirects=True,
        )
        antwoord.raise_for_status()
        document = antwoord.json()
    except httpx.HTTPError as exc:
        raise OIDCFout(f"Kan de OIDC-configuratie niet ophalen bij {url}: {exc}") from exc
    except ValueError as exc:
        raise OIDCFout(f"{url} gaf geen geldige JSON terug.") from exc

    for sleutel in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if not document.get(sleutel):
            raise OIDCFout(f"Het discovery-document mist '{sleutel}'.")

    _DISCOVERY_CACHE[url] = (nu, document)
    return document


def start_url(instelling, redirect_uri: str, sessie: dict) -> str:
    """
    Bouwt de autorisatie-URL en legt state + nonce in de sessie vast.

    State beschermt tegen CSRF op de callback, nonce tegen het hergebruiken van
    een id_token. Beide worden bij de callback gecontroleerd.
    """
    document = haal_discovery(instelling)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    sessie["oidc_state"] = state
    sessie["oidc_nonce"] = nonce

    parameters = {
        "response_type": "code",
        "client_id": instelling.client_id,
        "redirect_uri": redirect_uri,
        "scope": instelling.scopes or "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    return f"{document['authorization_endpoint']}?{urlencode(parameters)}"


def verwerk_callback(instelling, code: str, redirect_uri: str, nonce: str) -> dict:
    """
    Wisselt de autorisatiecode in voor tokens en geeft de geverifieerde claims.

    De claims komen uit het id_token (handtekening gecontroleerd tegen de JWKS
    van de provider) aangevuld met het userinfo-endpoint als dat beschikbaar is —
    sommige providers (Entra ID) zetten groepsclaims alleen daar.
    """
    document = haal_discovery(instelling)

    try:
        antwoord = httpx.post(
            document["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": instelling.client_id,
                "client_secret": instelling.client_secret,
            },
            timeout=settings.COMMONCONTROL_HTTP_TIMEOUT,
            verify=settings.COMMONCONTROL_VERIFY_TLS,
        )
    except httpx.HTTPError as exc:
        raise OIDCFout(f"Kan het token-endpoint niet bereiken: {exc}") from exc

    if antwoord.status_code >= 400:
        raise OIDCFout(
            f"De identity provider weigerde de autorisatiecode (HTTP {antwoord.status_code}): "
            f"{antwoord.text[:300]}"
        )

    tokens = antwoord.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise OIDCFout("De identity provider gaf geen id_token terug.")

    try:
        jwk_client = jwt.PyJWKClient(document["jwks_uri"], timeout=int(settings.COMMONCONTROL_HTTP_TIMEOUT))
        sleutel = jwk_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            sleutel.key,
            algorithms=document.get("id_token_signing_alg_values_supported") or ["RS256"],
            audience=instelling.client_id,
            issuer=document["issuer"],
        )
    except jwt.PyJWTError as exc:
        raise OIDCFout(f"Het id_token is niet geldig: {exc}") from exc
    except Exception as exc:  # netwerkfout bij het ophalen van de JWKS
        raise OIDCFout(f"Kan de handtekening van het id_token niet controleren: {exc}") from exc

    if nonce and claims.get("nonce") and claims["nonce"] != nonce:
        raise OIDCFout("De nonce klopt niet — mogelijk een herhaald verzoek.")

    userinfo_endpoint = document.get("userinfo_endpoint")
    toegang = tokens.get("access_token")
    if userinfo_endpoint and toegang:
        try:
            info = httpx.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {toegang}"},
                timeout=settings.COMMONCONTROL_HTTP_TIMEOUT,
                verify=settings.COMMONCONTROL_VERIFY_TLS,
            )
            if info.status_code < 400:
                # id_token is leidend; userinfo vult alleen ontbrekende claims aan.
                claims = {**info.json(), **claims}
        except (httpx.HTTPError, ValueError):
            logger.warning("Userinfo-endpoint niet bruikbaar; alleen id_token-claims gebruikt.")

    return claims


def groepen_uit_claims(claims: dict, claim_naam: str) -> list[str]:
    """
    Haalt de groepslijst uit de claims.

    Providers verschillen: een lijst strings, één string, of een lijst objecten
    met een 'name'/'displayName'. Alle drie worden hier plat geslagen in plaats
    van te vertrouwen op één vorm.
    """
    ruw = claims.get(claim_naam)
    if ruw is None:
        return []
    if isinstance(ruw, str):
        return [deel.strip() for deel in ruw.split(",") if deel.strip()]
    resultaat = []
    for item in ruw if isinstance(ruw, (list, tuple)) else [ruw]:
        if isinstance(item, str):
            resultaat.append(item)
        elif isinstance(item, dict):
            naam = item.get("name") or item.get("displayName") or item.get("id")
            if naam:
                resultaat.append(str(naam))
    return resultaat
