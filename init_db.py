"""
init_db.py — Seed de PWS-database met demo-data voor lokaal testen.

Gebruik:
    python init_db.py

Dit werkt met het huidige ECK-iD schema (geen wachtwoorden).
Alle ECK-iDs beginnen met 'demo_' zodat ze makkelijk te herkennen zijn.

Voor SSO-gebaseerde login: gebruik het portaal met testmodus.
Dit script is bedoeld voor lokale ontwikkeling zonder portaal.
"""

from __future__ import annotations
import json
import sqlite3
import sys
from db import DB_PATH, get_conn, _init_schema


def seed() -> None:
    _init_schema()
    conn = get_conn()

    # ── Gebruikers ────────────────────────────────────────────────────────────
    gebruikers = [
        ("demo_coordinator",  "M. Gijssen",      "coordinator", None),
        ("demo_beg_troost",   "C. Troostwijk",    "begeleider",  None),
        ("demo_beg_maas",     "J. van der Waal",  "begeleider",  None),
        ("demo_jaap",         "Jaap de Goede",    "student",     "h5a"),
        ("demo_jonathan",     "Jonathan de Groot","student",     "h5a"),
        ("demo_eva",          "Eva Jansen",       "student",     "h5b"),
        ("demo_sanne",        "Sanne Hendriks",   "student",     "h5b"),
        ("demo_amira",        "Amira Yildiz",     "student",     "h5a"),
        ("demo_tim",          "Tim Bakker",       "student",     "h5a"),
        ("demo_lars",         "Lars Visser",      "student",     "h5b"),
        ("demo_sam",          "Sam Okonkwo",      "student",     "h5b"),
    ]
    for eckid, naam, rol, klas in gebruikers:
        conn.execute("""
            INSERT INTO users (eckid, naam, rol, klas)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(eckid) DO UPDATE SET naam=excluded.naam
        """, (eckid, naam, rol, klas))
    conn.commit()

    # ── Koppel 1: Jaap + Jonathan, Troostwijk, plan_van_aanpak af ─────────────
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES ('demo_beg_troost', datetime('now'))"
    )
    k1 = cur.lastrowid
    conn.execute("UPDATE users SET koppel_id=? WHERE eckid IN ('demo_jaap','demo_jonathan')", (k1,))
    conn.execute("""
        INSERT INTO pws_onderzoek (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
        VALUES (?, 'Luchtwrijving op voertuigen', 'Natuurkunde',
                'Van welke factoren hangt de luchtwrijving op een voertuig af?',
                '["Wat is luchtwrijving?","Welke vormfactoren spelen een rol?"]',
                datetime('now'))
    """, (k1,))
    conn.execute("INSERT INTO pws_voortgang (koppel_id, sleutel, voltooid, gewijzigd) VALUES (?,?,1,datetime('now'))",
                 (k1, "plan_van_aanpak"))
    conn.execute("INSERT INTO pws_commentaar (koppel_id, auteur_id, tekst, aangemaakt) VALUES (?,?,?,datetime('now'))",
                 (k1, "demo_beg_troost", "Goed begin, mooie hoofdvraag!"))

    # ── Koppel 2: Eva + Sanne, Troostwijk, alleen onderwerp ───────────────────
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES ('demo_beg_troost', datetime('now'))"
    )
    k2 = cur.lastrowid
    conn.execute("UPDATE users SET koppel_id=? WHERE eckid IN ('demo_eva','demo_sanne')", (k2,))
    conn.execute("""
        INSERT INTO pws_onderzoek (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
        VALUES (?, 'Microplastics in de Noordzee', 'Biologie', '', '[]', datetime('now'))
    """, (k2,))

    # ── Koppel 3: Amira + Tim, geen begeleider, volledig ingevuld ────────────
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (NULL, datetime('now'))"
    )
    k3 = cur.lastrowid
    conn.execute("UPDATE users SET koppel_id=? WHERE eckid IN ('demo_amira','demo_tim')", (k3,))
    conn.execute("""
        INSERT INTO pws_onderzoek (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
        VALUES (?, 'Spectra van lichtbronnen', 'Natuurkunde',
                'Welke verschillen zijn er tussen spectra van gloeilamp, TL-buis en zon?',
                '["Hoe ontstaat een lichtspectrum?","Hoe meet je een spectrum?"]',
                datetime('now'))
    """, (k3,))

    # ── Koppel 4: Lars solo, geen begeleider ──────────────────────────────────
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (NULL, datetime('now'))"
    )
    k4 = cur.lastrowid
    conn.execute("UPDATE users SET koppel_id=? WHERE eckid='demo_lars'", (k4,))

    # Sam Okonkwo bewust zonder koppel (onboarding-test)

    conn.commit()
    conn.close()
    print(f"✅ Database aangemaakt: {DB_PATH}")
    print("Demo ECK-iDs:")
    print("  demo_coordinator  — coördinator")
    print("  demo_beg_troost   — begeleider")
    print("  demo_jaap         — student (koppel met Jonathan)")
    print("  demo_sam          — student (geen koppel)")
    print()
    print("Voor SSO-login: gebruik het portaal met TESTMODUS=true.")


if __name__ == "__main__":
    if DB_PATH.exists():
        antwoord = input(f"{DB_PATH} bestaat al. Overschrijven? (typ 'ja'): ")
        if antwoord.strip().lower() != "ja":
            print("Afgebroken.")
            sys.exit(0)
        DB_PATH.unlink()
    seed()
