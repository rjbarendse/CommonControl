# CommonControl

> ⚠ **Eerste beta-versie.** CommonControl is alleen tegen een demo omgeving 
> met elk component getest. Gebruik het vooralsnog met dat in het
> achterhoofd, en meld gerust een issue als iets niet klopt.

Webgebaseerde beheerinterface voor de CommonGround-componenten. Gebouwd door
**Madaro Services**.

CommonControl praat **uitsluitend via de publieke API's** van de componenten. Het
weet niets van Kubernetes, Helm of SSH. Daardoor maakt het niet uit waar de
componenten draaien — k3s, AKS, EKS, een virtuele machine of bij een
hostingpartij: alleen het adres en de inloggegevens tellen.

---

## Wat het beheert

Negen ZGW-componenten uit de CommonGround-stack.

| Component | API('s) | Authenticatie | Beheerbaar |
|---|---|---|---|
| **OpenZaak** | `/catalogi`, `/zaken`, `/documenten`, `/besluiten`, `/autorisaties` (elk `/api/v1`) | ZGW-JWT | 18 resources: catalogussen, zaaktypen, statustypen, resultaattypen, roltypen, eigenschappen, informatieobjecttypen, besluittypen, koppelingen, zaken, statussen, rollen, resultaten, zaakdocumenten, documenten, gebruiksrechten, besluiten, applicaties |
| **Open Notificaties** | `/api/v1` | ZGW-JWT | kanalen, abonnementen (webhooks) |
| **Objecttypen API** | `/api/v2` | `Token` | objecttypen, versies (genest) |
| **Objecten API** | `/api/v2` | `Token` | objecten, permissies (lezen) |
| **Open Klant** | `/klantinteracties/api/v1`, `/contactgegevens/api/v1` | `Token` | partijen, digitale adressen, klantcontacten, betrokkenen, actoren, interne taken, categorieën, personen, organisaties |
| **Open Product** | `/producttypen/api/v1`, `/producten/api/v1` | `Token` | producttypen, thema's, organisaties, prijzen, links, contacten, content, acties, producten |
| **Open Formulieren** | `/api/v2` | `Token` | formulieren, formulierdefinities, categorieën, thema's, producten |
| **Open Inwoner** | `/api` | `Token` | PDC: categorieën, producten |
| **Open Archiefbeheer** | `/api/v1` | sessie-login | vernietigingslijsten, regels, beoordelingen, gebruikers, archiefconfiguratie (lezen) |

### Eerlijke beperkingen

Twee componenten bieden zelf minder aan dan de rest. Dat is geen keuze van CommonControl, en het wordt in de interface ook zo getoond:

* **Open Inwoner** heeft maar een klein deel van zijn beheer als API: de
  producten- en dienstencatalogus. Portaalinhoud blijven in
  de eigen beheeromgeving.
* **Open Archiefbeheer** kent geen machine-credentials; zijn API is voor zijn
  eigen webinterface en werkt met een sessie-login. CommonControl logt daarom in
  met een serviceaccount. Vernietigingslijsten zijn hier **alleen te lezen** —
  beoordelen en vernietigen hoort in Open Archiefbeheer zelf te gebeuren, waar
  het vier-ogenprincipe is ingebouwd.

Bij **Open Formulieren** ontbreken twee endpoints die wel bestaan: services en
inzendingen. Beide overschrijven de authenticatie van het project zelf — inzendingen
horen bij de invulsessie van de burger, services zijn alleen met een sessie-login
bereikbaar. Geen token en geen rechtenniveau helpt daar, dus ze staan er niet in
plaats van te blijven falen. De thema's en producten zijn er wel, maar vragen een
token van een gebruiker met stafftoegang.

Verder is de formulierbouwer van Open Formulieren (velden slepen) bewust niet
meegenomen; CommonControl beheert daar de formulieren, categorieën en koppelingen.

---

## Hoe het in elkaar zit

```
commoncontrol/
├── Dockerfile · docker_start.sh · docker-compose.yml
├── k8s/                        manifesten (namespace, database, app, ingress)
└── src/
    ├── manage.py
    ├── commoncontrol/
    │   ├── settings.py         alles uit omgevingsvariabelen
    │   ├── test_settings.py    sqlite + gewone staticfiles, voor de testsuite
    │   ├── urls.py
    │   ├── crypto.py           versleuteling van opgeslagen geheimen (Fernet)
    │   ├── api.py              JSON-hulpjes en de rechtendecorator
    │   ├── beheer/
    │   │   ├── registry.py     ← DE BRON VAN WAARHEID: 9 componenten, 57 resources
    │   │   └── views.py        één generieke set views voor álle resources
    │   ├── verbindingen/
    │   │   ├── models.py       omgevingen en verbindingen (geheimen versleuteld)
    │   │   └── client.py       HTTPS-client, ZGW-JWT, foutvertaling
    │   ├── toegang/            inloggen, TOTP-MFA, SSO, rechten per component
    │   └── auditlog/           wie deed wat, wanneer, met welk resultaat
    ├── templates/              inlog- en MFA-schermen
    ├── static/commoncontrol/       huisstijl (css) en de interface (app.js)
    └── tests/                  164 tests
```

### De registry is het hart

`src/commoncontrol/beheer/registry.py` beschrijft elk component en elke resource één
keer: pad, velden, veldtypen, filters, welke bewerkingen mogen. Zowel de API-laag
als de interface leiden daar álles uit af, er is geen enkele component-specifieke
view of pagina.

Eén registry per component, om dezelfde reden als bij vergelijkbare
CommonGround-tooling: negen componenten × 57 resources handmatig uitschrijven
zou gegarandeerd gaan scheeflopen zodra er iets wijzigt.

**Een resource toevoegen = één descriptor erbij.** Er verschijnt dan vanzelf een
menu-item, een lijst met kolommen en filters, een formulier met validatie, en
rechtencontrole.

### Niets is onbereikbaar

Elk formulier heeft onderaan "Alle velden als JSON". Kent de registry een veld
(nog) niet, dan is het daar alsnog te zien en te bewerken. Zo hoeft een minder
gangbaar veld nooit te wachten op een aanpassing in de code.

---

## Toegang

**Inloggen** kan op twee manieren; beide kunnen tegelijk aanstaan.

* **Lokaal account met verplichte TOTP-MFA.** Bij de eerste login wordt om een
  authenticator-app gevraagd. Dat is niet over te slaan: een middleware bewaakt
  élk pad, dus een nieuwe pagina kan niet per ongeluk buiten de controle vallen.
* **SSO via OpenID Connect** (Entra ID, Keycloak, of een andere provider). De
  MFA is dan de verantwoordelijkheid van de provider. In te stellen en
  te testen vanuit de applicatie zelf, onder *Instellingen → Single Sign On*.

**Rechten** gelden per component en zijn *alleen lezen* of *lezen en wijzigen*.
Iemand kan rechten persoonlijk krijgen én via een groep; het sterkste recht
telt. Bij SSO worden gebruikers gekoppeld aan de groep met dezelfde naam als bij
de provider. Een beheerder mag alles, inclusief instellingen.

**Demo-account**: een beheerder kan een account markeren als demo. Zo iemand ziet
alle componenten en mag alles inzien, maar kan niets wijzigen — afgedwongen in de
middleware, niet alleen via rechten. Handig om de applicatie te laten zien zonder
risico. Aan en uit met één vinkje.

**Auditlog**: elke schrijfactie en elke inlogpoging wordt vastgelegd, geslaagd
én mislukt. Lezen wordt bewust niet gelogd — dat zou de echt interessante regels
onvindbaar maken. Een gewone gebruiker ziet zijn eigen handelingen, een
beheerder alles.

**Geheimen** (API-secrets, tokens, TOTP-sleutels, het OIDC-client-secret) staan
versleuteld in de database (Fernet) en worden nooit naar de browser
teruggestuurd. Een veld leeg laten betekent overal "ongewijzigd".

---

## Inrichten

Twee schermen, in deze volgorde. Beide alleen voor beheerders.

**Instellingen → Configuratie** is het instapscherm:

1. **Hoofddomein** van de organisatie, bijvoorbeeld `gemeente.nl`. Daaruit worden
   de hostnamen voorgesteld (`openzaak.gemeente.nl`, `notificaties.gemeente.nl`, …).
2. **Welke componenten gebruikt u** — vink aan wat u gebruikt en vul per component
   de hostnaam in, zonder `/api`. Bij het invullen draait meteen een **DNS-controle**:
   een groen vinkje met de gevonden adressen, of een rood kruisje met de reden.
3. Wat niet is aangevinkt blijft **grijs in het menu** en is niet te openen — ook
   niet via een directe link.
4. Uitvinken kan altijd en **bewaart de inloggegevens**, zodat opnieuw aanzetten
   geen nieuw token vraagt. Een aparte knop wist adres én credentials.

**Instellingen → Verbindingen** is de tweede stap: per component de inloggegevens
(client-id en secret, of een API-token) en de verbindingstest.

Die scheiding is opzet: het adres kent iedereen die de omgeving inricht, de
credentials niet.

> **Waar komt een API-token vandaan?** Voor de zes componenten met tokenauthenticatie
> maak je die aan in KubeManager, onder *CommonGround → Beheer → het component →
> API-tokens*. Met de hand kan ook, in de beheeromgeving van het component zelf onder
> *Auth Token → Tokens*. De interface wijst per component de weg.
>
> De componenten hanteren twee soorten tokens, en dat verschil is zichtbaar bij het
> aanmaken. Bij Open Formulieren, Open Product en Open Inwoner hangt een token aan een
> **gebruiker** en erft het diens rechten — vandaar dat sommige onderdelen een account
> met stafftoegang vragen. Bij Objecttypen, Objecten en Open Klant staat een token op
> zichzelf, met een naam en een verplichte contactpersoon.
>
> Laat `commonground-token` daarbij met rust: dat is door de installatiewizard
> aangemaakt en andere componenten melden zich daarmee. Maak voor CommonControl een
> eigen token aan.

**De verbindingstest gokt niet.** De componenten gebruiken in de praktijk
`Authorization: Token <sleutel>`, terwijl de gegenereerde OpenAPI van Open Klant
een bearer-schema beschrijft. In plaats van te kiezen welke bron gelijk heeft,
probeert de test beide en slaat op wat werkelijk werkt.

---

## Draaien

### Lokaal

Zet eerst een `.env` naast `docker-compose.yml`; zonder deze waarden start het
niet, met opzet want er zijn geen standaardgeheimen die in een openbare repo bekend
zouden zijn:

```
SECRET_KEY=een-lange-willekeurige-tekenreeks
DB_PASSWORD=een-wachtwoord
ADMIN_WACHTWOORD=een-eerste-wachtwoord
```

```bash
docker compose up --build
```

Daarna `http://localhost:8000`, met gebruikersnaam `beheerder` (of wat u in
`ADMIN_GEBRUIKERSNAAM` zet) en het wachtwoord uit uw `.env`.

### Kubernetes

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl -n commoncontrol create secret generic commoncontrol-secret \
  --from-literal=SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(64))')" \
  --from-literal=DB_PASSWORD="$(python -c 'import secrets;print(secrets.token_urlsafe(24))')" \
  --from-literal=ADMIN_GEBRUIKERSNAAM=beheerder \
  --from-literal=ADMIN_WACHTWOORD='een-lang-eerste-wachtwoord'
kubectl apply -f k8s/20-database.yaml -f k8s/30-app.yaml
# pas de hostnaam aan in 40-ingress.yaml en in ALLOWED_HOSTS in 30-app.yaml
kubectl apply -f k8s/40-ingress.yaml
```

De ingress is een **standaard** Kubernetes-Ingress, geen Traefik-specifieke
IngressRoute — juist omdat het op elk platform moet werken.

### Beheerder herstellen

Het startscript draait `maak_beheerder` idempotent. Buitengesloten? Pas het
secret aan en herstart de pod, of:

```bash
kubectl -n commoncontrol exec deploy/commoncontrol -- \
  python manage.py maak_beheerder --gebruikersnaam beheerder --mfa-resetten
```

---

## Functioneel versus technisch beheer

CommonControl **beheert de inhoud** van de componenten (zaaktypen, abonnementen,
objecttypen, partijen) via hun publieke API's. Het installeren en technisch
onderhouden van de componenten zelf (cluster, back-ups, certificaten) valt hier
bewust buiten: dat is een aparte verantwoordelijkheid, en CommonControl heeft
daar geen afhankelijkheid van. Gebruik hiervoor bijvoorbeelde KubeManager https://kubemanager.nl

---

## Licentie

Licensed under the EUPL. Zie [LICENSE](LICENSE) voor de volledige tekst.
