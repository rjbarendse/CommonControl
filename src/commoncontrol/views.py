"""De applicatieschil: één pagina waarin de interface draait."""

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def app(request):
    """
    Rendert de schil. ensure_csrf_cookie is essentieel: de interface doet al zijn
    schrijfacties met fetch() en moet de CSRF-token uit de cookie kunnen lezen.
    """
    return render(request, "app.html")


def niet_gevonden(request, exception=None):
    """
    Een pad onder /api/ moet ook JSON teruggeven als het helemaal geen view
    raakt; anders krijgt de interface HTML terug en kan hij alleen de status
    tonen. Buiten /api/ blijft het gewone gedrag.
    """
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"ok": False, "fout": f"Onbekend API-pad: {request.path}"}, status=404
        )
    return render(request, "toegang/sso_fout.html",
                  {"melding": "Deze pagina bestaat niet."}, status=404)


def serverfout(request):
    """
    Vangnet: ook een onverwachte uitzondering moet onder /api/ JSON opleveren.

    Zonder dit krijgt de interface HTML terug en kan hij alleen "de server gaf
    HTTP 500" tonen — een melding waar niemand iets mee kan. De echte oorzaak
    blijft in het podlogboek staan; die hoort niet in het antwoord, want daar
    kan gevoelige informatie in zitten.
    """
    if request.path.startswith("/api/"):
        return JsonResponse(
            {"ok": False,
             "fout": "Er ging iets mis in CommonControl zelf. Kijk in het logboek van de "
                     "pod voor de oorzaak."},
            status=500,
        )
    return render(request, "toegang/sso_fout.html",
                  {"melding": "Er ging iets mis. Probeer het opnieuw."}, status=500)
