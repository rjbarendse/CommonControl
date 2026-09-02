"""
Autorisatie: welk niveau heeft een gebruiker op welk CommonGround-component.

Regels, van sterk naar zwak:
  1. superuser        → schrijven op alles;
  2. persoonlijk recht en groepsrechten worden samengevoegd, het STERKSTE wint.

Bewust "sterkste wint" en niet "meest beperkende wint": rechten worden hier
toegekend, niet ontnomen. Iemand persoonlijk schrijfrecht geven terwijl zijn
groep leesrecht heeft moet werken zoals de beheerder verwacht.
"""

from __future__ import annotations

from .models import NIVEAU_GEEN, NIVEAU_LEZEN, NIVEAU_RANG, NIVEAU_SCHRIJVEN, ComponentToegang


def rechten_van(gebruiker) -> dict[str, str]:
    """Geeft {componentsleutel: niveau} voor deze gebruiker."""
    if not gebruiker or not gebruiker.is_authenticated:
        return {}

    if gebruiker.is_superuser:
        return {"*": NIVEAU_SCHRIJVEN}

    # Een demo-account ziet alles, maar alleen lezend. Bewust als jokerteken en
    # niet als negen losse rijen: dan hoeft niemand bij een nieuw component te
    # onthouden dat de demo-rechten ook bijgewerkt moeten worden.
    profiel = getattr(gebruiker, "profiel", None)
    if profiel is not None and profiel.demo:
        return {"*": NIVEAU_LEZEN}

    resultaat: dict[str, str] = {}
    groep_ids = list(gebruiker.groups.values_list("id", flat=True))

    rijen = ComponentToegang.objects.filter(gebruiker=gebruiker)
    if groep_ids:
        rijen = rijen | ComponentToegang.objects.filter(groep_id__in=groep_ids)

    for rij in rijen:
        huidig = resultaat.get(rij.component, NIVEAU_GEEN)
        if NIVEAU_RANG[rij.niveau] > NIVEAU_RANG[huidig]:
            resultaat[rij.component] = rij.niveau

    return {k: v for k, v in resultaat.items() if v != NIVEAU_GEEN}


def niveau_voor(gebruiker, component: str) -> str:
    """Het effectieve niveau van deze gebruiker op één component."""
    rechten = rechten_van(gebruiker)
    if rechten.get("*"):
        return rechten["*"]
    return rechten.get(component, NIVEAU_GEEN)


def mag_lezen(gebruiker, component: str) -> bool:
    return NIVEAU_RANG[niveau_voor(gebruiker, component)] >= NIVEAU_RANG[NIVEAU_LEZEN]


def mag_schrijven(gebruiker, component: str) -> bool:
    return NIVEAU_RANG[niveau_voor(gebruiker, component)] >= NIVEAU_RANG[NIVEAU_SCHRIJVEN]


def zichtbare_componenten(gebruiker, alle_sleutels: list[str]) -> list[str]:
    """Filtert een lijst componentsleutels op wat deze gebruiker mag zien."""
    rechten = rechten_van(gebruiker)
    if rechten.get("*"):
        return list(alle_sleutels)
    return [sleutel for sleutel in alle_sleutels if sleutel in rechten]
