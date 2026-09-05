# Open Notificaties — overzicht van API's en functioneel-beheeracties

Live onderzocht tegen **notificaties.demomeer.nl** (niet aangenomen): de OpenAPI-spec is rechtstreeks van die installatie opgehaald (`/api/v1/openapi.json`).

## Is er meer dan de ene zichtbare API?

**Nee.** Open Notificaties' API-dashboard linkt naar precies één API-groep: `/api/v1/`. Geen aparte groepen zoals bij OpenZaak — Open Notificaties is een eenvoudiger, op zichzelf staand component (kanalen, abonnementen en het publiceren van notificaties).


---

## Notificaties API (versie 1.0.0 (1))


### `abonnement` — ✅ in CommonControl

`/abonnement`

- **Opvragen** — Alle ABONNEMENTen opvragen
- **Aanmaken** — Maak een ABONNEMENT aan

`/abonnement/{uuid}`

- **Opvragen** — Een specifieke ABONNEMENT opvragen
- **Vervangen (volledig bijwerken)** — Werk een ABONNEMENT in zijn geheel bij
- **Deels bijwerken** — Werk een ABONNEMENT deels bij
- **Verwijderen** — Verwijder een ABONNEMENT


### `cloudevents` — ❌ nog niet in CommonControl

`/cloudevents`

- **Aanmaken** — **EXPERIMENTEEL** Publiceer een cloud event


### `kanaal` — ✅ in CommonControl

`/kanaal`

- **Opvragen** — Alle KANAALen opvragen
- **Aanmaken** — Maak een KANAAL aan

`/kanaal/{uuid}`

- **Opvragen** — Een specifiek KANAAL opvragen
- **Vervangen (volledig bijwerken)** — **EXPERIMENTEEL** Een specifiek KANAAL bewerken
- **Deels bijwerken** — **EXPERIMENTEEL** Een specifiek KANAAL deels bewerken


### `notificaties` — ✅ in CommonControl

`/notificaties`

- **Aanmaken** — Publiceer een notificatie


---

## Samenvatting

- **Totaal aantal functionele acties gevonden**: 13
- **Daarvan beschikbaar in CommonControl**: 12
- **Bewust niet gebouwd**: 1

| Endpoint | Waarom niet |
|---|---|
| `/cloudevents` | Door Open Notificaties zelf als **EXPERIMENTEEL** gemarkeerd, en gebruikt een ander content-type (`application/cloudevents+json` i.p.v. `application/json`) — CommonControl's HTTP-client stuurt altijd JSON. Zou een eigen contenttype-pad in de client vereisen voor één experimentele endpoint. |

`/notificaties` (een notificatie publiceren) is toegevoegd als een aanmaak-only resource, net als bij OpenZaak's vendor-acties — met dit verschil dat dit hier de kernfunctie van de API zelf is, geen vendor-uitbreiding. Bruikbaar om een abonnee-koppeling te testen zonder een echte gebeurtenis in OpenZaak te hoeven veroorzaken.