# CommonControl

Webgebaseerde beheerinterface voor de CommonGround-componenten. Gebouwd door
**Madaro Services**.

CommonControl praat **uitsluitend via de publieke API's** van de componenten. Het
weet niets van Kubernetes, Helm of SSH. Daardoor maakt het niet uit waar de
componenten draaien — k3s, AKS, EKS, een virtuele machine of bij een
hostingpartij: alleen het adres en de inloggegevens tellen.

---

## Wat het beheert

De negen Maykin/ZGW-componenten uit de CommonGround-stack. OpenBeheer zit er
niet in.

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

Deze paden en authenticatievormen zijn **geverifieerd**, niet aangenomen: tegen
de OpenAPI-specificaties van de upstream-projecten en tegen de `api_root`-waarden
die deze componenten in de praktijk daadwerkelijk gebruiken.

### Eerlijke beperkingen

Twee componenten bieden zelf minder aan dan de rest. Dat is geen keuze van CG
Control, en het wordt in de interface ook zo getoond:

* **Open Inwoner** heeft maar een klein deel van zijn beheer als API: de
  producten- en dienstencatalogus. Gebruikersbeheer en portaalinhoud blijven in
  de eigen beheeromgeving.
* **Open Archiefbeheer** kent geen machine-credentials; zijn API is voor zijn
  eigen webinterface en werkt met een sessie-login. CommonControl logt daarom in
  met een serviceaccount. Vernietigingslijsten zijn hier **alleen te lezen** —
  beoordelen en vernietigen hoort in Open Archiefbeheer zelf te gebeuren, waar
  het vier-ogenprincipe is ingebouwd.

Verder is de formulierbouwer van Open Formulieren (velden slepen) bewust niet
nagebouwd; CommonControl beheert daar de formulieren, categorieën en koppelingen.

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
    │   │   ├── registry.py     ← DE BRON VAN WAARHEID: 9 componenten, 56 resources
    │   │   └── views.py        één generieke set views voor álle resources
    │   ├── verbindingen/
    │   │   ├── models.py       omgevingen en verbindingen (geheimen versleuteld)
    │   │   └── client.py       HTTP-client, ZGW-JWT, foutvertaling
    │   ├── toegang/            inloggen, TOTP-MFA, SSO, rechten per component
    │   └── auditlog/           wie deed wat, wanneer, met welk resultaat
    ├── templates/              inlog- en MFA-schermen
    ├── static/commoncontrol/       huisstijl (css) en de interface (app.js)
    └── tests/                  70 tests
```

### De registry is het hart

`src/commoncontrol/beheer/registry.py` beschrijft elk component en elke resource één
keer: pad, velden, veldtypen, filters, welke bewerkingen mogen. Zowel de API-laag
als de interface leiden daar álles uit af — er is geen enkele component-specifieke
view of pagina.

Eén registry per component, om dezelfde reden als bij vergelijkbare
CommonGround-tooling: negen componenten × 56 resources handmatig uitschrijven
zou gegarandeerd gaan schelen zodra er iets wijzigt.

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
  tweede factor is dan de verantwoordelijkheid van de provider. In te stellen en
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

> Voor Open Formulieren, Open Product en Open Inwoner maak je zelf een API-token
> aan in de beheeromgeving van dat component (onder *Auth Token → Tokens*). De
> interface wijst je daar naartoe.

**De verbindingstest gokt niet.** De Maykin-componenten gebruiken in de praktijk
`Authorization: Token <sleutel>`, terwijl de gegenereerde OpenAPI van Open Klant
een bearer-schema beschrijft. In plaats van te kiezen welke bron gelijk heeft,
probeert de test beide en slaat op wat werkelijk werkt.

### Aanbevolen: een eigen applicatie in OpenZaak

Je kunt bestaande credentials hergebruiken die al voor deze componenten zijn
aangemaakt (bijvoorbeeld via een eerder ingelezen configuratiebestand). Dat werkt
meteen, maar voor de herleidbaarheid is het beter om in *OpenZaak → Applicaties*
een eigen applicatie voor CommonControl aan te maken en die client-id/secret hier
in te vullen. In de auditlog van OpenZaak zelf staat dan bovendien welke
beheerder de handeling deed — CommonControl zet de ingelogde gebruiker in het
`user_id` van het JWT.

---

## Draaien

### Lokaal

```bash
docker compose up --build
```

Daarna `http://localhost:8000`, met de beheerder uit `docker-compose.yml`
(standaard `beheerder` / `eerste-wachtwoord-wijzigen` — direct wijzigen).

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

## Tests

```bash
cd src
python manage.py test tests --settings=commoncontrol.test_settings
```

70 tests, geen netwerk nodig. Ze dekken vooral wat duur is als het misgaat:

* versleuteling heen en weer, en dat een andere sleutel geen crash geeft;
* het ZGW-JWT — inclusief de `client_identifier` in de **header**, waar OpenZaak
  anders een nietszeggende 403 op geeft;
* rechten: sterkste van persoonlijk en groep, en geen toegang zonder recht;
* de toegangspoort: zonder tweede factor geen API en geen interface, een
  pogingenlimiet, uitloggen alleen via POST, en `?next=` alleen binnen de app;
* padopbouw: een identificatie met `../` erin kan het pad niet veranderen;
* de doorgeefluik-route weigert een URL buiten het component;
* het inlezen van een bestaand wizard-configuratiebestand, inclusief de
  gevallen zonder token;
* de integriteit van de registry zelf.

> Die laatste categorie bewees zichzelf meteen: de test op titelvelden vond dat
> Open Klant's organisatie-resource naar een veld `naam` wees dat de
> Contactgegevens-API niet heeft (het heet `handelsnaam`).

`manage.py check --deploy` laat bewust twee waarschuwingen staan:
`SECURE_HSTS_INCLUDE_SUBDOMAINS` en `SECURE_HSTS_PRELOAD`. CommonControl draait op
een subdomein van de gemeente en mag geen beleid opleggen aan het hele domein —
dat is een beslissing van de domeineigenaar, niet van deze applicatie.

**Python-versie**: Django 5.1 ondersteunt tot en met Python 3.13; de Dockerfile
pint 3.12. Draai je de tests op 3.14, dan schakelt `src/tests/__init__.py` een
kleine shim in voor een onverenigbaarheid in Django's *testclient* (niet in de
applicatie). Dat blok kan weg zodra de tests op een ondersteunde versie draaien.

---

## Wat nog niet tegen een echt cluster is getest

Alles hierboven is lokaal geverifieerd: 70 tests groen, `manage.py check` schoon,
de manifesten door een YAML-parser, `app.js` door `node --check`. Wat een echte
omgeving nog moet uitwijzen:

* de veldenlijsten per resource tegen een draaiende installatie — de paden en
  authenticatie zijn geverifieerd, maar of elk veld exact zo heet als hier
  beschreven blijkt pas bij het eerste echte aanmaken. De JSON-modus vangt
  afwijkingen op zonder dat er iets onbereikbaar wordt;
* de sessie-login bij Open Archiefbeheer (CSRF-afhandeling verschilt per opzet);
* het token-voorvoegsel van Open Klant — de test bepaalt dat zelf, maar het is
  nog niet tegen een echte instantie waargenomen;
* een volledige OIDC-ronde met een echte identity provider.

---

## Functioneel versus technisch beheer

CommonControl **beheert de inhoud** van de componenten (zaaktypen, abonnementen,
objecttypen, partijen) via hun publieke API's. Het installeren en technisch
onderhouden van de componenten zelf (cluster, back-ups, certificaten) valt hier
bewust buiten: dat is een aparte verantwoordelijkheid, en CommonControl heeft
daar geen afhankelijkheid van.

---

## Licentie

Licensed under the EUPL. Zie [LICENSE](LICENSE) voor de volledige tekst.
