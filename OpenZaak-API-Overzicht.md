# OpenZaak — overzicht van API's en functioneel-beheeracties

Live onderzocht tegen **openzaak.demomeer.nl**: de OpenAPI-specs van alle vijf API-groepen zijn rechtstreeks van die installatie opgehaald (`/<groep>/api/v1/openapi.json`) en hieronder volledig uitgewerkt.

---

## Catalogi API (versie 1.3.1 (1))


### `besluittypen` — ✅ in CommonControl

`/besluittypen`

- **Opvragen** — Alle BESLUITTYPEN opvragen
- **Aanmaken** — Maak een BESLUITTYPE aan

`/besluittypen/{uuid}`

- **Opvragen** — Een specifieke BESLUITTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een BESLUITTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een BESLUITTYPE deels bij
- **Verwijderen** — Verwijder een BESLUITTYPE

`/besluittypen/{uuid}/publish`

- **Aanmaken** — Publiceer het concept BESLUITTYPE


### `catalogussen` — ✅ in CommonControl

`/catalogussen`

- **Opvragen** — Alle catalogi opvragen
- **Aanmaken** — Maak een CATALOGUS aan

`/catalogussen/{uuid}`

- **Opvragen** — Een specifieke CATALOGUS opvragen


### `eigenschappen` — ✅ in CommonControl

`/eigenschappen`

- **Opvragen** — Alle eigenschappen opvragen
- **Aanmaken** — Maak een EIGENSCHAP aan

`/eigenschappen/{uuid}`

- **Opvragen** — Een specifieke EIGENSCHAP opvragen
- **Vervangen (volledig bijwerken)** — Werk een EIGENSCHAP in zijn geheel bij
- **Deels bijwerken** — Werk een EIGENSCHAP deels bij
- **Verwijderen** — Verwijder een EIGENSCHAP


### `informatieobjecttypen` — ✅ in CommonControl

`/informatieobjecttypen`

- **Opvragen** — Alle informatieobjecttypen opvragen
- **Aanmaken** — Maak een INFORMATIEOBJECTTYPE aan

`/informatieobjecttypen/{uuid}`

- **Opvragen** — Een specifieke INFORMATIEOBJECTTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een INFORMATIEOBJECTTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een INFORMATIEOBJECTTYPE deels bij
- **Verwijderen** — Verwijder een INFORMATIEOBJECTTYPE

`/informatieobjecttypen/{uuid}/publish`

- **Aanmaken** — Publiceer het concept INFORMATIEOBJECTTYPE


### `resultaattypen` — ✅ in CommonControl

`/resultaattypen`

- **Opvragen** — Alle resultaattypen opvragen
- **Aanmaken** — Maak een RESULTAATTYPE aan

`/resultaattypen/{uuid}`

- **Opvragen** — Een specifieke RESULTAATTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een RESULTAATTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een RESULTAATTYPE deels bij
- **Verwijderen** — Verwijder een RESULTAATTYPE


### `roltypen` — ✅ in CommonControl

`/roltypen`

- **Opvragen** — Alle ROLTYPEN opvragen
- **Aanmaken** — Maak een ROLTYPE aan

`/roltypen/{uuid}`

- **Opvragen** — Een specifieke ROLTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een ROLTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een ROLTYPE deels bij
- **Verwijderen** — Verwijder een ROLTYPE


### `statustypen` — ✅ in CommonControl

`/statustypen`

- **Opvragen** — Alle STATUSTYPEN opvragen
- **Aanmaken** — Maak een STATUSTYPE aan

`/statustypen/{uuid}`

- **Opvragen** — Een specifieke STATUSTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een STATUSTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een STATUSTYPE deels bij
- **Verwijderen** — Verwijder een STATUSTYPE


### `zaakobjecttypen` — ✅ in CommonControl

`/zaakobjecttypen`

- **Opvragen** — Alle ZAAKOBJECTTYPEN opvragen
- **Aanmaken** — Maak een ZAAKOBJECTTYPE aan

`/zaakobjecttypen/{uuid}`

- **Opvragen** — Een specifieke ZAAKOBJECTTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKOBJECTTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKOBJECTTYPE deels bij
- **Verwijderen** — Verwijder een ZAAKOBJECTTYPE


### `zaaktype-informatieobjecttypen` — ✅ in CommonControl

`/zaaktype-informatieobjecttypen`

- **Opvragen** — Alle ZAAKTYPE-INFORMATIEOBJECTTYPE relaties opvragen
- **Aanmaken** — Maak een ZAAKTYPE-INFORMATIEOBJECTTYPE relatie aan

`/zaaktype-informatieobjecttypen/{uuid}`

- **Opvragen** — Een specifieke ZAAKTYPE-INFORMATIEOBJECTTYPE relatie opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKTYPE-INFORMATIEOBJECTTYPE relatie in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKTYPE-INFORMATIEOBJECTTYPE relatie deels bij
- **Verwijderen** — Verwijder een ZAAKTYPE-INFORMATIEOBJECTTYPE relatie


### `zaaktypen` — ✅ in CommonControl

`/zaaktypen`

- **Opvragen** — Alle ZAAKTYPEN opvragen
- **Aanmaken** — Maak een ZAAKTYPE aan

`/zaaktypen/{uuid}`

- **Opvragen** — Een specifieke ZAAKTYPE opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKTYPE in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKTYPE deels bij
- **Verwijderen** — Verwijder een ZAAKTYPE

`/zaaktypen/{uuid}/publish`

- **Aanmaken** — Publiceer het concept ZAAKTYPE


---

## Zaken API (versie 1.5.1 (1))


### `klantcontacten` — ✅ in CommonControl

`/klantcontacten`

- **Opvragen** — Alle KLANTCONTACTEN opvragen
- **Aanmaken** — Maak een KLANTCONTACT bij een ZAAK aan

`/klantcontacten/{uuid}`

- **Opvragen** — Een specifiek KLANTCONTACT bij een ZAAK opvragen


### `reserveer_zaaknummer` — ✅ in CommonControl

`/reserveer_zaaknummer`

- **Aanmaken** — Reserveer een zaaknummer


### `resultaten` — ✅ in CommonControl

`/resultaten`

- **Opvragen** — Alle RESULTATEN van ZAKEN opvragen
- **Aanmaken** — Maak een RESULTAAT bij een ZAAK aan

`/resultaten/{uuid}`

- **Opvragen** — Een specifiek RESULTAAT opvragen
- **Vervangen (volledig bijwerken)** — Werk een RESULTAAT in zijn geheel bij
- **Deels bijwerken** — Werk een RESULTAAT deels bij
- **Verwijderen** — Verwijder een RESULTAAT van een ZAAK


### `rollen` — ✅ in CommonControl

`/rollen`

- **Opvragen** — Alle ROLLEN bij ZAKEN opvragen
- **Aanmaken** — Maak een ROL aan bij een ZAAK

`/rollen/{uuid}`

- **Opvragen** — Een specifieke ROL bij een ZAAK opvragen
- **Vervangen (volledig bijwerken)** — Werk een ROL aan bij een ZAAK
- **Verwijderen** — Verwijder een ROL van een ZAAK


### `statussen` — ✅ in CommonControl

`/statussen`

- **Opvragen** — Alle STATUSSEN van ZAKEN opvragen
- **Aanmaken** — Maak een STATUS aan voor een ZAAK

`/statussen/{uuid}`

- **Opvragen** — Een specifieke STATUS van een ZAAK opvragen


### `substatussen` — ✅ in CommonControl

`/substatussen`

- **Opvragen** — Alle SUBSTATUSSEN van STATUSSEN opvragen
- **Aanmaken** — Maak een SUBSTATUS aan bij een STATUS voor een ZAAK

`/substatussen/{uuid}`

- **Opvragen** — Een specifieke SUBSTATUS bij een STATUS van een ZAAK opvragen


### `zaak_afsluiten` — ✅ in CommonControl

`/zaak_afsluiten/{uuid}`

- **Aanmaken** — Sluit een zaak


### `zaak_bijwerken` — ✅ in CommonControl

`/zaak_bijwerken/{uuid}`

- **Aanmaken** — Update een zaak


### `zaak_opschorten` — ✅ in CommonControl

`/zaak_opschorten/{uuid}`

- **Aanmaken** — Schort een zaak op


### `zaak_registreren` — ✅ in CommonControl

`/zaak_registreren`

- **Aanmaken** — Registreer een zaak


### `zaak_verlengen` — ✅ in CommonControl

`/zaak_verlengen/{uuid}`

- **Aanmaken** — Verleng een zaak


### `zaakcontactmomenten` — ✅ in CommonControl

`/zaakcontactmomenten`

- **Opvragen** — Alle ZAAKCONTACTMOMENTEN opvragen
- **Aanmaken** — Maak een ZAAKCONTACTMOMENT aan

`/zaakcontactmomenten/{uuid}`

- **Opvragen** — Een specifiek ZAAKCONTACTMOMENT opvragen
- **Verwijderen** — Verwijder een ZAAKCONTACTMOMENT


### `zaakinformatieobjecten` — ✅ in CommonControl

`/zaakinformatieobjecten`

- **Opvragen** — Alle ZAAK-INFORMATIEOBJECT relaties opvragen
- **Aanmaken** — Maak een ZAAK-INFORMATIEOBJECT relatie aan

`/zaakinformatieobjecten/{uuid}`

- **Opvragen** — Een specifieke ZAAK-INFORMATIEOBJECT relatie opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAK-INFORMATIEOBJECT relatie in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAK-INFORMATIEOBJECT relatie in deels bij
- **Verwijderen** — Verwijder een ZAAK-INFORMATIEOBJECT relatie


### `zaaknotities` — ✅ in CommonControl

`/zaaknotities`

- **Opvragen** — Alle ZAAKNOTITIES opvragen
- **Aanmaken** — Maak een ZAAKNOTITIE aan

`/zaaknotities/{uuid}`

- **Opvragen** — Een specifieke ZAAKNOTITIE opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKNOTITIE in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKNOTITIE deels bij
- **Verwijderen** — Verwijder een ZAAKNOTITIE


### `zaaknummer_reserveren` — ❌ nog niet in CommonControl

`/zaaknummer_reserveren`

- **Aanmaken** — Reserveer een zaaknummer


### `zaakobjecten` — ✅ in CommonControl

`/zaakobjecten`

- **Opvragen** — Alle ZAAKOBJECTEN opvragen
- **Aanmaken** — Maak een ZAAKOBJECT aan

`/zaakobjecten/{uuid}`

- **Opvragen** — Een specifiek ZAAKOBJECT opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKOBJECT in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKOBJECT deels bij
- **Verwijderen** — Verwijder een ZAAKOBJECT


### `zaakverzoeken` — ✅ in CommonControl

`/zaakverzoeken`

- **Opvragen** — Alle ZAAK-VERZOEKEN opvragen
- **Aanmaken** — Maak een ZAAK-VERZOEK aan

`/zaakverzoeken/{uuid}`

- **Opvragen** — Een specifiek ZAAK-VERZOEK opvragen
- **Verwijderen** — Verwijder een ZAAK-VERZOEK


### `zaken` — ✅ in CommonControl

`/zaken`

- **Opvragen** — Alle ZAKEN opvragen
- **Aanmaken** — Maak een ZAAK aan

`/zaken/_zoek`

- **Aanmaken** — Voer een (geo)-zoekopdracht uit op ZAKEN

`/zaken/{uuid}`

- **Opvragen** — Een specifieke ZAAK opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAK in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAK deels bij
- **Verwijderen** — Verwijder een ZAAK

`/zaken/{zaak_uuid}/audittrail`

- **Opvragen** — Alle audit trail regels behorend bij de ZAAK

`/zaken/{zaak_uuid}/audittrail/{uuid}`

- **Opvragen** — Een specifieke audit trail regel opvragen

`/zaken/{zaak_uuid}/besluiten`

- **Opvragen** — Alle ZAAKBESLUITEN opvragen
- **Aanmaken** — Maak een ZAAKBESLUIT aan

`/zaken/{zaak_uuid}/besluiten/{uuid}`

- **Opvragen** — Een specifiek ZAAKBESLUIT opvragen
- **Verwijderen** — Verwijder een ZAAKBESLUIT

`/zaken/{zaak_uuid}/zaakeigenschappen`

- **Opvragen** — Alle ZAAKEIGENSCHAPPEN opvragen
- **Aanmaken** — Maak een ZAAKEIGENSCHAP aan

`/zaken/{zaak_uuid}/zaakeigenschappen/{uuid}`

- **Opvragen** — Een specifieke ZAAKEIGENSCHAP opvragen
- **Vervangen (volledig bijwerken)** — Werk een ZAAKEIGENSCHAP in zijn geheel bij
- **Deels bijwerken** — Werk een ZAAKEIGENSCHAP deels bij
- **Verwijderen** — Verwijder een ZAAKEIGENSCHAP


---

## Documenten API (versie 1.4.2 (1))


### `bestandsdelen` — ❌ nog niet in CommonControl

`/bestandsdelen/{uuid}`

- **Vervangen (volledig bijwerken)** — Upload een bestandsdeel


### `document_registreren` — ✅ in CommonControl

`/document_registreren`

- **Aanmaken** — Registreer een document


### `documentnummer_reserveren` — ✅ in CommonControl

`/documentnummer_reserveren`

- **Aanmaken** — Reserveer een documentnummer


### `enkelvoudiginformatieobjecten` — ✅ in CommonControl

`/enkelvoudiginformatieobjecten`

- **Opvragen** — Alle (ENKELVOUDIGE) INFORMATIEOBJECTEN opvragen
- **Aanmaken** — Maak een (ENKELVOUDIG) INFORMATIEOBJECT aan

`/enkelvoudiginformatieobjecten/_zoek`

- **Aanmaken** — Voer een zoekopdracht uit op (ENKELVOUDIG) INFORMATIEOBJECTEN

`/enkelvoudiginformatieobjecten/{enkelvoudiginformatieobject_uuid}/audittrail`

- **Opvragen** — Alle audit trail regels behorend bij het INFORMATIEOBJECT

`/enkelvoudiginformatieobjecten/{enkelvoudiginformatieobject_uuid}/audittrail/{uuid}`

- **Opvragen** — Een specifieke audit trail regel opvragen

`/enkelvoudiginformatieobjecten/{uuid}`

- **Opvragen** — Een specifiek (ENKELVOUDIG) INFORMATIEOBJECT opvragen
- **Vervangen (volledig bijwerken)** — Werk een (ENKELVOUDIG) INFORMATIEOBJECT in zijn geheel bij
- **Deels bijwerken** — Werk een (ENKELVOUDIG) INFORMATIEOBJECT deels bij
- **Verwijderen** — Verwijder een (ENKELVOUDIG) INFORMATIEOBJECT

`/enkelvoudiginformatieobjecten/{uuid}/download`

- **Opvragen** — Download de binaire data van het (ENKELVOUDIG) INFORMATIEOBJECT

`/enkelvoudiginformatieobjecten/{uuid}/lock`

- **Aanmaken** — Vergrendel een (ENKELVOUDIG) INFORMATIEOBJECT

`/enkelvoudiginformatieobjecten/{uuid}/unlock`

- **Aanmaken** — Ontgrendel een (ENKELVOUDIG) INFORMATIEOBJECT


### `gebruiksrechten` — ✅ in CommonControl

`/gebruiksrechten`

- **Opvragen** — Alle GEBRUIKSRECHTEN opvragen
- **Aanmaken** — Maak een GEBRUIKSRECHT aan

`/gebruiksrechten/{uuid}`

- **Opvragen** — Een specifieke GEBRUIKSRECHT opvragen
- **Vervangen (volledig bijwerken)** — Werk een GEBRUIKSRECHT in zijn geheel bij
- **Deels bijwerken** — Werk een GEBRUIKSRECHT relatie deels bij
- **Verwijderen** — Verwijder een GEBRUIKSRECHT


### `import` — ❌ nog niet in CommonControl

`/import/create`

- **Aanmaken** — Een IMPORT maken

`/import/{uuid}/delete`

- **Verwijderen** — Een IMPORT verwijderen

`/import/{uuid}/report`

- **Opvragen** — Het reportage bestand van een IMPORT downloaden

`/import/{uuid}/status`

- **Opvragen** — De status van een IMPORT opvragen

`/import/{uuid}/upload`

- **Aanmaken** — Een IMPORT bestand uploaden


### `objectinformatieobjecten` — ✅ in CommonControl

`/objectinformatieobjecten`

- **Opvragen** — Alle OBJECT-INFORMATIEOBJECT relaties opvragen
- **Aanmaken** — Maak een OBJECT-INFORMATIEOBJECT relatie aan

`/objectinformatieobjecten/{uuid}`

- **Opvragen** — Een specifieke OBJECT-INFORMATIEOBJECT relatie opvragen
- **Verwijderen** — Verwijder een OBJECT-INFORMATIEOBJECT relatie


### `verzendingen` — ✅ in CommonControl

`/verzendingen`

- **Opvragen** — Alle VERZENDINGEN opvragen
- **Aanmaken** — Maak een VERZENDING aan

`/verzendingen/{uuid}`

- **Opvragen** — Een specifieke VERZENDING opvragen
- **Vervangen (volledig bijwerken)** — Werk een VERZENDING in zijn geheel bij
- **Deels bijwerken** — Werk een VERZENDING relatie deels bij
- **Verwijderen** — Verwijder een VERZENDING


---

## Besluiten API (versie 1.1.0 (1))


### `besluit_verwerken` — ✅ in CommonControl

`/besluit_verwerken`

- **Aanmaken** — Verwerk een besluit


### `besluiten` — ✅ in CommonControl

`/besluiten`

- **Opvragen** — Alle BESLUITEN opvragen
- **Aanmaken** — Maak een BESLUIT aan

`/besluiten/{besluit_uuid}/audittrail`

- **Opvragen** — Alle audit trail regels behorend bij het BESLUIT

`/besluiten/{besluit_uuid}/audittrail/{uuid}`

- **Opvragen** — Een specifieke audit trail regel opvragen

`/besluiten/{uuid}`

- **Opvragen** — Een specifiek BESLUIT opvragen
- **Vervangen (volledig bijwerken)** — Werk een BESLUIT in zijn geheel bij
- **Deels bijwerken** — Werk een BESLUIT deels bij
- **Verwijderen** — Verwijder een BESLUIT


### `besluitinformatieobjecten` — ✅ in CommonControl

`/besluitinformatieobjecten`

- **Opvragen** — Alle BESLUIT-INFORMATIEOBJECT relaties opvragen
- **Aanmaken** — Maak een BESLUIT-INFORMATIEOBJECT relatie aan

`/besluitinformatieobjecten/{uuid}`

- **Opvragen** — Een specifieke BESLUIT-INFORMATIEOBJECT relatie opvragen
- **Verwijderen** — Verwijder een BESLUIT-INFORMATIEOBJECT relatie


---

## Autorisaties API (versie 1.0.0 (1))


### `applicaties` — ✅ in CommonControl

`/applicaties`

- **Opvragen** — Geef een collectie van applicaties, met ingesloten autorisaties
- **Aanmaken** — Registreer een applicatie met een bepaalde set van autorisaties

`/applicaties/consumer`

- **Opvragen** — Vraag een applicatie op, op basis van clientId

`/applicaties/{uuid}`

- **Opvragen** — Vraag een applicatie op, met ingesloten autorisaties
- **Vervangen (volledig bijwerken)** — Werk de applicatie bij
- **Deels bijwerken** — Werk (een deel van) de applicatie bij
- **Verwijderen** — Verwijder een applicatie met de bijhorende autorisaties


---

