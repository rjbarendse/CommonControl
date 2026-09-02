from django.urls import path

from . import views

app_name = "toegang"

urlpatterns = [
    path("gezond/", views.gezond, name="gezond"),
    path("inloggen/", views.inloggen, name="inloggen"),
    path("uitloggen/", views.uitloggen, name="uitloggen"),
    path("mfa/instellen/", views.mfa_instellen, name="mfa_instellen"),
    path("mfa/controle/", views.mfa_controle, name="mfa_controle"),
    path("sso/start/", views.sso_start, name="sso_start"),
    path("sso/callback/", views.sso_callback, name="sso_callback"),
]
