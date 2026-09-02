# CommonControl — beheerinterface voor de CommonGround-componenten
#
# Python 3.12: dat is de nieuwste versie die Django 5.1 officieel ondersteunt.
# Bewust niet 3.13/3.14 — zie de opmerking in src/tests/__init__.py.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=commoncontrol.settings

WORKDIR /app

# Buildtools zijn nodig voor psycopg/cryptography als er geen wheel is; ze gaan
# er daarna weer uit zodat het image klein en de aanvalsoppervlakte klein blijft.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && apt-get purge -y build-essential \
 && apt-get autoremove -y

COPY version.txt .
COPY src/ ./src/
COPY docker_start.sh .
# CR-tekens strippen vóór chmod. De bron staat op een Windows-machine en
# KubeManager pakt die map ongewijzigd in; komt het script met CRLF binnen, dan
# leest de kernel de shebang als "/bin/sh\r" en faalt de container met het
# misleidende "exec ./docker_start.sh: no such file or directory" — een fout die
# naar het script lijkt te wijzen maar over de interpreter gaat.
RUN sed -i 's/\r$//' docker_start.sh && chmod +x docker_start.sh

# Statische bestanden alvast verzamelen: WhiteNoise serveert ze en de
# manifest-opslag heeft dit nodig. Gebeurt tijdens de build, zodat het niet bij
# elke containerstart opnieuw hoeft. De sleutel hier is een wegwerpwaarde —
# collectstatic raakt geen geheimen aan.
RUN cd src && SECRET_KEY=build-tijd-sleutel DB_ENGINE=django.db.backends.sqlite3 \
    python manage.py collectstatic --noinput

# Niet als root draaien.
RUN useradd --uid 1001 --create-home commoncontrol && chown -R commoncontrol /app
USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/gezond/', timeout=4).status==200 else 1)"

CMD ["./docker_start.sh"]
