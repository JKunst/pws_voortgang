"""Database-initialisatie met demo-data. Draaien met: python init_db.py"""

from __future__ import annotations

import json
import sqlite3
import sys

from db import DB_PATH, hash_password


SCHEMA = """
CREATE TABLE IF NOT EXISTS pws_koppel (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    begeleider_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    aangemaakt    TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    naam          TEXT NOT NULL,
    rol           TEXT NOT NULL CHECK (rol IN ('student', 'begeleider', 'coordinator')),
    koppel_id     INTEGER REFERENCES pws_koppel(id) ON DELETE SET NULL,
    klas          TEXT
);

CREATE TABLE IF NOT EXISTS pws_onderzoek (
    koppel_id       INTEGER PRIMARY KEY REFERENCES pws_koppel(id) ON DELETE CASCADE,
    onderwerp       TEXT,
    vak             TEXT,
    hoofdvraag      TEXT,
    deelvragen_json TEXT,
    bijgewerkt      TEXT
);

CREATE TABLE IF NOT EXISTS pws_voortgang (
    koppel_id INTEGER NOT NULL REFERENCES pws_koppel(id) ON DELETE CASCADE,
    sleutel   TEXT NOT NULL,
    voltooid  INTEGER NOT NULL DEFAULT 0,
    gewijzigd TEXT,
    PRIMARY KEY (koppel_id, sleutel)
);

CREATE TABLE IF NOT EXISTS pws_commentaar (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    koppel_id  INTEGER NOT NULL REFERENCES pws_koppel(id) ON DELETE CASCADE,
    auteur_id  INTEGER NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    tekst      TEXT NOT NULL,
    aangemaakt TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_koppel  ON users(koppel_id);
CREATE INDEX IF NOT EXISTS idx_koppel_bg     ON pws_koppel(begeleider_id);
CREATE INDEX IF NOT EXISTS idx_comm_koppel   ON pws_commentaar(koppel_id);
"""


def _add_user(conn, username, password, naam, rol, klas=None):
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, naam, rol, klas) "
        "VALUES (?, ?, ?, ?, ?)",
        (username, hash_password(password), naam, rol, klas),
    )
    return cur.lastrowid


def _create_koppel(conn, begeleider_id=None):
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (?, datetime('now'))",
        (begeleider_id,),
    )
    return cur.lastrowid


def _place_in_koppel(conn, user_id, koppel_id):
    conn.execute("UPDATE users SET koppel_id = ? WHERE id = ?", (koppel_id, user_id))


def _add_onderzoek(conn, koppel_id, onderwerp, vak, hoofdvraag, deelvragen):
    conn.execute(
        "INSERT INTO pws_onderzoek "
        "(koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (
            koppel_id, onderwerp, vak, hoofdvraag,
            json.dumps(deelvragen, ensure_ascii=False),
        ),
    )


def _add_voortgang(conn, koppel_id, sleutel):
    conn.execute(
        "INSERT INTO pws_voortgang (koppel_id, sleutel, voltooid, gewijzigd) "
        "VALUES (?, ?, 1, datetime('now'))",
        (koppel_id, sleutel),
    )


def _add_commentaar(conn, koppel_id, auteur_id, tekst):
    conn.execute(
        "INSERT INTO pws_commentaar (koppel_id, auteur_id, tekst, aangemaakt) "
        "VALUES (?, ?, ?, datetime('now'))",
        (koppel_id, auteur_id, tekst),
    )


def initialize() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)

        # Begeleiders
        troostwijk_id = _add_user(conn, "c.troostwijk", "begeleider", "C. Troostwijk",  "begeleider")
        vdmaas_id     = _add_user(conn, "j.vandermaas", "begeleider", "J. van der Maas","begeleider")

        # Coördinator
        _gijsbers_id  = _add_user(conn, "m.gijsbers",   "coordinator","M. Gijsbers",    "coordinator")

        # Leerlingen (variatie aan namen, verdeeld over verschillende statussen)
        jaap_id     = _add_user(conn, "jaap.degoede",    "pws2026", "Jaap de Goede",     "student", "h5a")
        jonathan_id = _add_user(conn, "jonathan.degroot","pws2026", "Jonathan de Groot", "student", "h5a")
        eva_id      = _add_user(conn, "eva.jansen",      "pws2026", "Eva Jansen",        "student", "h5b")
        sanne_id    = _add_user(conn, "sanne.hendriks",  "pws2026", "Sanne Hendriks",    "student", "h5b")
        amira_id    = _add_user(conn, "amira.yildiz",    "pws2026", "Amira Yildiz",      "student", "h5a")
        tim_id      = _add_user(conn, "tim.bakker",      "pws2026", "Tim Bakker",        "student", "h5a")
        lars_id     = _add_user(conn, "lars.visser",     "pws2026", "Lars Visser",       "student", "h5b")
        # Nieuwe leerling zonder koppel — voor testen van de onboarding-flow
        _           = _add_user(conn, "nieuwe.leerling", "pws2026", "Sam Okonkwo",       "student", "h5b")

        # --- Koppel 1: Jaap + Jonathan, aangenomen door Troostwijk, volledig + 1 deadline af ---
        k1 = _create_koppel(conn, begeleider_id=troostwijk_id)
        _place_in_koppel(conn, jaap_id, k1)
        _place_in_koppel(conn, jonathan_id, k1)
        _add_onderzoek(
            conn, k1,
            "Luchtwrijving op voertuigen", "Natuurkunde",
            "Van welke factoren hangt de luchtwrijving op een voertuig af, en "
            "wat is het verband tussen elk van die factoren en de grootte van "
            "de luchtwrijving?",
            [
                "Wat is luchtwrijving en hoe wordt deze berekend?",
                "Welke vormfactoren beïnvloeden de luchtwrijving op een voertuig?",
                "Hoe verhoudt de snelheid zich tot de luchtwrijving?",
                "Hoe meet je luchtwrijving in een schaalmodel in een windtunnel?",
            ],
        )
        _add_voortgang(conn, k1, "plan_van_aanpak")
        _add_commentaar(
            conn, k1, troostwijk_id,
            "Goed begin, mooie hoofdvraag. Zorg dat jullie in de komende weken "
            "een duidelijke windtunnel-opzet op papier hebben voor we verder "
            "kunnen.",
        )

        # --- Koppel 2: Eva + Sanne, aangenomen door Troostwijk, alleen onderwerp ingevuld ---
        k2 = _create_koppel(conn, begeleider_id=troostwijk_id)
        _place_in_koppel(conn, eva_id, k2)
        _place_in_koppel(conn, sanne_id, k2)
        _add_onderzoek(
            conn, k2,
            "Microplastics in de Noordzee", "Biologie",
            "", [],
        )

        # --- Koppel 3: Amira + Tim, NOG ZONDER begeleider, volledig ingevuld ---
        k3 = _create_koppel(conn, begeleider_id=None)
        _place_in_koppel(conn, amira_id, k3)
        _place_in_koppel(conn, tim_id, k3)
        _add_onderzoek(
            conn, k3,
            "Spectra van lichtbronnen", "Natuurkunde",
            "Welke verschillen zijn er tussen het spectrum van een gloeilamp, "
            "een TL-buis en de zon, en waardoor worden die verschillen "
            "veroorzaakt?",
            [
                "Hoe ontstaat een lichtspectrum?",
                "Hoe meet je een spectrum betrouwbaar met een eenvoudige opstelling?",
                "Welke factoren bepalen het spectrum van een gloeilamp?",
                "Waarom heeft een TL-buis pieken in plaats van een continu spectrum?",
            ],
        )

        # --- Koppel 4: Lars solo, NOG ZONDER begeleider, niks ingevuld ---
        k4 = _create_koppel(conn, begeleider_id=None)
        _place_in_koppel(conn, lars_id, k4)

        # Sam Okonkwo bewust zonder koppel (onboarding-test)

        conn.commit()
        print(f"Database aangemaakt: {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    if DB_PATH.exists():
        antwoord = input(
            f"{DB_PATH} bestaat al. Overschrijven? (typ 'ja' om door te gaan): "
        )
        if antwoord.strip().lower() != "ja":
            print("Afgebroken.")
            sys.exit(0)
        DB_PATH.unlink()
    initialize()
