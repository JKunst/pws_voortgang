# PWS-platform

Standalone Streamlit-app voor het profielwerkstuk havo 5 / vwo 6.

## Rollen

- **Leerling** — ziet tijdlijn, vinkt deadlines af, kiest partner (of werkt solo),
  vult onderwerp/hoofdvraag/deelvragen in, leest feedback van begeleider.
- **Begeleider** — kiest koppels uit een lijst van beschikbare koppels
  (filterbaar op vak), ziet dashboard van eigen koppels met onderzoek en
  voortgang, geeft feedback.
- **Coördinator** — overzicht van álle koppels met leden, klas, vak,
  onderwerp, begeleider en status. Sorteer- en filterbaar, exporteerbaar
  als CSV.

## Datamodel

```
users         begeleiders + leerlingen (leerling heeft koppel_id FK)
pws_koppel    groep van 1 of 2 leerlingen (optioneel begeleider_id FK)
pws_onderzoek onderwerp / vak / hoofdvraag / deelvragen per koppel
pws_voortgang afgevinkte deadlines per koppel
pws_commentaar feedback-thread per koppel
```

Onderzoek, voortgang en feedback zitten op **koppel**-niveau, niet op leerling.
Twee partners delen dus automatisch alle data.

## Snel starten

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python init_db.py               # maakt pws.db met demo-data
streamlit run app.py
```

## Demo-accounts

Alle wachtwoorden behalve de begeleiders zijn `pws2026`.

| Rol | Gebruiker | Status |
|---|---|---|
| Coördinator | `m.gijsbers` / `coordinator` | overzicht van alles |
| Begeleider | `c.troostwijk` / `begeleider` | heeft 2 koppels aangenomen |
| Begeleider | `j.vandermaas` / `begeleider` | nog geen koppels — test de "Neem aan"-flow |
| Leerling | `jaap.degoede` | koppel met Jonathan, plan van aanpak af |
| Leerling | `jonathan.degroot` | partner van Jaap |
| Leerling | `eva.jansen` | koppel met Sanne, alleen onderwerp |
| Leerling | `sanne.hendriks` | partner van Eva |
| Leerling | `amira.yildiz` | koppel met Tim, volledig — wacht op begeleider |
| Leerling | `tim.bakker` | partner van Amira |
| Leerling | `lars.visser` | solo, niks ingevuld, geen begeleider |
| Leerling | `nieuwe.leerling` | geen koppel — test de partner-kiezer |

## Flow om te testen

1. Log in als `nieuwe.leerling` — je komt op een onboarding-scherm waar je
   eerst een partner moet kiezen (of solo) voordat je de app ziet.
2. Log in als `j.vandermaas` → tab **Beschikbare koppels** → neem het
   koppel van Amira + Tim aan. Verschijnt dan onder **Mijn koppels**.
3. Log in als `c.troostwijk` → open het koppel Jaap+Jonathan → schrijf
   een stuk feedback onderaan → log weer in als `jaap.degoede` en
   check het in de tab **Feedback van begeleider**.

## Bestanden

```
app.py               entry + login + rol-routing
db.py                SQLite-helpers (users, koppel, onderzoek, voortgang, commentaar)
pws_data.py          fasen, mijlpalen, vakkenlijst — pas jaarlijks aan
tijdlijn.py          visuele tijdlijn bovenaan (gedeeld)
view_student.py      leerling-weergave (5 tabs + partner-onboarding)
view_begeleider.py   begeleider-dashboard met 2 tabs
init_db.py           schema + demo-data
```

## Bijwerken voor volgend schooljaar

In `pws_data.py`:
- `SCHOOLJAAR`
- `FASEN` (datums per fase)
- `MIJLPALEN` (alle deadlines en PWS-ochtenden)

De sleutels in `MIJLPALEN` (`plan_van_aanpak`, `concept`, `definitief`,
`presentatie`) worden gebruikt in de database. Laat die hetzelfde, anders
gaat oude voortgang verloren.

## Nieuwe gebruikers toevoegen

Direct in SQLite of via een korte helper:

```python
import sqlite3
import db
from init_db import _add_user

conn = sqlite3.connect(db.DB_PATH)
_add_user(conn, "nieuwe.leerling", "startwachtwoord", "Naam Leerling", "student", "h5c")
conn.commit()
conn.close()
```

Nieuwe leerlingen krijgen bij eerste login een onboarding-scherm om hun
partner te kiezen. Begeleiders zien het koppel daarna vanzelf bij
*Beschikbare koppels*.

## Productie-opmerkingen

- Wachtwoorden: PBKDF2-SHA256 (100k iteraties) — prima voor schoolgebruik.
  Forceer het wijzigen van het startwachtwoord of integreer met SSO.
- SQLite is prima voor ~200 leerlingen. Bij meer, of veel concurrente
  schrijfacties: Postgres.
- Upgraden vanaf een eerdere versie van dit schema: db weggooien en opnieuw
  seeden (het oude model had geen `pws_koppel`-tabel).
# pws_voortgang
