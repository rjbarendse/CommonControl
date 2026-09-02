# Beveiliging

CommonControl beheert zaakgegevens en houdt de credentials vast waarmee het bij
die gegevens kan. Dit bestand beschrijft hoe dat is afgeschermd, wat het
uitdrukkelijk **niet** doet, en hoe je een kwetsbaarheid meldt.

## Een kwetsbaarheid melden

Meld een vermoedelijke kwetsbaarheid **niet** via een openbaar issue, maar per
e-mail aan **info@madaro.nl**. Vermeld wat je hebt gevonden en hoe het te
reproduceren is; je krijgt binnen vijf werkdagen een reactie.

---

## Wat de applicatie afdwingt

**Inloggen.** Een lokaal account vereist wachtwoord én TOTP uit een
authenticator-app. Twee uitzonderingen: SSO-gebruikers (de provider regelt de
tweede factor) en demo-accounts (zie hieronder). Die tweede factor is niet over te slaan: een middleware
bewaakt élk pad, en alleen expliciet vrijgegeven paden (inloggen, uitloggen,
gezondheidscontrole, SSO-callback, statische bestanden) zijn zonder sessie
bereikbaar. Die lijst wordt exact vergeleken, niet als prefix — anders zou een
later toegevoegd `/gezondheidsrapport` ongemerkt onder `/gezond` vallen.

**SSO.** Optioneel, via OpenID Connect. De `state`- en `nonce`-parameters worden
gecontroleerd en het `id_token` wordt tegen de JWKS van de provider geverifieerd
(handtekening, `aud`, `iss`). Bij SSO regelt de provider de tweede factor.

**Rechten.** Per component *alleen lezen* of *lezen en wijzigen*, persoonlijk of
via een groep; het sterkste recht telt. Beheerdersfuncties (gebruikers, groepen,
SSO, omgevingen aanmaken) vereisen de beheerdersrol. Ook het inzien of testen van
een verbinding vereist leesrecht op dat component.

**Demo-account.** Een beheerder kan een account als *demo* markeren: het mag alle
componenten inzien maar niets wijzigen. Dat is niet alleen een rechtenniveau maar
een harde grendel in de middleware — elk verzoek met een andere methode dan GET,
HEAD of OPTIONS wordt geweigerd, behalve op de paden voor inloggen, uitloggen en
de tweede factor. Zo geldt het ook voor een view die de rechtencontrole zou
vergeten. Demo en beheerder sluiten elkaar uit. Uitschakelen kan met de vlag zelf
of door het account op inactief te zetten.

⚠ Een demo-account hoeft **geen** tweede factor in te stellen: het is bedoeld om
de applicatie te laten zien en wordt daarna op inactief gezet. Daarmee is het
wachtwoord de enige drempel, terwijl het account wél in echte zaakgegevens kijkt.
Gebruik dus een uniek wachtwoord, zet het account uit zodra de demo voorbij is,
en overweeg voor demonstraties liever een omgeving met testgegevens.

**Pogingenlimiet.** Tien mislukte inlog- of MFA-pogingen per gebruikersnaam of IP
binnen een kwartier blokkeren verdere pogingen.

**Verantwoording.** Elke schrijfactie en elke inlogpoging wordt vastgelegd,
geslaagd én mislukt. Lezen wordt bewust niet gelogd; dat zou de interessante
regels onvindbaar maken.

## Geheimen

API-secrets, tokens, TOTP-sleutels en het OIDC-client-secret staan versleuteld in
de database (Fernet, AES-128-CBC + HMAC). Ze worden **nooit** naar de browser
teruggestuurd: de interface krijgt alleen `heeftToken: true`. Een leeg
invoerveld betekent overal "ongewijzigd".

⚠ **`SECRET_KEY` is verplicht.** De applicatie start niet zonder. Er staat geen
bruikbare standaardwaarde in de broncode, juist omdat die openbaar is: een
meegeleverde sleutel is een publiek bekende sleutel.

⚠ **`SECRET_KEY` nooit vervangen zonder eerst `ENCRYPTION_KEY` apart te zetten.**
Is `ENCRYPTION_KEY` leeg, dan wordt de versleutelsleutel uit `SECRET_KEY`
afgeleid; wie dan `SECRET_KEY` verandert, maakt alle opgeslagen credentials
onleesbaar en moet ze stuk voor stuk opnieuw invoeren.

Dit beschermt tegen het uitlekken van de database (een back-up, een dump in een
ticket). Het beschermt niet tegen iemand die de applicatieserver zelf beheert —
die kan de sleutel lezen. Dat is inherent: de applicatie moet de geheimen kunnen
gebruiken.

## Uitgaand verkeer

CommonControl doet HTTPS-verzoeken naar adressen die een beheerder instelt. Dat is
zijn functie, en daarmee een bewuste keuze met gevolgen:

* alleen een **beheerder** mag een verbinding aanmaken of wijzigen;
* omleidingen worden **niet blind gevolgd**. Een omleiding binnen dezelfde host
  wel (veel API's sturen `/pad` door naar `/pad/`), naar een ander adres niet —
  anders zou een gecompromitteerd component ons naar een intern adres kunnen
  sturen, bijvoorbeeld een metadata-endpoint van een cloud;
* het doorgeefluik voor ZGW-verwijzingen (`/rauw`) accepteert uitsluitend URL's
  die binnen het ingestelde adres van dat component vallen, en is alleen-lezen;
* certificaten worden gecontroleerd. `VERIFY_TLS=false` bestaat voor een
  testomgeving met een self-signed certificaat en hoort nooit in productie.

## Wat er bewust niet in zit

* **Geen wachtwoordherstel per e-mail.** Een beheerder zet een nieuw wachtwoord;
  dat vermijdt een extra aanvalsvlak op een beheerapplicatie.
* **Geen registratie.** Accounts worden aangemaakt door een beheerder of komen
  via SSO binnen.
* **Geen API voor externe systemen.** De interface is de enige client; er zijn
  geen API-sleutels voor derden.

## Bekende beperkingen

* Een TOTP-code blijft geldig binnen zijn tijdvenster (±30 s). Er is geen
  eenmalig-gebruik-registratie, dus een onderschepte code is binnen dat venster
  herbruikbaar.
* De pogingenlimiet telt ook op gebruikersnaam. Iemand kan daarmee een account
  een kwartier lang blokkeren. Dat is de klassieke afweging tussen brute force
  tegenhouden en niemand kunnen buitensluiten.
* De sterkte van een ZGW-client-secret bepaalt het component, niet wij. Een
  secret korter dan 32 tekens is zwak voor HS256; kies er een van minstens 32.

## Afhankelijkheden

Alle versies staan vast in `requirements.txt`. Django staat op de **LTS**-reeks
(5.2, beveiligingsupdates tot april 2028). Controleer de versies periodiek en
werk ze bij zodra er een beveiligingsrelease is; `pip list --outdated` en
`pip-audit` zijn daarvoor genoeg.

## Uitrol

* Zet `DEBUG=false` (de standaard) en vul `ALLOWED_HOSTS`.
* Draai achter TLS. De applicatie stuurt http door naar https, zet HSTS voor een
  jaar en markeert cookies als `Secure`, `HttpOnly` en `SameSite=Lax`.
* HSTS staat bewust **zonder** `includeSubDomains` en zonder preload: CommonControl
  draait op een subdomein en mag geen beleid opleggen aan het hele domein.
* Draai `python manage.py check --deploy` na elke configuratiewijziging.
