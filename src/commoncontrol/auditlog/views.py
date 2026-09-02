"""Inzage in de auditlog."""

from __future__ import annotations

from django.core.paginator import Paginator

from commoncontrol.api import api_view, ok

from .models import Gebeurtenis

PER_PAGINA = 50


@api_view("GET")
def gebeurtenissen(request):
    """
    Toont de auditlog. Een gewone gebruiker ziet zijn eigen regels, een
    beheerder alles — zo kan iedereen nagaan wat er onder zijn naam is gebeurd
    zonder dat de hele organisatie meekijkt.
    """
    query = Gebeurtenis.objects.select_related("gebruiker")
    if not request.user.is_superuser:
        query = query.filter(gebruiker=request.user)

    soort = request.GET.get("soort") or ""
    if soort == "wijzigingen":
        query = query.filter(soort="wijziging")
    elif soort == "aanmeldingen":
        query = query.filter(
            soort__in=("login", "login_mislukt", "mfa", "mfa_mislukt", "sso",
                       "sso_mislukt", "uitloggen")
        )
    elif soort == "mislukt":
        query = query.filter(gelukt=False)

    component = request.GET.get("component") or ""
    if component:
        query = query.filter(component=component)

    zoek = (request.GET.get("zoek") or "").strip()
    if zoek:
        query = query.filter(gebruikersnaam__icontains=zoek)

    pagina = Paginator(query, PER_PAGINA).get_page(request.GET.get("page") or 1)

    return ok(
        {
            "aantal": pagina.paginator.count,
            "paginas": pagina.paginator.num_pages,
            "pagina": pagina.number,
            "regels": [
                {
                    "tijdstip": g.tijdstip.isoformat(),
                    "soort": g.get_soort_display(),
                    "soortSleutel": g.soort,
                    "gebruiker": g.gebruikersnaam or "—",
                    "ip": g.ip or "",
                    "omgeving": g.omgeving,
                    "component": g.component,
                    "resource": g.resource,
                    "actie": g.actie,
                    "doel": g.doel,
                    "gelukt": g.gelukt,
                    "detail": g.detail,
                }
                for g in pagina.object_list
            ],
        }
    )
