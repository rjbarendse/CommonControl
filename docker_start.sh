#!/bin/sh
# Opstartscript van de CommonControl-container.
set -e

cd /app/src

echo "==> Databasemigraties uitvoeren"
python manage.py migrate --noinput

# Eerste beheerder aanmaken als die via de omgeving is meegegeven. Zonder
# beheerder kan niemand inloggen en dus ook geen omgeving of rechten instellen.
# Het commando is idempotent, dus dit is ook het herstelpad bij een vergeten
# wachtwoord: pas het secret aan en herstart de pod.
if [ -n "${ADMIN_GEBRUIKERSNAAM}" ] && [ -n "${ADMIN_WACHTWOORD}" ]; then
  echo "==> Beheerder '${ADMIN_GEBRUIKERSNAAM}' controleren"
  python manage.py maak_beheerder \
    --gebruikersnaam "${ADMIN_GEBRUIKERSNAAM}" \
    --wachtwoord "${ADMIN_WACHTWOORD}" \
    --email "${ADMIN_EMAIL:-}"
fi

echo "==> CommonControl starten"
exec gunicorn commoncontrol.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${WEB_WORKERS:-3}" \
  --timeout "${WEB_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
