"""Constanten voor de PWS-app. Pas dit bestand jaarlijks aan."""

from datetime import date

SCHOOLJAAR = "2025-2026"

FASEN = [
    {"naam": "Oriëntatie",  "start": date(2025, 5, 1),   "eind": date(2025, 9, 9),   "kleur": "#4A90E2"},
    {"naam": "Uitvoering",  "start": date(2025, 9, 10),  "eind": date(2025, 12, 18), "kleur": "#50C878"},
    {"naam": "Verwerking",  "start": date(2025, 12, 19), "eind": date(2026, 2, 13),  "kleur": "#F5A623"},
    {"naam": "Presentatie", "start": date(2026, 2, 14),  "eind": date(2026, 2, 26),  "kleur": "#C0392B"},
    {"naam": "Reflectie",   "start": date(2026, 2, 27),  "eind": date(2026, 3, 16),  "kleur": "#8B4789"},
]

MIJLPALEN = [
    {"datum": date(2025, 9, 9),   "titel": "Plan van aanpak",      "toelichting": "Hoofdvraag, deelvragen en werkplan inleveren via Magister (uiterlijk 17:00).", "sleutel": "plan_van_aanpak"},
    {"datum": date(2025, 10, 15), "titel": "PWS-ochtend oktober",  "toelichting": "Werkplan uitvoeren; logboek en bronnenlijst bijhouden.",                     "sleutel": None},
    {"datum": date(2025, 11, 27), "titel": "PWS-dag november",     "toelichting": "Onderzoek afronden, conceptverslag schrijven.",                              "sleutel": None},
    {"datum": date(2025, 12, 18), "titel": "Conceptversie",        "toelichting": "Conceptversie PWS inleveren via Magister (uiterlijk 23:30).",                "sleutel": "concept"},
    {"datum": date(2026, 1, 23),  "titel": "Feedback ontvangen",   "toelichting": "Feedback van begeleider op conceptversie; bespreken.",                       "sleutel": None},
    {"datum": date(2026, 2, 13),  "titel": "Definitieve versie",   "toelichting": "Definitieve versie via Magister (uiterlijk 23:30).",                         "sleutel": "definitief"},
    {"datum": date(2026, 2, 26),  "titel": "Presentatieavond",     "toelichting": "Presenteren aan ouders, docenten en belangstellenden (15 minuten).",         "sleutel": "presentatie"},
    {"datum": date(2026, 3, 16),  "titel": "Eindcijfer bekend",    "toelichting": "Eindbespreking afgerond; eindcijfer ingeleverd bij coördinator.",            "sleutel": None},
]

DEADLINE_SLEUTELS = [m["sleutel"] for m in MIJLPALEN if m["sleutel"]]

VAK_SUGGESTIES = [
    "Wiskunde A", "Wiskunde B", "Wiskunde C", "Wiskunde D",
    "Natuurkunde", "Scheikunde", "Biologie", "NLT",
    "Economie", "Bedrijfseconomie (M&O)",
    "Aardrijkskunde", "Geschiedenis", "Maatschappijwetenschappen",
    "Nederlands", "Engels", "Duits", "Frans", "Spaans",
    "Kunst (beeldend / muziek / drama)",
    "Twee vakken (in overleg)",
    "Anders (in overleg)",
]
