"""Toetst de feitelijke beweringen in README.md tegen de code.

Reden: de README noemde 56 resources (waren er 57), 70 tests (waren er 164), een
standaardwachtwoord dat niet meer bestaat, en een testonderwerp voor een functie die
verwijderd is. Zulke getallen lopen stil uit de pas; deze controle vangt dat af.

Draaien:  python controleer-readme.py
"""
import io
import pathlib
import re
import sys

WORTEL = pathlib.Path(__file__).parent
ok = True

# De Windows-console staat standaard op cp1252 en struikelt over een emoji of een
# gedachtestreepje in een label.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check(label, geslaagd, extra=""):
    global ok
    ok = ok and bool(geslaagd)
    print(("  OK   " if geslaagd else "  FOUT ") + label + (f" — {extra}" if extra else ""))


def lees(pad):
    return io.open(WORTEL / pad, encoding="utf-8").read()


readme = lees("README.md")
registry = lees("src/commoncontrol/beheer/registry.py")

# ── aantallen ───────────────────────────────────────────────────────────────
componenten = len(re.findall(r"^[A-Z][A-Z_]+ = Component\(", registry, re.M))
resources = len(re.findall(r"\bResource\(", registry))
tests = sum(
    len(re.findall(r"^\s*def test_", lees(p.relative_to(WORTEL)), re.M))
    for p in (WORTEL / "src" / "tests").glob("test_*.py")
)

check(f"README noemt {componenten} componenten", f"{componenten} componenten" in readme)
check(f"README noemt {resources} resources", f"{resources} resources" in readme,
      re.findall(r"\d+ resources", readme))
check(f"README noemt {tests} tests", f"{tests} tests" in readme,
      re.findall(r"\d+ tests", readme))

# Elk component uit de registry staat in de tabel.
# ⚠ Alleen het label van het Component zelf pakken — een `label=` verderop in het blok
#   hoort bij een Resource, en die horen niet in de tabel.
comp_labels = []
for m in re.finditer(r"^[A-Z][A-Z_]+ = Component\(", registry, re.M):
    blok = registry[m.end():m.end() + 600]
    lab = re.search(r"label=\"([^\"]+)\"", blok)
    if lab:
        comp_labels.append(lab.group(1))
tabel = readme.split("### Eerlijke beperkingen")[0]
ontbreekt = [l for l in comp_labels if l not in tabel]
check(f"alle {len(comp_labels)} componenten staan in de tabel", not ontbreekt, ", ".join(ontbreekt))

# ── verwijderde functionaliteit wordt niet meer beschreven ──────────────────
# De import "Uit KubeManager overnemen" en het zoeken op domein zijn verwijderd.
# ⚠ Op de route en de view toetsen, niet op het wóórd: dat komt ook voor in een
#   testcommentaar dat juist uitlegt dat de route weg is.
broncode = "\n".join(lees(p.relative_to(WORTEL)) for p in (WORTEL / "src").rglob("*.py"))
weg = (not re.search(r"def (importeren|zoeken)\w*\s*\(", broncode)
       and not re.search(r'["\']api/(importeren|zoeken)', broncode)
       and not (WORTEL / "src/commoncontrol/verbindingen/ontdekking.py").exists())
check("de import-functie is inderdaad weg uit de code", weg)
if weg:
    check("README belooft die functie niet meer",
          "wizard-configuratiebestand" not in readme and "overnemen" not in readme)

# ── docker-compose: geen standaardgeheimen, README zegt dat ook ────────────
compose = lees("docker-compose.yml")
verplicht = re.findall(r"\$\{(\w+):\?", compose)
check("docker-compose eist geheimen uit .env", bool(verplicht), ", ".join(verplicht))
check("README noemt geen standaardwachtwoord meer",
      "eerste-wachtwoord-wijzigen" not in readme)
for naam in verplicht:
    check(f"README noemt {naam} voor de .env", naam in readme)

# ── tokens: elk component met tokenauth heeft een hint, README klopt daarmee ─
token_comps = []
for m in re.finditer(r"^([A-Z][A-Z_]+) = Component\(", registry, re.M):
    blok = registry[m.end():].split("\n)")[0]
    if re.search(r"auth=\"token\"", blok):
        token_comps.append((m.group(1), "token_hint" in blok))
check(f"{len(token_comps)} componenten gebruiken tokenauthenticatie",
      len(token_comps) > 0, ", ".join(n for n, _ in token_comps))
zonder = [n for n, h in token_comps if not h]
check("elk daarvan legt uit waar het token vandaan komt", not zonder, ", ".join(zonder))
check("README noemt datzelfde aantal", f"de {['nul','één','twee','drie','vier','vijf','zes','zeven','acht','negen'][len(token_comps)]} componenten met tokenauthenticatie" in readme
      or f"{len(token_comps)} componenten met tokenauthenticatie" in readme,
      "verwacht: 'de zes componenten met tokenauthenticatie'")

# ── verwijzingen naar bestanden die moeten bestaan ──────────────────────────
for pad in re.findall(r"`(k8s/[\w./-]+)`|(k8s/[\w.-]+\.yaml)", readme):
    p = pad[0] or pad[1]
    if p and not (WORTEL / p).exists():
        check(f"bestand {p} bestaat", False)
for p in ["LICENSE", "src/commoncontrol/beheer/registry.py", "src/commoncontrol/crypto.py",
          "src/commoncontrol/api.py", "docker_start.sh", "Dockerfile"]:
    check(f"{p} bestaat", (WORTEL / p).exists())

print("ALL_OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
