"""
Maakt (of herstelt) een beheerdersaccount.

Bestaansreden: zonder beheerder kan niemand een omgeving aanmaken of rechten
uitdelen — dan staat de applicatie er wel, maar kun je er niets mee. Django's
eigen `createsuperuser` vraagt om invoer en werkt dus niet in een container die
zonder terminal opstart.

Idempotent: bestaat de gebruiker al, dan wordt alleen de beheerdersrol hersteld
(en het wachtwoord gezet als je dat meegeeft). Zo is dit ook het herstelpad als
iemand zichzelf per ongeluk heeft buitengesloten.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from commoncontrol.toegang.models import Gebruikersprofiel


class Command(BaseCommand):
    help = "Maakt een beheerder aan of herstelt er een."

    def add_arguments(self, parser):
        parser.add_argument("--gebruikersnaam", required=True)
        parser.add_argument("--wachtwoord", default="")
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--mfa-resetten",
            action="store_true",
            help="Laat de tweede factor opnieuw instellen (bij verlies van de authenticator).",
        )

    def handle(self, *args, **opties):
        gebruikersnaam = opties["gebruikersnaam"].strip()
        if not gebruikersnaam:
            raise CommandError("Geef een gebruikersnaam op.")

        gebruiker, nieuw = User.objects.get_or_create(username=gebruikersnaam)
        if nieuw and not opties["wachtwoord"]:
            gebruiker.delete()
            raise CommandError(
                "Voor een nieuwe beheerder is --wachtwoord verplicht "
                "(minimaal 12 tekens)."
            )

        if opties["wachtwoord"]:
            if len(opties["wachtwoord"]) < 12:
                raise CommandError("Het wachtwoord moet minstens 12 tekens hebben.")
            gebruiker.set_password(opties["wachtwoord"])
        if opties["email"]:
            gebruiker.email = opties["email"]

        gebruiker.is_superuser = True
        gebruiker.is_staff = True
        gebruiker.is_active = True
        gebruiker.save()

        profiel, _ = Gebruikersprofiel.objects.get_or_create(gebruiker=gebruiker)
        if opties["mfa_resetten"]:
            profiel.mfa_ingesteld = False
            profiel.totp_geheim = ""
            profiel.save(update_fields=["mfa_ingesteld", "totp_geheim_versleuteld"])

        self.stdout.write(self.style.SUCCESS(
            f"Beheerder '{gebruikersnaam}' is {'aangemaakt' if nieuw else 'bijgewerkt'}. "
            "Bij de eerste login wordt om een authenticator-app gevraagd."
        ))
