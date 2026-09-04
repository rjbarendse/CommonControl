/* ═══════════════════════════════════════════════════════════════════
   CommonControl — interface

   Bewust zonder framework en zonder bouwstap, net als KubeManager: één
   bestand dat je kunt lezen en dat het zonder netwerk naar een CDN doet.

   Alles wat je op het scherm ziet komt uit de registry die de server
   levert. Een nieuwe resource in de registry verschijnt hier vanzelf,
   met lijst, formulier en validatie — zonder dat hier iets verandert.
   ═══════════════════════════════════════════════════════════════════ */
'use strict';

// ── Kleine hulpjes ─────────────────────────────────────────────────────────

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function h(tag, attrs, ...kinderen) {
  const el = document.createElement(tag);
  for (const [sleutel, waarde] of Object.entries(attrs || {})) {
    if (waarde === null || waarde === undefined || waarde === false) continue;
    // Bewust geen 'html'-optie: alles gaat via createTextNode, zodat er geen
    // enkele plek is waar tekst van een component als HTML kan eindigen.
    if (sleutel === 'class') el.className = waarde;
    else if (sleutel.startsWith('on') && typeof waarde === 'function') {
      el.addEventListener(sleutel.slice(2), waarde);
    } else if (sleutel === 'dataset') Object.assign(el.dataset, waarde);
    else el.setAttribute(sleutel, waarde === true ? '' : waarde);
  }
  for (const kind of kinderen.flat()) {
    if (kind === null || kind === undefined || kind === false) continue;
    el.append(kind instanceof Node ? kind : document.createTextNode(String(kind)));
  }
  return el;
}

function leeg(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

function cookie(naam) {
  const treffer = document.cookie.match(new RegExp('(^|;\\s*)' + naam + '=([^;]*)'));
  return treffer ? decodeURIComponent(treffer[2]) : '';
}

function toast(tekst, soort = 'info') {
  const el = h('div', { class: `toast ${soort}` }, tekst);
  $('#toasts').append(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 250);
  }, soort === 'error' ? 8000 : 4000);
}

/** Eén plek voor alle serveraanroepen: CSRF, foutafhandeling en JSON. */
async function api(pad, opties = {}) {
  const config = {
    method: opties.method || 'GET',
    headers: { 'Accept': 'application/json' },
    credentials: 'same-origin',
  };
  if (opties.body !== undefined) {
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(opties.body);
  }
  if (config.method !== 'GET') config.headers['X-CSRFToken'] = cookie('csrftoken');

  let antwoord;
  try {
    antwoord = await fetch(pad, config);
  } catch (err) {
    throw Object.assign(new Error('Geen verbinding met de server: ' + err.message), { netwerk: true });
  }

  if (antwoord.status === 401) {
    // Sessie verlopen of tweede factor nog niet voltooid: terug naar inloggen.
    window.location.href = '/inloggen/?next=' + encodeURIComponent(window.location.pathname + window.location.hash);
    throw new Error('Niet ingelogd.');
  }

  let inhoud = null;
  try { inhoud = await antwoord.json(); } catch { /* leeg antwoord */ }

  if (!antwoord.ok || (inhoud && inhoud.ok === false)) {
    const melding = (inhoud && inhoud.fout) || `De server gaf HTTP ${antwoord.status}.`;
    throw Object.assign(new Error(melding), {
      status: antwoord.status,
      velden: (inhoud && inhoud.velden) || {},
      body: inhoud && inhoud.body,
    });
  }
  return inhoud ? inhoud.data : null;
}

// ── Toestand ───────────────────────────────────────────────────────────────

const staat = {
  componenten: [],
  // Welke componentblokken in de zijbalk uitgeklapt staan. Zonder dit gaat die
  // keuze verloren bij elke hertekening, waardoor het menu onder je muis
  // verspringt.
  openComponenten: new Set(),
  perSleutel: {},
  omgevingen: [],
  omgeving: null,       // slug
  gebruiker: null,
  route: null,
};

const OPSLAG_OMGEVING = 'commoncontrol.omgeving';

function component(sleutel) { return staat.perSleutel[sleutel]; }

function resourceVan(componentSleutel, resourceSleutel) {
  const comp = component(componentSleutel);
  return comp ? comp.resources.find((r) => r.key === resourceSleutel) : null;
}

// ── Waardeweergave ─────────────────────────────────────────────────────────

function toonWaarde(waarde, veld) {
  if (waarde === null || waarde === undefined || waarde === '') return '—';
  if (typeof waarde === 'boolean') return waarde ? 'ja' : 'nee';
  if (Array.isArray(waarde)) return waarde.length ? `${waarde.length} item(s)` : '—';
  if (typeof waarde === 'object') return '{…}';
  const tekst = String(waarde);
  if (veld && veld.type === 'datumtijd' && tekst.includes('T')) {
    const datum = new Date(tekst);
    if (!isNaN(datum)) return datum.toLocaleString('nl-NL', { dateStyle: 'short', timeStyle: 'short' });
  }
  // Een ZGW-URL is voor een mens onleesbaar lang; het laatste stuk (de uuid)
  // zegt genoeg, en de volledige waarde staat in de tooltip.
  if (veld && veld.type === 'url' && tekst.startsWith('http')) {
    const delen = tekst.replace(/\/$/, '').split('/');
    return '…/' + delen[delen.length - 1];
  }
  return tekst;
}

function haalId(rij, resource) {
  if (!rij) return '';
  const kandidaten = [resource.idVeld, 'uuid', 'id', 'pk', 'slug'];
  for (const naam of kandidaten) {
    if (naam && rij[naam] !== undefined && rij[naam] !== null && rij[naam] !== '') {
      return String(rij[naam]);
    }
  }
  if (typeof rij.url === 'string') {
    const delen = rij.url.replace(/\/$/, '').split('/');
    return delen[delen.length - 1];
  }
  return '';
}

// ── Modals ─────────────────────────────────────────────────────────────────

function modal({ titel, inhoud, knoppen, breed }) {
  const houder = $('#modaal');
  const sluit = () => leeg(houder);

  const venster = h('div', { class: 'modal' + (breed ? '' : ' modal-sm') },
    h('div', { class: 'modal-header' },
      h('h3', {}, titel),
      h('button', { class: 'modal-close', 'aria-label': 'Sluiten', onclick: sluit }, '×')),
    h('div', { class: 'modal-body' }, inhoud),
    h('div', { class: 'modal-footer' },
      ...(knoppen || []).map((knop) =>
        h('button', {
          class: 'btn ' + (knop.soort || 'btn-secondary'),
          onclick: () => knop.actie ? knop.actie(sluit) : sluit(),
        }, knop.label)))
  );

  const achtergrond = h('div', {
    class: 'modal-backdrop',
    onclick: (e) => { if (e.target === achtergrond) sluit(); },
  }, venster);

  leeg(houder).append(achtergrond);
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { sluit(); document.removeEventListener('keydown', esc); }
  });
  const eerste = venster.querySelector('input, select, textarea');
  if (eerste) eerste.focus();
  return sluit;
}

function bevestig(titel, tekst, opActie, { gevaarlijk = true, knopLabel = 'Verwijderen' } = {}) {
  modal({
    titel,
    inhoud: h('div', {}, h('div', { class: 'info-block ' + (gevaarlijk ? 'danger' : 'warn') }, tekst)),
    knoppen: [
      { label: 'Annuleren' },
      {
        label: knopLabel,
        soort: gevaarlijk ? 'btn-danger' : 'btn-primary',
        actie: (sluit) => { sluit(); opActie(); },
      },
    ],
  });
}

// ── Navigatie ──────────────────────────────────────────────────────────────

const INSTELLINGEN = [
  // Configuratie staat vooraan: het is het instapscherm van een nieuwe omgeving.
  // Verbindingen bevat inloggegevens en is daarom beheerder-only, net als de
  // gebruikers- en SSO-schermen. De auditlog blijft voor iedereen zichtbaar —
  // die toont een gewone gebruiker alleen zijn eigen handelingen.
  { key: 'configuratie', label: 'Configuratie', beheerder: true },
  { key: 'verbindingen', label: 'Verbindingen', beheerder: true },
  { key: 'gebruikers', label: 'Gebruikers en rechten', beheerder: true },
  { key: 'sso', label: 'Single Sign On', beheerder: true },
  { key: 'auditlog', label: 'Auditlog', beheerder: false },
];

function tekenZijbalk() {
  const zijbalkEl = $('#zijbalk');
  // De zijbalk scrollt zelf. leeg() zet scrollTop op 0, dus zonder dit springt
  // het menu bij elke navigatie terug naar boven.
  const scrollPositie = zijbalkEl.scrollTop;
  const zijbalk = leeg(zijbalkEl);

  zijbalk.append(
    h('div', { class: 'nav-kop' }, 'Overzicht'),
    h('button', {
      class: 'nav-item' + (staat.route && staat.route.soort === 'overzicht' ? ' actief' : ''),
      onclick: () => (window.location.hash = '#/overzicht'),
    }, '▦ Dashboard'),
    h('div', { class: 'nav-kop' }, 'Componenten')
  );

  if (!staat.componenten.length) {
    zijbalk.append(h('p', { class: 'hint', style: 'padding:8px 16px' },
      'Je hebt nog geen toegang tot componenten. Vraag een beheerder om rechten.'));
  }

  for (const comp of staat.componenten) {
    const actief = staat.route && staat.route.component === comp.key;
    // Het component waar je nu in werkt hoort open te staan; wat je zelf hebt
    // uitgeklapt blijft dat ook.
    if (actief) staat.openComponenten.add(comp.key);
    const staatOpen = actief || staat.openComponenten.has(comp.key);
    const verbonden = comp.verbinding && comp.verbinding.laatsteTestOk;
    const ingesteld = comp.verbinding && comp.verbinding.ingevuld;
    // Een component telt als "in gebruik" zodra er een actieve verbinding voor
    // is. Wat niet in gebruik is blijft zichtbaar maar grijs: dan zie je wat er
    // nog te kiezen valt, in plaats van dat het menu stilletjes korter wordt.
    const inGebruik = !!(comp.verbinding && comp.verbinding.actief);

    const blok = h('div', {
      class: 'nav-comp' + (staatOpen && inGebruik ? ' open' : '') + (inGebruik ? '' : ' uit'),
    });
    blok.append(h('button', {
      class: 'nav-comp-knop',
      onclick: () => {
        if (!inGebruik) {
          toast(staat.gebruiker.beheerder
            ? `${comp.label} staat uit. Zet het aan onder Instellingen → Configuratie.`
            : `${comp.label} is niet in gebruik. Vraag een beheerder om het aan te zetten.`,
          'info');
          return;
        }
        const nuOpen = blok.classList.toggle('open');
        if (nuOpen) staat.openComponenten.add(comp.key);
        else staat.openComponenten.delete(comp.key);
      },
      title: inGebruik ? comp.beschrijving : `${comp.label} is niet in gebruik`,
    },
      h('span', {
        class: 'status-dot ' + (!inGebruik ? 'onbekend'
          : verbonden ? '' : ingesteld ? 'onbekend' : 'off'),
        title: !inGebruik ? 'Niet in gebruik'
          : verbonden ? 'Verbinding getest en werkend'
            : ingesteld ? 'Ingesteld, nog niet getest'
              : 'Nog geen verbinding ingesteld',
      }),
      comp.label,
      h('span', { class: 'telling' }, !inGebruik ? 'uit'
        : comp.niveau === 'schrijven' ? '' : 'lezen')
    ));

    const sub = h('div', { class: 'nav-sub' });
    let vorigeApi = null;
    for (const resource of comp.resources) {
      if (comp.apis.length > 1 && resource.api !== vorigeApi) {
        vorigeApi = resource.api;
        const groep = comp.apis.find((a) => a.key === resource.api);
        sub.append(h('div', { class: 'nav-groepkop' }, groep ? groep.label : resource.api));
      }
      // Geneste resources (zoals objecttypeversies) worden vanuit hun ouder
      // geopend; ze los in het menu zetten zou een halve pagina opleveren.
      if (resource.ouder) continue;
      const isActief = staat.route && staat.route.component === comp.key
        && staat.route.resource === resource.key;
      sub.append(h('button', {
        class: 'nav-item' + (isActief ? ' actief' : ''),
        onclick: () => (window.location.hash = `#/c/${comp.key}/${resource.key}`),
      }, resource.labelMv));
    }
    blok.append(sub);
    zijbalk.append(blok);
  }

  zijbalk.append(h('div', { class: 'nav-kop' }, 'Instellingen'));
  for (const item of INSTELLINGEN) {
    if (item.beheerder && !staat.gebruiker.beheerder) continue;
    const isActief = staat.route && staat.route.soort === 'instellingen' && staat.route.pagina === item.key;
    zijbalk.append(h('button', {
      class: 'nav-item' + (isActief ? ' actief' : ''),
      onclick: () => (window.location.hash = `#/instellingen/${item.key}`),
    }, item.label));
  }

  zijbalkEl.scrollTop = scrollPositie;
}

// ── Router ─────────────────────────────────────────────────────────────────

function leesRoute() {
  const hash = window.location.hash.replace(/^#\/?/, '');
  const delen = hash.split('/').filter(Boolean);
  if (!delen.length || delen[0] === 'overzicht') return { soort: 'overzicht' };
  if (delen[0] === 'instellingen') return { soort: 'instellingen', pagina: delen[1] || 'verbindingen' };
  if (delen[0] === 'c' && delen[1]) {
    return {
      soort: 'resource',
      component: delen[1],
      resource: delen[2] || null,
      ouder: delen[3] || null,
    };
  }
  return { soort: 'overzicht' };
}

let _vorigeRoute = null;

async function routeer() {
  staat.route = leesRoute();

  // Ook het hoofdvenster scrollt zelf. Bij écht navigeren wil je bovenaan
  // beginnen, maar bij een verversing van dezelfde pagina (opslaan, een
  // verbinding testen, een filter zetten) is terugspringen naar boven hinderlijk
  // — dan verlies je de plek waar je net stond.
  const routeSleutel = window.location.hash || '#/overzicht';
  const zelfdePagina = routeSleutel === _vorigeRoute;
  const hoofdEl = $('#hoofd');
  const scrollPositie = zelfdePagina ? hoofdEl.scrollTop : 0;
  _vorigeRoute = routeSleutel;

  tekenZijbalk();
  const hoofd = leeg(hoofdEl);
  hoofd.append(h('p', { class: 'hint' }, h('span', { class: 'spin' }, '◐'), ' Laden…'));

  try {
    if (staat.route.soort === 'overzicht') await toonOverzicht();
    else if (staat.route.soort === 'instellingen') await toonInstellingen(staat.route.pagina);
    else await toonResource(staat.route);
  } catch (err) {
    leeg(hoofd).append(
      h('div', { class: 'info-block danger' },
        h('strong', {}, 'Er ging iets mis. '), err.message)
    );
  }

  hoofdEl.scrollTop = scrollPositie;
}

// ── Overzicht ──────────────────────────────────────────────────────────────

async function toonOverzicht() {
  const hoofd = leeg($('#hoofd'));

  // Alleen wat onder Configuratie is aangevinkt telt mee; de rest hoort niet
  // als 'nog te doen' of als storing op het dashboard te staan.
  const inGebruik = staat.componenten.filter((c) => c.verbinding && c.verbinding.actief);
  const metVerbinding = inGebruik.filter((c) => c.verbinding.ingevuld);
  const werkend = metVerbinding.filter((c) => c.verbinding.laatsteTestOk === true);
  const mislukt = metVerbinding.filter((c) => c.verbinding.laatsteTestOk === false);

  hoofd.append(
    h('div', { class: 'toolbar' },
      h('h2', {}, 'Overzicht'),
      h('span', { class: 'kruimel' }, staat.omgeving
        ? `Omgeving: ${(staat.omgevingen.find((o) => o.slug === staat.omgeving) || {}).naam || staat.omgeving}`
        : 'Geen omgeving gekozen'),
      h('button', {
        class: 'btn btn-secondary ml-auto',
        onclick: testAlleVerbindingen,
      }, 'Alle verbindingen testen')),

    h('div', { class: 'cards' },
      kaart('Componenten beschikbaar', inGebruik.length, 'c-accent',
        'waar jij toegang toe hebt'),
      kaart('Verbindingen ingesteld', metVerbinding.length, 'c-accent',
        `van ${inGebruik.length} in gebruik`),
      kaart('Werkend getest', werkend.length, werkend.length ? 'c-success' : 'c-warning',
        werkend.length === metVerbinding.length ? 'alles in orde' : 'nog niet alles getest'),
      kaart('Met een probleem', mislukt.length, mislukt.length ? 'c-danger' : 'c-success',
        mislukt.length ? 'zie hieronder' : 'geen'))
  );

  if (!staat.omgevingen.length) {
    hoofd.append(h('div', { class: 'info-block warn' },
      h('strong', {}, 'Nog geen omgeving. '),
      'Maak eerst een omgeving aan onder ',
      h('a', { href: '#/instellingen/verbindingen' }, 'Verbindingen'),
      ' — dat is de gemeente of installatie waarvan je de componenten beheert.'));
  }

  const tabel = h('table', {},
    h('thead', {}, h('tr', {},
      h('th', {}, 'Component'), h('th', {}, 'Adres'), h('th', {}, 'Toegang'),
      h('th', {}, 'Verbinding'), h('th', {}, ''))),
    h('tbody', {}, staat.componenten.map((comp) => {
      const v = comp.verbinding;
      const status = !v || !v.actief
        ? h('span', { class: 'badge b-muted' }, 'niet in gebruik')
        : !v.ingevuld ? h('span', { class: 'badge b-warning' }, 'inloggegevens ontbreken')
          : v.laatsteTestOk === true ? h('span', { class: 'badge b-success' }, 'werkt')
            : v.laatsteTestOk === false ? h('span', { class: 'badge b-danger' }, 'fout')
              : h('span', { class: 'badge b-warning' }, 'niet getest');

      return h('tr', { class: (!v || !v.actief) ? 'uit' : '' },
        h('td', {}, h('strong', {}, comp.label),
          comp.letOp ? h('div', { class: 'hint' }, '⚠ beperking — zie het component zelf') : null),
        h('td', { class: 'mono' }, v && v.basisUrl ? v.basisUrl : '—'),
        h('td', {}, h('span', {
          class: 'badge ' + (comp.niveau === 'schrijven' ? 'b-accent' : 'b-muted'),
        }, comp.niveau === 'schrijven' ? 'lezen en wijzigen' : 'alleen lezen')),
        h('td', {}, status,
          v && v.actief && v.laatsteTestMelding && v.laatsteTestOk === false
            ? h('div', { class: 'hint' }, v.laatsteTestMelding) : null),
        h('td', {}, h('div', { class: 'actions' },
          h('button', {
            class: 'act',
            onclick: () => (window.location.hash = `#/c/${comp.key}/${comp.resources[0].key}`),
          }, 'Openen'))));
    }))
  );
  hoofd.append(h('div', { class: 'tabel-wrap' }, tabel));
}

function kaart(titel, waarde, kleur, onder) {
  return h('div', { class: 'card ' + (kleur || '') },
    h('div', { class: 'card-title' }, titel),
    h('div', { class: 'card-value' }, String(waarde)),
    h('div', { class: 'card-sub' }, onder || ''));
}

async function testAlleVerbindingen() {
  if (!vereistOmgeving()) return;
  toast('Verbindingen testen…', 'info');
  try {
    const resultaten = await api(`/api/omgevingen/${staat.omgeving}/test`, { method: 'POST' });
    const goed = Object.values(resultaten).filter((r) => r.ok).length;
    const totaal = Object.keys(resultaten).length;
    toast(`${goed} van ${totaal} verbindingen werken.`, goed === totaal ? 'success' : 'error');
    await laadRegistry();
    routeer();
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Resourceoverzicht ──────────────────────────────────────────────────────

const paginaStaat = {};   // per resource: huidige pagina en filters

async function toonResource(route) {
  const comp = component(route.component);
  if (!comp) throw new Error('Dit component bestaat niet of je hebt er geen toegang toe.');
  const resource = route.resource
    ? resourceVan(route.component, route.resource)
    : comp.resources[0];
  if (!resource) throw new Error('Deze resource bestaat niet.');

  const sleutel = `${comp.key}/${resource.key}/${route.ouder || ''}`;
  const lokaal = paginaStaat[sleutel] || (paginaStaat[sleutel] = { pagina: 1, filters: {} });
  const magSchrijven = comp.niveau === 'schrijven';

  const hoofd = leeg($('#hoofd'));

  const werkbalk = h('div', { class: 'toolbar' },
    h('h2', {}, resource.labelMv),
    h('span', { class: 'kruimel' }, comp.label),
    h('span', { class: 'ml-auto' }),
    h('button', { class: 'btn btn-secondary', onclick: () => routeer() }, '↻ Verversen'),
    magSchrijven && resource.methoden.includes('maak')
      ? h('button', {
        class: 'btn btn-primary',
        onclick: () => opentFormulier(comp, resource, null, route.ouder),
      }, '+ Nieuw')
      : null
  );
  hoofd.append(werkbalk);

  if (resource.hint) hoofd.append(h('div', { class: 'info-block info' }, resource.hint));
  if (comp.letOp) hoofd.append(h('div', { class: 'info-block warn' }, comp.letOp));

  // Filters
  if (resource.filters.length) {
    const rij = h('div', { class: 'toolbar' });
    for (const filter of resource.filters) {
      const invoer = filter.type === 'keuze'
        ? h('select', {
          class: 'kies',
          onchange: (e) => { lokaal.filters[filter.naam] = e.target.value; lokaal.pagina = 1; routeer(); },
        }, h('option', { value: '' }, filter.label),
          ...filter.keuzes.map((k) => h('option', {
            value: k, selected: lokaal.filters[filter.naam] === k,
          }, k)))
        : h('input', {
          class: 'zoek', placeholder: filter.label, value: lokaal.filters[filter.naam] || '',
          onchange: (e) => { lokaal.filters[filter.naam] = e.target.value.trim(); lokaal.pagina = 1; routeer(); },
        });
      rij.append(invoer);
    }
    if (Object.values(lokaal.filters).some(Boolean)) {
      rij.append(h('button', {
        class: 'btn btn-secondary',
        onclick: () => { lokaal.filters = {}; lokaal.pagina = 1; routeer(); },
      }, 'Filters wissen'));
    }
    hoofd.append(rij);
  }

  const params = new URLSearchParams();
  for (const [naam, waarde] of Object.entries(lokaal.filters)) if (waarde) params.set(naam, waarde);
  // Alleen pagineren waar het component dat kent: een overbodige ?page laat het
  // hele verzoek falen bij de ZGW-componenten.
  if (resource.gepagineerd !== false && lokaal.pagina > 1) params.set('page', lokaal.pagina);
  if (route.ouder) params.set('ouder', route.ouder);

  let gegevens;
  try {
    gegevens = await api(
      `/api/beheer/${staat.omgeving}/${comp.key}/${resource.key}?${params}`
    );
  } catch (err) {
    hoofd.append(h('div', { class: 'info-block danger' },
      h('strong', {}, 'Ophalen mislukt. '), err.message,
      err.status === 409
        ? h('p', {}, h('a', { href: '#/instellingen/verbindingen' }, 'Naar Verbindingen →'))
        : null));
    return;
  }

  const rijen = Array.isArray(gegevens) ? gegevens : (gegevens && gegevens.results) || [];
  const totaal = Array.isArray(gegevens) ? gegevens.length : (gegevens && gegevens.count);

  const kolommen = resource.velden.filter((v) => v.inLijst);
  const tonen = kolommen.length ? kolommen : resource.velden.slice(0, 4);

  const tabel = h('table', {},
    h('thead', {}, h('tr', {},
      ...tonen.map((veld) => h('th', {}, veld.label)),
      h('th', { style: 'width:1%' }, ''))),
    h('tbody', {}, rijen.length
      ? rijen.map((rij) => {
        const id = haalId(rij, resource);
        return h('tr', { class: 'klikbaar' },
          ...tonen.map((veld) => h('td', {
            title: typeof rij[veld.naam] === 'string' ? rij[veld.naam] : '',
            onclick: () => opentFormulier(comp, resource, rij, route.ouder),
          }, h('span', { class: veld.type === 'url' ? 'mono afkap' : '' },
            toonWaarde(rij[veld.naam], veld)))),
          h('td', {}, h('div', { class: 'actions' },
            !resource.ouder && geneste(comp, resource)
              ? h('button', {
                class: 'act',
                onclick: () => (window.location.hash =
                  `#/c/${comp.key}/${geneste(comp, resource).key}/${id}`),
              }, geneste(comp, resource).labelMv)
              : null,
            h('button', {
              class: 'act',
              onclick: () => opentFormulier(comp, resource, rij, route.ouder),
            }, magSchrijven && resource.methoden.includes('wijzig') ? 'Bewerken' : 'Bekijken'),
            magSchrijven && resource.methoden.includes('verwijder')
              ? h('button', {
                class: 'act act-danger',
                onclick: () => verwijder(comp, resource, rij, route.ouder),
              }, 'Verwijderen')
              : null)));
      })
      : h('tr', { class: 'leeg-rij' },
        h('td', { colspan: tonen.length + 1 }, 'Geen resultaten.')))
  );

  hoofd.append(h('div', { class: 'tabel-wrap' }, tabel));

  if (!Array.isArray(gegevens) && gegevens && (gegevens.next || gegevens.previous)) {
    hoofd.append(h('div', { class: 'paginering' },
      h('button', {
        class: 'btn btn-secondary', disabled: !gegevens.previous,
        onclick: () => { lokaal.pagina = Math.max(1, lokaal.pagina - 1); routeer(); },
      }, '← Vorige'),
      h('span', {}, `Pagina ${lokaal.pagina}${totaal ? ` — ${totaal} resultaten` : ''}`),
      h('button', {
        class: 'btn btn-secondary', disabled: !gegevens.next,
        onclick: () => { lokaal.pagina += 1; routeer(); },
      }, 'Volgende →')));
  } else if (totaal !== undefined && totaal !== null) {
    hoofd.append(h('div', { class: 'paginering' }, `${totaal} resultaten`));
  }
}

/** Een resource die deze resource als ouder heeft (bijvoorbeeld versies). */
function geneste(comp, resource) {
  return comp.resources.find((r) => r.ouder === resource.key) || null;
}

// Oplopende teller voor unieke <datalist>-id's — een formulier kan meerdere
// url-velden met voorstellen tonen, en een gebruiker kan meerdere formulieren
// ná elkaar openen binnen dezelfde pagina.
let _datalistTeller = 0;

/**
 * Haalt de bestaande items van een resource op als {url, label}-paren, voor
 * de voorstellen bij een url-veld dat naar die resource verwijst (zie
 * registry.py: Veld.verwijst_naar). Faalt stil — zonder voorstellen blijft
 * het veld gewoon een vrij in te vullen tekstveld.
 */
async function haalUrlKandidaten(comp, doelSleutel) {
  const doel = comp.resources.find((r) => r.key === doelSleutel);
  if (!doel) return [];
  const MAX = 300;   // ruim genoeg voor een dropdown, voorkomt een op hol geslagen ophaalactie
  const kandidaten = [];
  try {
    let pagina = 1;
    for (;;) {
      const params = new URLSearchParams();
      if (doel.gepagineerd !== false && pagina > 1) params.set('page', pagina);
      const gegevens = await api(`/api/beheer/${staat.omgeving}/${comp.key}/${doel.key}?${params}`);
      const rijen = Array.isArray(gegevens) ? gegevens : (gegevens && gegevens.results) || [];
      for (const rij of rijen) {
        if (rij && rij.url) kandidaten.push({ url: rij.url, label: rij[doel.titelVeld] || rij.url });
      }
      const volgende = !Array.isArray(gegevens) && gegevens && gegevens.next;
      if (!volgende || rijen.length === 0 || kandidaten.length >= MAX) break;
      pagina += 1;
    }
  } catch {
    return kandidaten;   // wat er al binnen was blijft bruikbaar
  }
  return kandidaten;
}

// ── Formulier ──────────────────────────────────────────────────────────────

function opentFormulier(comp, resource, rij, ouderId) {
  const nieuw = !rij;
  const magSchrijven = comp.niveau === 'schrijven'
    && resource.methoden.includes(nieuw ? 'maak' : 'wijzig');

  const invoerVelden = {};
  const formulier = h('div', {});
  const raster = h('div', { class: 'form-grid' });

  for (const veld of resource.velden) {
    const alleenLezen = veld.alleenLezen || !magSchrijven;
    // Automatisch toegekende velden bij een nieuw item alleen maar verwarrend.
    if (nieuw && veld.alleenLezen) continue;

    const waarde = rij ? rij[veld.naam] : undefined;
    const breed = ['tekstlang', 'json', 'lijst'].includes(veld.type);

    let invoer;
    let datalistVoorDitVeld = null;
    let hintVoorDitVeld = '';
    if (veld.type === 'bool') {
      invoer = h('select', { class: 'kies', disabled: alleenLezen },
        h('option', { value: '' }, '—'),
        h('option', { value: 'true', selected: waarde === true }, 'ja'),
        h('option', { value: 'false', selected: waarde === false }, 'nee'));
    } else if (veld.type === 'keuze' && veld.keuzes.length) {
      invoer = h('select', { class: 'kies', disabled: alleenLezen },
        h('option', { value: '' }, '—'),
        ...veld.keuzes.map((k) => h('option', { value: k, selected: waarde === k }, k)));
    } else if (veld.type === 'json' || veld.type === 'lijst') {
      const tekst = waarde === undefined || waarde === null
        ? (veld.type === 'lijst' ? '[]' : '{}')
        : JSON.stringify(waarde, null, 2);
      invoer = h('textarea', { readonly: alleenLezen, spellcheck: 'false' }, tekst);
    } else if (veld.type === 'tekstlang') {
      invoer = h('textarea', { readonly: alleenLezen }, waarde == null ? '' : String(waarde));
    } else {
      const soort = veld.type === 'datum' ? 'date'
        : veld.type === 'getal' ? 'number'
          : veld.type === 'email' ? 'email' : 'text';
      const attrs = {
        type: soort, readonly: alleenLezen,
        value: waarde == null ? '' : String(waarde),
      };
      // url-veld dat naar een resource binnen dit component verwijst (bv.
      // Zaaktype.catalogus): voorstellen tonen via <datalist>, met behoud
      // van het gewone tekstveld als terugvaloptie voor een handmatige URL.
      if (veld.type === 'url' && veld.verwijstNaar && !alleenLezen) {
        const doel = comp.resources.find((r) => r.key === veld.verwijstNaar);
        if (doel) {
          const dlId = `dl-${++_datalistTeller}`;
          attrs.list = dlId;
          datalistVoorDitVeld = h('datalist', { id: dlId });
          const datalistRef = datalistVoorDitVeld;
          haalUrlKandidaten(comp, veld.verwijstNaar).then((kandidaten) => {
            for (const k of kandidaten) datalistRef.append(h('option', { value: k.url }, k.label));
          });
          if (!veld.hint) {
            hintVoorDitVeld = `Typ om te zoeken in bestaande ${doel.labelMv.toLowerCase()}, `
              + 'of vul zelf een URL in.';
          }
        }
      }
      invoer = h('input', attrs);
    }

    invoerVelden[veld.naam] = { invoer, veld };
    raster.append(h('div', { class: 'form-row' + (breed ? ' breed' : '') },
      h('label', {}, veld.label, veld.verplicht ? h('span', { class: 'verplicht' }, ' *') : null),
      invoer,
      datalistVoorDitVeld,
      (veld.hint || hintVoorDitVeld) ? h('div', { class: 'hint' }, veld.hint || hintVoorDitVeld) : null,
      h('div', { class: 'veldfout', hidden: true })));
  }
  formulier.append(raster);

  // Ontsnappingsklep: het volledige object als JSON. Zo is elk veld dat de
  // registry (nog) niet kent alsnog te zien en te bewerken.
  //
  // Bewust een apart "gewijzigd"-vlagje i.p.v. rauwBlok.open bij het versturen:
  // dit tekstvak toont bij een nieuw item altijd een statische lege '{}' en
  // volgt de formuliervelden erboven niet live. Wie het blokje alleen opent
  // om te kijken (zonder iets te typen) zou anders zijn hele formulier
  // stilzwijgend zien vervangen door die lege '{}' — precies wat er misging.
  let rauwGewijzigd = false;
  const rauw = h('textarea', {
    spellcheck: 'false', style: 'min-height:240px',
    readonly: !magSchrijven,
    oninput: () => { rauwGewijzigd = true; },
  }, rij ? JSON.stringify(rij, null, 2) : '{}');
  const rauwBlok = h('details', { style: 'margin-top:8px' },
    h('summary', { style: 'cursor:pointer;font-size:12px;font-weight:700;color:var(--text-muted)' },
      'Alle velden als JSON (voor wat het formulier niet toont)'),
    h('div', { class: 'form-row', style: 'margin-top:10px' }, rauw,
      h('div', { class: 'hint' },
        'Wat je hier wijzigt wordt verstuurd in plaats van het formulier hierboven.')));
  formulier.append(rauwBlok);

  const foutBlok = h('div', { class: 'msg err', hidden: true });
  formulier.append(foutBlok);

  const knoppen = [{ label: magSchrijven ? 'Annuleren' : 'Sluiten' }];
  if (magSchrijven) {
    knoppen.push({
      label: nieuw ? 'Aanmaken' : 'Opslaan',
      soort: 'btn-primary',
      actie: async (sluit) => {
        foutBlok.hidden = true;
        $$('.veldfout', formulier).forEach((e) => { e.hidden = true; e.textContent = ''; });
        $$('input, textarea', formulier).forEach((e) => e.classList.remove('fout'));

        let gegevens;
        try {
          gegevens = rauwGewijzigd
            ? JSON.parse(rauw.value || '{}')
            : verzamel(invoerVelden, nieuw);
        } catch (err) {
          foutBlok.hidden = false;
          foutBlok.textContent = 'De JSON klopt niet: ' + err.message;
          return;
        }

        const id = rij ? haalId(rij, resource) : '';
        const basis = `/api/beheer/${staat.omgeving}/${comp.key}/${resource.key}`;
        const zoek = ouderId ? `?ouder=${encodeURIComponent(ouderId)}` : '';
        try {
          await api(nieuw ? `${basis}${zoek}` : `${basis}/${encodeURIComponent(id)}${zoek}`, {
            method: nieuw ? 'POST' : 'PATCH',
            body: gegevens,
          });
          toast(nieuw ? `${resource.label} aangemaakt.` : `${resource.label} opgeslagen.`, 'success');
          sluit();
          routeer();
        } catch (err) {
          foutBlok.hidden = false;
          foutBlok.textContent = err.message;
          for (const [naam, reden] of Object.entries(err.velden || {})) {
            const doel = invoerVelden[naam];
            if (!doel) continue;
            doel.invoer.classList.add('fout');
            const melding = doel.invoer.parentElement.querySelector('.veldfout');
            if (melding) { melding.hidden = false; melding.textContent = reden; }
          }
        }
      },
    });
  }

  modal({
    titel: (nieuw ? 'Nieuw: ' : magSchrijven ? 'Bewerken: ' : 'Bekijken: ') + resource.label,
    inhoud: formulier,
    knoppen,
    breed: true,
  });
}

/** Leest het formulier uit en zet de waarden om naar het juiste JSON-type. */
function verzamel(invoerVelden, nieuw) {
  const uit = {};
  for (const [naam, { invoer, veld }] of Object.entries(invoerVelden)) {
    if (veld.alleenLezen) continue;
    const ruw = invoer.value;

    if (veld.type === 'json' || veld.type === 'lijst') {
      const tekst = (ruw || '').trim();
      if (!tekst || tekst === '{}' || tekst === '[]') {
        // Een leeg verplicht veld toch meesturen: dan zegt het component zelf
        // wat er ontbreekt, in zijn eigen bewoordingen.
        if (veld.verplicht) uit[naam] = JSON.parse(tekst || (veld.type === 'lijst' ? '[]' : '{}'));
        continue;
      }
      uit[naam] = JSON.parse(tekst);
      continue;
    }
    if (veld.type === 'bool') {
      if (ruw === '') continue;
      uit[naam] = ruw === 'true';
      continue;
    }
    if (ruw === '' || ruw === null || ruw === undefined) {
      // Bij het bewerken betekent leegmaken écht leegmaken; bij het aanmaken
      // laten we het veld gewoon weg zodat de standaardwaarde geldt.
      if (!nieuw) uit[naam] = null;
      continue;
    }
    uit[naam] = veld.type === 'getal' ? Number(ruw) : ruw;
  }
  return uit;
}

function verwijder(comp, resource, rij, ouderId) {
  const id = haalId(rij, resource);
  const naam = rij[resource.titelVeld] || id;
  bevestig(
    `${resource.label} verwijderen`,
    `Weet je zeker dat je "${naam}" wilt verwijderen uit ${comp.label}? ` +
    'Dit gebeurt direct in het component zelf en kan niet ongedaan gemaakt worden.',
    async () => {
      const zoek = ouderId ? `?ouder=${encodeURIComponent(ouderId)}` : '';
      try {
        await api(
          `/api/beheer/${staat.omgeving}/${comp.key}/${resource.key}/${encodeURIComponent(id)}${zoek}`,
          { method: 'DELETE' }
        );
        toast(`${resource.label} verwijderd.`, 'success');
        routeer();
      } catch (err) {
        toast(err.message, 'error');
      }
    }
  );
}

// ── Instellingen ───────────────────────────────────────────────────────────

async function toonInstellingen(pagina) {
  // De menu-items zijn al op rol gefilterd, maar een #-link is zo getypt.
  const item = INSTELLINGEN.find((i) => i.key === pagina);
  if (item && item.beheerder && !staat.gebruiker.beheerder) {
    leeg($('#hoofd')).append(h('div', { class: 'info-block warn' },
      'Deze pagina is alleen voor beheerders.'));
    return undefined;
  }
  if (pagina === 'configuratie') return schermConfiguratie();
  if (pagina === 'verbindingen') return schermVerbindingen();
  if (pagina === 'gebruikers') return schermGebruikers();
  if (pagina === 'sso') return schermSso();
  if (pagina === 'auditlog') return schermAuditlog();
  return schermVerbindingen();
}

/**
 * Zonder gekozen omgeving zet de interface letterlijk 'null' in de URL en geeft
 * de server een 404 — een melding die niets uitlegt. Alles wat een omgeving
 * nodig heeft loopt daarom eerst hierlangs.
 */
function vereistOmgeving() {
  if (staat.omgeving) return true;
  toast(staat.omgevingen.length
    ? 'Kies eerst bovenin een omgeving.'
    : 'Maak eerst een omgeving aan — dat is de gemeente of installatie die je beheert.',
  'error');
  return false;
}

// ── Configuratie ───────────────────────────────────────────────────────────

/** Leidt een hostnaam af uit het hoofddomein: <subdomein>.<domein>. */
function afgeleideHostnaam(regel, domein) {
  const schoon = (domein || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
  return schoon && regel.subdomein ? `${regel.subdomein}.${schoon}` : '';
}

async function schermConfiguratie() {
  const hoofd = leeg($('#hoofd'));
  if (!staat.omgeving) {
    hoofd.append(h('div', { class: 'info-block warn' },
      staat.omgevingen.length
        ? 'Kies bovenin welke omgeving je wilt inrichten.'
        : 'Maak eerst een omgeving aan onder Verbindingen.'));
    return;
  }

  const cfg = await api(`/api/omgevingen/${staat.omgeving}/configuratie`);
  const rijen = [];

  const domein = h('input', {
    type: 'text', value: cfg.omgeving.domein || '', placeholder: 'gemeente.nl',
    onchange: () => vulLegeHostnamen(),
  });

  function vulLegeHostnamen() {
    for (const rij of rijen) {
      if (!rij.hostnaam.value.trim()) {
        const voorstel = afgeleideHostnaam(rij.regel, domein.value);
        if (voorstel) { rij.hostnaam.value = voorstel; rij.status(null); }
      }
    }
  }

  hoofd.append(
    h('div', { class: 'toolbar' }, h('h2', {}, 'Configuratie'),
      h('span', { class: 'kruimel' }, cfg.omgeving.naam)),
    h('div', { class: 'info-block info' },
      'Hier bepaal je welke CommonGround-componenten deze organisatie gebruikt en ',
      'op welk adres ze staan. De inloggegevens per component vul je daarna in ',
      'onder ', h('a', { href: '#/instellingen/verbindingen' }, 'Verbindingen'), '.'),

    h('div', { class: 'sectie' },
      h('h3', {}, 'Hoofddomein'),
      h('div', { class: 'form-row', style: 'max-width:420px' },
        h('label', {}, 'Wat is het hoofddomein voor uw componenten?'), domein,
        h('div', { class: 'hint' },
          'Alleen het domein, dus zonder https:// en zonder pad. Hieruit worden ',
          'de hostnamen voorgesteld, bijvoorbeeld ', h('span', { class: 'mono' }, 'openzaak.gemeente.nl'), '.')),
      h('button', {
        class: 'btn btn-secondary',
        onclick: () => {
          if (!domein.value.trim()) { toast('Vul eerst een hoofddomein in.', 'error'); return; }
          bevestig('Hostnamen afleiden',
            'Alle hostnamen worden overschreven met <subdomein>.' + domein.value.trim()
            + '. Handmatige afwijkingen gaan daarbij verloren.',
            () => {
              for (const rij of rijen) {
                const voorstel = afgeleideHostnaam(rij.regel, domein.value);
                if (voorstel) { rij.hostnaam.value = voorstel; rij.status(null); }
              }
              toast('Hostnamen ingevuld. Controleer ze en sla op.', 'success');
            }, { gevaarlijk: false, knopLabel: 'Overschrijven' });
        },
      }, 'Alle hostnamen afleiden uit het domein')),
  );

  // ── Componentenlijst ────────────────────────────────────────────────────
  const lijst = h('div', { class: 'sectie' },
    h('h3', {}, 'Welke componenten gebruikt u?'),
    h('p', { class: 'hint', style: 'margin-bottom:14px' },
      'Vink aan wat u gebruikt. Wat niet is aangevinkt blijft grijs in het menu ',
      'staan en is niet te openen. Uitvinken bewaart de inloggegevens, zodat ',
      'opnieuw aanzetten geen nieuw token vraagt.'));

  const tabel = h('table', {},
    h('thead', {}, h('tr', {},
      h('th', { style: 'width:1%' }, 'In gebruik'),
      h('th', {}, 'Component'),
      h('th', {}, 'Hostnaam (zonder /api)'),
      h('th', {}, 'DNS-controle'),
      h('th', { style: 'width:1%' }, ''))),
    h('tbody', {}));
  const body = tabel.querySelector('tbody');

  for (const regel of cfg.componenten) {
    const statusCel = h('td', {});
    const gebruikt = h('input', { type: 'checkbox', checked: regel.gebruikt });
    const hostnaam = h('input', {
      type: 'text', value: regel.hostnaam || '',
      placeholder: regel.voorstel || `${regel.subdomein}.gemeente.nl`,
      style: 'width:100%',
    });

    const zetStatus = (uitkomst) => {
      leeg(statusCel);
      if (uitkomst === null) {
        statusCel.append(h('span', { class: 'hint' }, 'nog niet gecontroleerd'));
      } else if (uitkomst === 'bezig') {
        statusCel.append(h('span', { class: 'hint' }, h('span', { class: 'spin' }, '◐'), ' controleren…'));
      } else if (uitkomst.ok) {
        statusCel.append(h('span', { class: 'dns-ok' }, '✓ '),
          h('span', { class: 'hint' }, uitkomst.melding));
      } else {
        statusCel.append(h('span', { class: 'dns-fout' }, '✗ '),
          h('span', { class: 'hint' }, uitkomst.melding));
      }
    };
    zetStatus(null);

    const controleer = async () => {
      const waarde = hostnaam.value.trim();
      if (!waarde) { zetStatus(null); return; }
      zetStatus('bezig');
      try {
        zetStatus(await api('/api/dns-check', { method: 'POST', body: { hostnaam: waarde } }));
      } catch (err) {
        zetStatus({ ok: false, melding: err.message });
      }
    };
    // Na het invullen meteen controleren; een knop blijft voor een hercontrole.
    hostnaam.addEventListener('change', controleer);

    const rij = { regel, gebruikt, hostnaam, status: zetStatus, controleer };
    rijen.push(rij);

    body.append(h('tr', {},
      h('td', {}, gebruikt),
      h('td', {}, h('strong', {}, regel.label),
        h('div', { class: 'hint' }, regel.auth === 'zgw-jwt' ? 'ZGW-JWT'
          : regel.auth === 'sessie' ? 'sessie-login' : 'API-token'),
        regel.ingevuld ? h('span', { class: 'badge b-success' }, 'inloggegevens ingevuld')
          : regel.heeftGegevens ? h('span', { class: 'badge b-warning' }, 'inloggegevens onvolledig')
            : null),
      h('td', {}, hostnaam),
      statusCel,
      h('td', {}, h('div', { class: 'actions' },
        h('button', { class: 'act', onclick: controleer }, 'DNS-controle'),
        regel.heeftGegevens
          ? h('button', {
            class: 'act act-danger',
            onclick: () => bevestig(`Gegevens van ${regel.label} wissen`,
              `Het adres én de opgeslagen inloggegevens van ${regel.label} worden verwijderd. `
              + 'Het component zelf verandert niet.',
              async () => {
                try {
                  await api(`/api/omgevingen/${staat.omgeving}/configuratie`, {
                    method: 'PUT',
                    body: { domein: domein.value.trim(),
                      componenten: [{ component: regel.component, verwijderen: true }] },
                  });
                  toast('Gegevens gewist.', 'success');
                  await laadRegistry();
                  routeer();
                } catch (err) { toast(err.message, 'error'); }
              }),
          }, 'Gegevens wissen')
          : null))));
  }

  lijst.append(h('div', { class: 'tabel-wrap' }, tabel));
  hoofd.append(lijst);

  hoofd.append(h('div', { class: 'toolbar' },
    h('button', {
      class: 'btn btn-primary',
      onclick: async (e) => {
        const knop = e.currentTarget;
        knop.disabled = true;
        try {
          await api(`/api/omgevingen/${staat.omgeving}/configuratie`, {
            method: 'PUT',
            body: {
              domein: domein.value.trim(),
              componenten: rijen.map((r) => ({
                component: r.regel.component,
                gebruikt: r.gebruikt.checked,
                hostnaam: r.hostnaam.value.trim(),
              })),
            },
          });
          toast('Configuratie opgeslagen.', 'success');
          await laadRegistry();
          routeer();
        } catch (err) {
          toast(err.message, 'error');
        } finally {
          knop.disabled = false;
        }
      },
    }, 'Opslaan'),
    h('button', {
      class: 'btn btn-secondary',
      onclick: () => { for (const r of rijen) if (r.gebruikt.checked) r.controleer(); },
    }, 'Alle aangevinkte controleren')));
}

async function schermVerbindingen() {
  const hoofd = leeg($('#hoofd'));
  const beheerder = staat.gebruiker.beheerder;

  hoofd.append(h('div', { class: 'toolbar' },
    h('h2', {}, 'Verbindingen'),
    h('span', { class: 'ml-auto' }),
    beheerder ? h('button', { class: 'btn btn-primary', onclick: dialoogNieuweOmgeving },
      '+ Omgeving') : null));

  hoofd.append(h('div', { class: 'info-block info' },
    'CommonControl praat uitsluitend via de publieke API van elk component. ',
    'Het maakt dus niet uit waar een component draait — alleen het adres en de ',
    'inloggegevens tellen.'));

  if (!staat.omgevingen.length) {
    hoofd.append(h('div', { class: 'info-block warn' },
      h('strong', {}, 'Begin hier: maak een omgeving aan. '),
      'Een omgeving is één samenhangende CommonGround-installatie, meestal één ',
      'gemeente. Daarna stel je onder Configuratie in welke componenten je '
      + 'gebruikt en op welk adres ze staan.'));
    return;
  }
  if (!staat.omgeving) {
    hoofd.append(h('div', { class: 'info-block warn' },
      'Kies bovenin welke omgeving je wilt beheren.'));
    return;
  }

  const omgeving = await api(`/api/omgevingen/${staat.omgeving}`);
  const perComponent = {};
  for (const v of omgeving.verbindingen) perComponent[v.component] = v;

  for (const comp of staat.componenten) {
    const v = perComponent[comp.key];
    hoofd.append(kaartVerbinding(comp, v, beheerder));
  }
}

function kaartVerbinding(comp, verbinding, beheerder) {
  const status = !verbinding || !verbinding.ingevuld
    ? h('span', { class: 'badge b-muted' }, 'niet ingesteld')
    : verbinding.laatsteTestOk === true ? h('span', { class: 'badge b-success' }, 'werkt')
      : verbinding.laatsteTestOk === false ? h('span', { class: 'badge b-danger' }, 'fout')
        : h('span', { class: 'badge b-warning' }, 'niet getest');

  const velden = {};
  const authType = (verbinding && verbinding.authType) || comp.auth;
  // Hetzelfde criterium als in het menu: aangevinkt onder Configuratie.
  const inGebruik = !!(verbinding && verbinding.actief);

  const blok = h('div', { class: 'sectie' + (inGebruik ? '' : ' uit') });
  blok.append(h('h3', {}, comp.label, ' ', status,
    inGebruik ? null : h('span', { class: 'badge b-muted', style: 'margin-left:6px' },
      'niet in gebruik')));
  if (!inGebruik) {
    blok.append(h('div', { class: 'info-block warn' },
      'Dit component staat niet aangevinkt onder ',
      h('a', { href: '#/instellingen/configuratie' }, 'Configuratie'),
      '. Zet het daar aan \u2014 met een hostnaam \u2014 om hier de inloggegevens in te vullen.'));
  }
  if (comp.letOp) blok.append(h('div', { class: 'info-block warn' }, comp.letOp));

  const raster = h('div', { class: 'form-grid' });

  velden.basisUrl = h('input', {
    type: 'url', placeholder: 'https://' + comp.subdomein + '.gemeente.nl',
    value: (verbinding && verbinding.basisUrl) || '', readonly: !beheerder,
  });
  raster.append(h('div', { class: 'form-row breed' },
    h('label', {}, 'Adres van het component'),
    velden.basisUrl,
    h('div', { class: 'hint' }, 'Alleen het adres, zonder API-pad. ',
      comp.apis.map((a) => a.pad).join(', '), ' wordt er zelf achter gezet.')));

  const authKeuze = h('select', { class: 'kies', disabled: !beheerder },
    ...[['zgw-jwt', 'ZGW-JWT (client-id + secret)'],
    ['token', 'Token in de Authorization-header'],
    ['sessie', 'Sessie-login (gebruikersnaam + wachtwoord)'],
    ['geen', 'Geen authenticatie']]
      .map(([w, l]) => h('option', { value: w, selected: authType === w }, l)));
  velden.authType = authKeuze;
  raster.append(h('div', { class: 'form-row' },
    h('label', {}, 'Authenticatie'), authKeuze));

  const specifiek = h('div', { class: 'form-grid breed' });
  raster.append(specifiek);

  function tekenSpecifiek() {
    leeg(specifiek);
    // De velden van de vorige vorm loskoppelen: anders leest 'Opslaan' straks
    // nog een waarde uit een invoerveld dat niet meer op het scherm staat.
    for (const naam of ['clientId', 'secret', 'token', 'tokenPrefix',
                        'gebruikersnaam', 'wachtwoord']) {
      delete velden[naam];
    }
    const gekozen = authKeuze.value;
    if (gekozen === 'zgw-jwt') {
      velden.clientId = h('input', {
        value: (verbinding && verbinding.clientId) || '', readonly: !beheerder,
        placeholder: 'bijvoorbeeld commoncontrol',
      });
      velden.secret = h('input', {
        type: 'password', readonly: !beheerder,
        placeholder: verbinding && verbinding.heeftSecret ? 'ingesteld — leeg laten = ongewijzigd' : '',
      });
      specifiek.append(
        h('div', { class: 'form-row' }, h('label', {}, 'Client-id'), velden.clientId),
        h('div', { class: 'form-row' }, h('label', {}, 'Client-secret'), velden.secret,
          h('div', { class: 'hint' },
            'Dit is de Applicatie in de Autorisaties-API van OpenZaak. Maak er bij ',
            'voorkeur één aan speciaal voor CommonControl.')));
    } else if (gekozen === 'token') {
      velden.token = h('input', {
        type: 'password', readonly: !beheerder,
        placeholder: verbinding && verbinding.heeftToken ? 'ingesteld — leeg laten = ongewijzigd' : '',
      });
      velden.tokenPrefix = h('input', {
        value: (verbinding && verbinding.tokenPrefix) || comp.tokenPrefix, readonly: !beheerder,
      });
      specifiek.append(
        h('div', { class: 'form-row' }, h('label', {}, 'Token'), velden.token,
          // Waar je dit token aanmaakt, zodat niemand hoeft te zoeken.
          comp.tokenHint && !(verbinding && verbinding.heeftToken)
            ? h('div', { class: 'hint' }, comp.tokenHint) : null),
        h('div', { class: 'form-row' }, h('label', {}, 'Voorvoegsel'), velden.tokenPrefix,
          h('div', { class: 'hint' },
            'Meestal "Token". Klopt het niet, dan corrigeert de verbindingstest dit zelf.')));
    } else if (gekozen === 'sessie') {
      velden.gebruikersnaam = h('input', {
        value: (verbinding && verbinding.gebruikersnaam) || '', readonly: !beheerder,
      });
      velden.wachtwoord = h('input', {
        type: 'password', readonly: !beheerder,
        placeholder: verbinding && verbinding.heeftWachtwoord ? 'ingesteld — leeg laten = ongewijzigd' : '',
      });
      specifiek.append(
        h('div', { class: 'form-row' }, h('label', {}, 'Gebruikersnaam'), velden.gebruikersnaam),
        h('div', { class: 'form-row' }, h('label', {}, 'Wachtwoord'), velden.wachtwoord));
    }
  }
  authKeuze.addEventListener('change', tekenSpecifiek);
  tekenSpecifiek();

  blok.append(raster);

  if (verbinding && verbinding.laatsteTestMelding) {
    blok.append(h('div', {
      class: 'msg ' + (verbinding.laatsteTestOk ? 'ok' : 'err'),
    }, verbinding.laatsteTestMelding));
  }

  const knoppen = h('div', { class: 'toolbar', style: 'margin:14px 0 0' });
  if (beheerder) {
    knoppen.append(h('button', {
      class: 'btn btn-primary',
      onclick: async (e) => {
        const knop = e.currentTarget;
        knop.disabled = true;
        try {
          const lichaam = {
            basisUrl: velden.basisUrl.value.trim(),
            authType: velden.authType.value,
            actief: true,
            clientId: velden.clientId ? velden.clientId.value.trim() : '',
            secret: velden.secret ? velden.secret.value : '',
            token: velden.token ? velden.token.value : '',
            tokenPrefix: velden.tokenPrefix ? velden.tokenPrefix.value.trim() : '',
            gebruikersnaam: velden.gebruikersnaam ? velden.gebruikersnaam.value.trim() : '',
            wachtwoord: velden.wachtwoord ? velden.wachtwoord.value : '',
          };
          await api(`/api/omgevingen/${staat.omgeving}/verbindingen/${comp.key}`,
            { method: 'PUT', body: lichaam });
          toast('Verbinding opgeslagen.', 'success');
          await laadRegistry();
          routeer();
        } catch (err) {
          toast(err.message, 'error');
        } finally {
          knop.disabled = false;
        }
      },
    }, 'Opslaan'));
  }
  knoppen.append(h('button', {
    class: 'btn btn-secondary',
    disabled: !verbinding,
    onclick: async (e) => {
      const knop = e.currentTarget;
      knop.disabled = true;
      knop.textContent = 'Testen…';
      try {
        const uitkomst = await api(
          `/api/omgevingen/${staat.omgeving}/verbindingen/${comp.key}/test`, { method: 'POST' });
        toast(uitkomst.melding, uitkomst.ok ? 'success' : 'error');
        await laadRegistry();
        routeer();
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        knop.disabled = false;
        knop.textContent = 'Verbinding testen';
      }
    },
  }, 'Verbinding testen'));

  if (beheerder && verbinding) {
    knoppen.append(h('button', {
      class: 'btn btn-danger-outline ml-auto',
      onclick: () => bevestig('Verbinding verwijderen',
        `De verbinding met ${comp.label} wordt verwijderd, inclusief de opgeslagen credentials. ` +
        'Het component zelf verandert niet.',
        async () => {
          await api(`/api/omgevingen/${staat.omgeving}/verbindingen/${comp.key}`, { method: 'DELETE' });
          toast('Verbinding verwijderd.', 'success');
          await laadRegistry();
          routeer();
        }),
    }, 'Verwijderen'));
  }
  blok.append(knoppen);

  // Niet in gebruik: alles onbruikbaar maken. Credentials invullen voor een
  // component dat uitstaat levert alleen verwarring op — de volgorde is eerst
  // aanzetten onder Configuratie, dan hier de gegevens.
  if (!inGebruik) {
    for (const el of blok.querySelectorAll('input, select, textarea, button')) {
      el.disabled = true;
    }
  }
  return blok;
}

function dialoogNieuweOmgeving() {
  const naam = h('input', { placeholder: 'Gemeente Voorbeeld' });
  const domein = h('input', { placeholder: 'voorbeeld.nl' });
  modal({
    titel: 'Nieuwe omgeving',
    inhoud: h('div', {},
      h('p', { class: 'hint', style: 'margin-bottom:14px' },
        'Een omgeving is één samenhangende CommonGround-installatie, meestal één gemeente.'),
      h('div', { class: 'form-row' }, h('label', {}, 'Naam'), naam),
      h('div', { class: 'form-row' }, h('label', {}, 'Basisdomein (optioneel)'), domein,
        h('div', { class: 'hint' }, 'Gebruikt om componenten automatisch te zoeken.'))),
    knoppen: [
      { label: 'Annuleren' },
      {
        label: 'Aanmaken', soort: 'btn-primary',
        actie: async (sluit) => {
          try {
            const nieuw = await api('/api/omgevingen', {
              method: 'POST',
              body: { naam: naam.value.trim(), domein: domein.value.trim() },
            });
            kiesOmgeving(nieuw.slug);
            sluit();
            toast('Omgeving aangemaakt.', 'success');
          } catch (err) { toast(err.message, 'error'); }
        },
      },
    ],
  });
}

// ── Gebruikers en rechten ──────────────────────────────────────────────────

async function schermGebruikers() {
  const hoofd = leeg($('#hoofd'));
  const gegevens = await api('/api/gebruikers');
  const groepen = await api('/api/groepen');

  hoofd.append(h('div', { class: 'toolbar' },
    h('h2', {}, 'Gebruikers en rechten'),
    h('span', { class: 'ml-auto' }),
    h('button', { class: 'btn btn-secondary', onclick: () => dialoogGroep(gegevens) }, '+ Groep'),
    h('button', {
      class: 'btn btn-primary',
      onclick: () => dialoogGebruiker(null, gegevens, groepen),
    }, '+ Gebruiker')));

  hoofd.append(h('div', { class: 'info-block info' },
    'Rechten gelden per component en zijn "alleen lezen" of "lezen en wijzigen". ',
    'Iemand kan rechten persoonlijk krijgen én via een groep; het sterkste recht telt.'));

  hoofd.append(h('div', { class: 'tabel-wrap' }, h('table', {},
    h('thead', {}, h('tr', {},
      h('th', {}, 'Gebruiker'), h('th', {}, 'E-mail'), h('th', {}, 'Herkomst'),
      h('th', {}, 'MFA'), h('th', {}, 'Groepen'), h('th', {}, 'Rechten'),
      h('th', {}, ''))),
    h('tbody', {}, gegevens.gebruikers.map((g) => h('tr', {},
      h('td', {}, h('strong', {}, g.gebruikersnaam),
        g.naam ? h('div', { class: 'hint' }, g.naam) : null,
        !g.actief ? h('span', { class: 'badge b-danger' }, 'inactief') : null),
      h('td', {}, g.email || '—'),
      h('td', {}, g.viaSso ? h('span', { class: 'badge b-info' }, 'SSO')
        : h('span', { class: 'badge b-muted' }, 'lokaal'),
        g.demo ? h('span', { class: 'badge b-warning', style: 'margin-left:4px' },
          'demo') : null),
      h('td', {}, g.viaSso ? h('span', { class: 'hint' }, 'via de IdP')
        : g.demo ? h('span', { class: 'hint' }, 'niet vereist')
          : g.mfaIngesteld ? h('span', { class: 'badge b-success' }, 'ingesteld')
            : h('span', { class: 'badge b-warning' }, 'nog niet')),
      h('td', {}, g.groepen && g.groepen.length
        ? g.groepen.map((n) => h('span', {
          class: 'badge b-muted', style: 'margin-right:4px',
        }, n))
        : h('span', { class: 'hint' }, 'geen')),
      h('td', {}, g.beheerder
        ? h('span', { class: 'badge b-accent' }, 'beheerder — alles')
        : g.demo
          ? h('span', { class: 'badge b-warning' }, 'demo — alles lezen')
          : rechtenSamenvatting(g.rechten, gegevens.componenten)),
      h('td', {}, h('div', { class: 'actions' },
        h('button', {
          class: 'act', onclick: () => dialoogGebruiker(g, gegevens, groepen),
        }, 'Bewerken')))))))));

  hoofd.append(h('div', { class: 'sectie', style: 'margin-top:20px' },
    h('h3', {}, 'Groepen'),
    h('p', { class: 'hint', style: 'margin-bottom:12px' },
      'Bij SSO worden gebruikers automatisch in de groep gezet die dezelfde naam heeft ' +
      'als hun groep bij de identity provider.'),
    h('div', { class: 'tabel-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, 'Groep'), h('th', {}, 'Leden'),
        h('th', {}, 'Rechten'), h('th', {}, ''))),
      h('tbody', {}, groepen.length ? groepen.map((gr) => h('tr', {},
        h('td', {}, h('strong', {}, gr.naam)),
        h('td', {}, String(gr.leden)),
        h('td', {}, rechtenSamenvatting(gr.rechten, gegevens.componenten)),
        h('td', {}, h('div', { class: 'actions' },
          h('button', {
            class: 'act', onclick: () => dialoogGroepRechten(gr, gegevens),
          }, 'Rechten'),
          h('button', {
            class: 'act act-danger',
            onclick: () => bevestig('Groep verwijderen',
              `De groep "${gr.naam}" en zijn rechten worden verwijderd.`,
              async () => {
                await api(`/api/groepen/${gr.id}`, { method: 'DELETE' });
                toast('Groep verwijderd.', 'success');
                routeer();
              }),
          }, 'Verwijderen')))))
        : h('tr', { class: 'leeg-rij' }, h('td', { colspan: 4 }, 'Nog geen groepen.')))))));
}

function rechtenSamenvatting(rechten, componenten) {
  const namen = Object.keys(rechten || {}).filter((k) => k !== '*');
  if (!namen.length) return h('span', { class: 'hint' }, 'geen');
  const labels = Object.fromEntries(componenten.map((c) => [c.key, c.label]));
  return h('span', {}, namen.map((k) => h('span', {
    class: 'badge ' + (rechten[k] === 'schrijven' ? 'b-accent' : 'b-muted'),
    style: 'margin-right:4px',
    title: rechten[k] === 'schrijven' ? 'lezen en wijzigen' : 'alleen lezen',
  }, labels[k] || k)));
}

function rechtenRaster(componenten, niveaus, huidig) {
  const kiezers = {};
  const raster = h('div', { class: 'form-grid' });
  for (const comp of componenten) {
    const kiezer = h('select', { class: 'kies' },
      ...niveaus.map((n) => h('option', {
        value: n.waarde, selected: (huidig[comp.key] || 'geen') === n.waarde,
      }, n.label)));
    kiezers[comp.key] = kiezer;
    raster.append(h('div', { class: 'form-row' }, h('label', {}, comp.label), kiezer));
  }
  const lees = () => Object.fromEntries(
    Object.entries(kiezers).map(([k, el]) => [k, el.value]));
  return { raster, lees };
}

function dialoogGebruiker(bestaand, gegevens, allegroepen = []) {
  const nieuw = !bestaand;
  const gebruikersnaam = h('input', { value: bestaand ? bestaand.gebruikersnaam : '', readonly: !nieuw });
  const naam = h('input', { value: bestaand ? bestaand.naam : '' });
  const email = h('input', { type: 'email', value: bestaand ? bestaand.email : '' });
  const wachtwoord = h('input', {
    type: 'password',
    placeholder: nieuw ? 'minimaal 12 tekens' : 'leeg laten = ongewijzigd',
  });
  const beheerder = h('input', { type: 'checkbox', checked: bestaand ? bestaand.beheerder : false });
  const demo = h('input', { type: 'checkbox', checked: bestaand ? !!bestaand.demo : false });
  const actief = h('input', { type: 'checkbox', checked: bestaand ? bestaand.actief : true });
  const mfaReset = h('input', { type: 'checkbox' });

  const { raster, lees } = rechtenRaster(
    gegevens.componenten, gegevens.niveaus, (bestaand && bestaand.rechten) || {});

  // Groepen: iemand zit meestal in weinig groepen, dus vinkjes zijn duidelijker
  // dan een meervoudige keuzelijst.
  const huidigeGroepen = new Set((bestaand && bestaand.groepen) || []);
  const groepVinkjes = {};
  const groepenBlok = h('div', {});
  if (allegroepen.length) {
    groepenBlok.append(h('h3', { style: 'font-size:13px;margin:18px 0 10px' }, 'Groepen'));
    const rij = h('div', { class: 'form-grid' });
    for (const groep of allegroepen) {
      const vinkje = h('input', {
        type: 'checkbox', checked: huidigeGroepen.has(groep.naam),
      });
      groepVinkjes[groep.naam] = vinkje;
      rij.append(h('label', { class: 'form-check' }, vinkje, ' ', groep.naam,
        h('span', { class: 'hint', style: 'margin-left:6px' },
          `${groep.leden} ${groep.leden === 1 ? 'lid' : 'leden'}`)));
    }
    groepenBlok.append(rij);
    if (bestaand && bestaand.viaSso) {
      groepenBlok.append(h('div', { class: 'info-block warn' },
        'Deze gebruiker logt in via SSO. Stuurt de identity provider groepen mee, '
        + 'dan zijn die bij de volgende login leidend en overschrijven ze wat je '
        + 'hier instelt.'));
    }
  } else {
    groepenBlok.append(h('p', { class: 'hint', style: 'margin-top:18px' },
      'Er zijn nog geen groepen. Maak er een aan met "+ Groep" om rechten aan '
      + 'meerdere gebruikers tegelijk te kunnen geven.'));
  }
  const gekozenGroepen = () => Object.entries(groepVinkjes)
    .filter(([, el]) => el.checked).map(([naam]) => naam);

  const rechtenBlok = h('div', {},
    h('h3', { style: 'font-size:13px;margin:18px 0 10px' }, 'Rechten per component'), raster);

  // Beheerder en demo zijn beide 'alles', maar tegengesteld: de een mag alles
  // wijzigen, de ander niets. Ze sluiten elkaar uit, en in beide gevallen zegt
  // de rechtentabel niets meer.
  const demoUitleg = h('div', { class: 'hint', style: 'margin:-8px 0 14px 24px' },
    'Een demo-account hoeft geen authenticator in te stellen. Het kijkt wel in '
    + 'echte gegevens, dus zet het na de demo op inactief.');

  const werkRollenBij = () => {
    if (beheerder.checked) demo.checked = false;
    if (demo.checked) beheerder.checked = false;
    demo.disabled = beheerder.checked;
    beheerder.disabled = demo.checked;
    rechtenBlok.hidden = beheerder.checked || demo.checked;
    groepenBlok.hidden = demo.checked;
    demoUitleg.hidden = !demo.checked;
  };
  beheerder.addEventListener('change', werkRollenBij);
  demo.addEventListener('change', werkRollenBij);
  werkRollenBij();

  modal({
    titel: nieuw ? 'Nieuwe gebruiker' : `Gebruiker ${bestaand.gebruikersnaam}`,
    breed: true,
    inhoud: h('div', {},
      h('div', { class: 'form-grid' },
        h('div', { class: 'form-row' }, h('label', {}, 'Gebruikersnaam'), gebruikersnaam),
        h('div', { class: 'form-row' }, h('label', {}, 'Volledige naam'), naam),
        h('div', { class: 'form-row' }, h('label', {}, 'E-mailadres'), email),
        h('div', { class: 'form-row' }, h('label', {}, 'Wachtwoord'), wachtwoord)),
      h('label', { class: 'form-check' }, beheerder,
        ' Beheerder (volledige toegang tot alles, inclusief instellingen)'),
      h('label', { class: 'form-check' }, demo,
        ' Demo-account (mag alle componenten inzien, maar niets wijzigen)'),
      demoUitleg,
      h('label', { class: 'form-check' }, actief, ' Account is actief'),
      bestaand && !bestaand.viaSso
        ? h('label', { class: 'form-check' }, mfaReset,
          ' Tweede factor opnieuw laten instellen (bij verlies van de authenticator)')
        : null,
      groepenBlok,
      rechtenBlok),
    knoppen: [
      { label: 'Annuleren' },
      bestaand ? {
        label: 'Verwijderen', soort: 'btn-danger-outline',
        actie: (sluit) => {
          sluit();
          bevestig('Gebruiker verwijderen',
            `"${bestaand.gebruikersnaam}" wordt verwijderd. De auditlogregels blijven bestaan.`,
            async () => {
              try {
                await api(`/api/gebruikers/${bestaand.id}`, { method: 'DELETE' });
                toast('Gebruiker verwijderd.', 'success');
                routeer();
              } catch (err) { toast(err.message, 'error'); }
            });
        },
      } : null,
      {
        label: nieuw ? 'Aanmaken' : 'Opslaan', soort: 'btn-primary',
        actie: async (sluit) => {
          const lichaam = {
            gebruikersnaam: gebruikersnaam.value.trim(),
            naam: naam.value.trim(),
            email: email.value.trim(),
            beheerder: beheerder.checked,
            demo: demo.checked,
            actief: actief.checked,
            groepen: demo.checked ? [] : gekozenGroepen(),
            rechten: beheerder.checked ? {} : lees(),
          };
          if (wachtwoord.value) lichaam.wachtwoord = wachtwoord.value;
          if (mfaReset.checked) lichaam.mfaResetten = true;
          try {
            await api(nieuw ? '/api/gebruikers' : `/api/gebruikers/${bestaand.id}`,
              { method: nieuw ? 'POST' : 'PATCH', body: lichaam });
            toast(nieuw ? 'Gebruiker aangemaakt.' : 'Gebruiker opgeslagen.', 'success');
            sluit();
            routeer();
          } catch (err) { toast(err.message, 'error'); }
        },
      },
    ].filter(Boolean),
  });
}

function dialoogGroep() {
  const naam = h('input', { placeholder: 'bijvoorbeeld Zaakbeheerders' });
  modal({
    titel: 'Nieuwe groep',
    inhoud: h('div', {},
      h('div', { class: 'form-row' }, h('label', {}, 'Naam'), naam,
        h('div', { class: 'hint' },
          'Gebruik bij SSO exact de naam van de groep bij de identity provider.'))),
    knoppen: [
      { label: 'Annuleren' },
      {
        label: 'Aanmaken', soort: 'btn-primary',
        actie: async (sluit) => {
          try {
            await api('/api/groepen', { method: 'POST', body: { naam: naam.value.trim() } });
            toast('Groep aangemaakt.', 'success');
            sluit();
            routeer();
          } catch (err) { toast(err.message, 'error'); }
        },
      },
    ],
  });
}

function dialoogGroepRechten(groep, gegevens) {
  const { raster, lees } = rechtenRaster(gegevens.componenten, gegevens.niveaus, groep.rechten || {});
  modal({
    titel: `Rechten van groep ${groep.naam}`,
    breed: true,
    inhoud: raster,
    knoppen: [
      { label: 'Annuleren' },
      {
        label: 'Opslaan', soort: 'btn-primary',
        actie: async (sluit) => {
          try {
            await api(`/api/groepen/${groep.id}`, { method: 'PATCH', body: { rechten: lees() } });
            toast('Rechten opgeslagen.', 'success');
            sluit();
            routeer();
          } catch (err) { toast(err.message, 'error'); }
        },
      },
    ],
  });
}

// ── SSO ────────────────────────────────────────────────────────────────────

async function schermSso() {
  const hoofd = leeg($('#hoofd'));
  const inst = await api('/api/sso');

  const velden = {};
  const maak = (sleutel, label, waarde, hint, type = 'text') => {
    velden[sleutel] = h('input', { type, value: waarde || '' });
    return h('div', { class: 'form-row' }, h('label', {}, label), velden[sleutel],
      hint ? h('div', { class: 'hint' }, hint) : null);
  };

  const actief = h('input', { type: 'checkbox', checked: inst.actief });
  const aanmaken = h('input', { type: 'checkbox', checked: inst.gebruikersAanmaken });
  const secret = h('input', {
    type: 'password',
    placeholder: inst.heeftClientSecret ? 'ingesteld — leeg laten = ongewijzigd' : '',
  });
  const uitslag = h('div', {});

  hoofd.append(
    h('div', { class: 'toolbar' }, h('h2', {}, 'Single Sign On')),
    h('div', { class: 'info-block info' },
      'CommonControl werkt met elke OpenID Connect-provider, zoals Entra ID of Keycloak. ',
      'Bij SSO regelt de provider ook de tweede factor; CommonControl vraagt dan zelf geen code meer. ',
      h('br'),
      'Registreer bij de provider deze redirect-URI: ',
      h('span', { class: 'mono' }, window.location.origin + '/sso/callback/')),

    h('div', { class: 'sectie' },
      h('h3', {}, 'Provider'),
      h('label', { class: 'form-check' }, actief, ' SSO inschakelen (toont de knop op het inlogscherm)'),
      h('div', { class: 'form-grid' },
        maak('discoveryUrl', 'Discovery-URL of issuer', inst.discoveryUrl,
          'Bijvoorbeeld https://login.microsoftonline.com/<tenant>/v2.0'),
        maak('knopLabel', 'Tekst op de knop', inst.knopLabel),
        maak('clientId', 'Client-id', inst.clientId),
        h('div', { class: 'form-row' }, h('label', {}, 'Client-secret'), secret),
        maak('scopes', 'Scopes', inst.scopes)),
      h('button', {
        class: 'btn btn-secondary',
        onclick: async () => {
          leeg(uitslag).append(h('p', { class: 'hint' }, 'Controleren…'));
          try {
            const r = await api('/api/sso/test', {
              method: 'POST', body: { discoveryUrl: velden.discoveryUrl.value.trim() },
            });
            leeg(uitslag).append(h('div', { class: 'msg ' + (r.ok ? 'ok' : 'err') }, r.melding));
          } catch (err) {
            leeg(uitslag).append(h('div', { class: 'msg err' }, err.message));
          }
        },
      }, 'Provider controleren'),
      uitslag),

    h('div', { class: 'sectie' },
      h('h3', {}, 'Claims en rollen'),
      h('div', { class: 'form-grid' },
        maak('claimGebruikersnaam', 'Claim met de gebruikersnaam', inst.claimGebruikersnaam),
        maak('claimEmail', 'Claim met het e-mailadres', inst.claimEmail),
        maak('claimGroepen', 'Claim met de groepen', inst.claimGroepen),
        maak('groepBeheerders', 'Groep die beheerder wordt', inst.groepBeheerders,
          'Leden hiervan krijgen volledige rechten. Leeg laten = niemand automatisch.')),
      h('label', { class: 'form-check' }, aanmaken,
        ' Onbekende gebruikers automatisch aanmaken bij een geslaagde SSO-login'),
      h('p', { class: 'hint' },
        'Groepen worden gekoppeld op naam: bestaat er hier een groep met dezelfde naam ' +
        'als bij de provider, dan krijgt de gebruiker de rechten van die groep.')),

    h('button', {
      class: 'btn btn-primary',
      onclick: async () => {
        try {
          await api('/api/sso', {
            method: 'PUT',
            body: {
              actief: actief.checked,
              gebruikersAanmaken: aanmaken.checked,
              clientSecret: secret.value,
              ...Object.fromEntries(Object.entries(velden).map(([k, el]) => [k, el.value.trim()])),
            },
          });
          toast('SSO-instellingen opgeslagen.', 'success');
        } catch (err) { toast(err.message, 'error'); }
      },
    }, 'Opslaan')
  );
}

// ── Auditlog ───────────────────────────────────────────────────────────────

const auditStaat = { pagina: 1, soort: '', component: '', zoek: '' };

async function schermAuditlog() {
  const hoofd = leeg($('#hoofd'));

  const soort = h('select', { class: 'kies', onchange: (e) => { auditStaat.soort = e.target.value; auditStaat.pagina = 1; routeer(); } },
    ...[['', 'Alles'], ['wijzigingen', 'Wijzigingen'], ['aanmeldingen', 'Aanmeldingen'], ['mislukt', 'Alleen mislukt']]
      .map(([w, l]) => h('option', { value: w, selected: auditStaat.soort === w }, l)));
  const zoek = h('input', {
    class: 'zoek', placeholder: 'Gebruiker…', value: auditStaat.zoek,
    onchange: (e) => { auditStaat.zoek = e.target.value.trim(); auditStaat.pagina = 1; routeer(); },
  });

  hoofd.append(h('div', { class: 'toolbar' },
    h('h2', {}, 'Auditlog'), soort, zoek,
    h('span', { class: 'kruimel ml-auto' },
      staat.gebruiker.beheerder ? 'Je ziet alle gebruikers.' : 'Je ziet je eigen handelingen.')));

  const params = new URLSearchParams({ page: auditStaat.pagina });
  if (auditStaat.soort) params.set('soort', auditStaat.soort);
  if (auditStaat.zoek) params.set('zoek', auditStaat.zoek);
  const gegevens = await api('/api/auditlog?' + params);

  hoofd.append(h('div', { class: 'tabel-wrap' }, h('table', {},
    h('thead', {}, h('tr', {},
      h('th', {}, 'Tijdstip'), h('th', {}, 'Gebruiker'), h('th', {}, 'Soort'),
      h('th', {}, 'Component'), h('th', {}, 'Actie'), h('th', {}, 'Resultaat'))),
    h('tbody', {}, gegevens.regels.length ? gegevens.regels.map((r) => h('tr', {},
      h('td', { class: 'mono' }, new Date(r.tijdstip).toLocaleString('nl-NL')),
      h('td', {}, r.gebruiker, r.ip ? h('div', { class: 'hint' }, r.ip) : null),
      h('td', {}, r.soort),
      h('td', {}, r.component ? (component(r.component) || {}).label || r.component : '—',
        r.resource ? h('div', { class: 'hint' }, r.resource) : null),
      h('td', {}, r.actie || '—', r.doel ? h('div', { class: 'hint mono afkap' }, r.doel) : null),
      h('td', {}, r.gelukt
        ? h('span', { class: 'badge b-success' }, 'gelukt')
        : h('span', { class: 'badge b-danger', title: r.detail }, 'mislukt'))))
      : h('tr', { class: 'leeg-rij' }, h('td', { colspan: 6 }, 'Geen regels.'))))));

  hoofd.append(h('div', { class: 'paginering' },
    h('button', {
      class: 'btn btn-secondary', disabled: auditStaat.pagina <= 1,
      onclick: () => { auditStaat.pagina -= 1; routeer(); },
    }, '← Vorige'),
    h('span', {}, `Pagina ${gegevens.pagina} van ${gegevens.paginas} — ${gegevens.aantal} regels`),
    h('button', {
      class: 'btn btn-secondary', disabled: auditStaat.pagina >= gegevens.paginas,
      onclick: () => { auditStaat.pagina += 1; routeer(); },
    }, 'Volgende →')));
}

// ── Omgevingskiezer en gebruikersmenu ──────────────────────────────────────

function kiesOmgeving(slug) {
  staat.omgeving = slug;
  localStorage.setItem(OPSLAG_OMGEVING, slug);
  laadRegistry().then(routeer);
}

function tekenKop() {
  const huidige = staat.omgevingen.find((o) => o.slug === staat.omgeving);
  const badge = $('#omgevingBadge');
  $('#omgevingLabel').textContent = huidige ? huidige.naam : 'Geen omgeving';
  badge.classList.toggle('leeg', !huidige);
  $('#omgevingDot').className = 'status-dot ' + (huidige ? '' : 'onbekend');

  const menu = leeg($('#omgevingMenu'));
  for (const omgeving of staat.omgevingen) {
    menu.append(h('div', {
      class: 'dropdown-item' + (omgeving.slug === staat.omgeving ? ' actief' : ''),
      role: 'option',
      onclick: () => { menu.classList.remove('open'); kiesOmgeving(omgeving.slug); },
    }, h('span', {}, omgeving.naam),
      omgeving.domein ? h('span', { class: 'hint ml-auto' }, omgeving.domein) : null));
  }
  if (staat.gebruiker.beheerder) {
    menu.append(h('div', {
      class: 'dropdown-item',
      style: 'color:var(--accent);font-weight:600',
      onclick: () => { menu.classList.remove('open'); dialoogNieuweOmgeving(); },
    }, '+ Nieuwe omgeving'));
  }

  const balk = $('#demoBanner');
  if (balk) balk.hidden = !staat.gebruiker.demo;

  $('#gebruikerNaam').textContent = staat.gebruiker.naam;
  const gebruikerMenu = leeg($('#gebruikerMenu'));
  gebruikerMenu.append(
    h('div', { class: 'dropdown-item', onclick: () => (window.location.hash = '#/instellingen/auditlog') },
      'Mijn handelingen'),
    h('div', {
      class: 'dropdown-item', style: 'color:var(--danger)',
      onclick: () => $('#uitlogForm').submit(),
    }, 'Uitloggen'));
}

function koppelKop() {
  const wissel = (knop, menu) => {
    knop.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = menu.classList.toggle('open');
      knop.setAttribute('aria-expanded', String(open));
    });
  };
  wissel($('#omgevingBadge'), $('#omgevingMenu'));
  wissel($('#knopGebruiker'), $('#gebruikerMenu'));
  document.addEventListener('click', () => {
    $('#omgevingMenu').classList.remove('open');
    $('#gebruikerMenu').classList.remove('open');
  });
  $('#knopVerversen').addEventListener('click', async () => {
    await laadRegistry();
    routeer();
    toast('Bijgewerkt.', 'success');
  });
}

// ── Opstarten ──────────────────────────────────────────────────────────────

async function laadRegistry() {
  const params = staat.omgeving ? '?omgeving=' + encodeURIComponent(staat.omgeving) : '';
  const gegevens = await api('/api/registry' + params);
  staat.componenten = gegevens.componenten;
  staat.perSleutel = Object.fromEntries(gegevens.componenten.map((c) => [c.key, c]));
  staat.omgevingen = gegevens.omgevingen;
  staat.gebruiker = gegevens.gebruiker;

  if (!staat.omgeving || !staat.omgevingen.some((o) => o.slug === staat.omgeving)) {
    const standaard = staat.omgevingen.find((o) => o.standaard) || staat.omgevingen[0];
    staat.omgeving = standaard ? standaard.slug : null;
    if (staat.omgeving) {
      localStorage.setItem(OPSLAG_OMGEVING, staat.omgeving);
      // Opnieuw laden zodat de verbindingsstatus bij de nu gekozen omgeving hoort.
      return laadRegistry();
    }
  }
  tekenKop();
  return gegevens;
}

async function start() {
  staat.omgeving = localStorage.getItem(OPSLAG_OMGEVING) || null;
  koppelKop();
  try {
    await laadRegistry();
  } catch (err) {
    leeg($('#hoofd')).append(h('div', { class: 'info-block danger' },
      'Kan de gegevens niet laden: ' + err.message));
    return;
  }
  window.addEventListener('hashchange', routeer);
  routeer();
}

document.addEventListener('DOMContentLoaded', start);
