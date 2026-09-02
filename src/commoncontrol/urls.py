"""
URL-indeling van CommonControl.

De interface is een enkele pagina met routering in de browser (op basis van
#-links). Daardoor is er precies een HTML-route en zijn alle andere routes
API's - dat scheelt een catch-all die per ongeluk API-paden opslokt.
"""

from django.urls import include, path

from commoncontrol import views as schil
from commoncontrol.auditlog import views as auditlog
from commoncontrol.beheer import views as beheer
from commoncontrol.toegang import beheer_api as toegang_beheer
from commoncontrol.verbindingen import views as verbindingen

urlpatterns = [
    # -- Inloggen, MFA, SSO en de gezondheidscontrole -------------------------
    path("", include("commoncontrol.toegang.urls")),

    # -- Omgevingen en verbindingen ------------------------------------------
    path("api/registry", beheer.registry_view),
    path("api/omgevingen", verbindingen.omgevingen),
    path("api/omgevingen/<slug:slug>", verbindingen.omgeving),
    path("api/omgevingen/<slug:slug>/test", verbindingen.test_alles),
    path("api/omgevingen/<slug:slug>/configuratie", verbindingen.configuratie),
    path("api/dns-check", verbindingen.dns_check),
    path(
        "api/omgevingen/<slug:slug>/verbindingen/<str:component_sleutel>",
        verbindingen.verbinding,
    ),
    path(
        "api/omgevingen/<slug:slug>/verbindingen/<str:component_sleutel>/test",
        verbindingen.test_verbinding,
    ),

    # -- Gebruikers, groepen, rechten, SSO en auditlog ------------------------
    path("api/gebruikers", toegang_beheer.gebruikers),
    path("api/gebruikers/<int:gebruiker_id>", toegang_beheer.gebruiker),
    path("api/groepen", toegang_beheer.groepen),
    path("api/groepen/<int:groep_id>", toegang_beheer.groep),
    path("api/sso", toegang_beheer.sso),
    path("api/sso/test", toegang_beheer.sso_test),
    path("api/auditlog", auditlog.gebeurtenissen),

    # -- Generieke beheerlaag ------------------------------------------------
    # 'rauw' staat bewust voor de resource-route: anders zou dat woord als
    # resourcesleutel worden gelezen.
    path("api/beheer/<slug:omgeving_slug>/<str:component_sleutel>/rauw", beheer.rauw),
    path(
        "api/beheer/<slug:omgeving_slug>/<str:component_sleutel>/<str:resource_sleutel>",
        beheer.collectie,
    ),
    path(
        "api/beheer/<slug:omgeving_slug>/<str:component_sleutel>/<str:resource_sleutel>"
        "/<path:object_id>",
        beheer.item,
    ),

    # -- De interface --------------------------------------------------------
    path("", schil.app, name="app"),
]

# Ook een pad dat geen enkele route raakt moet onder /api/ JSON opleveren.
handler404 = "commoncontrol.views.niet_gevonden"
handler500 = "commoncontrol.views.serverfout"
