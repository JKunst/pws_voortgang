"""
db.py — SQLite helpers voor de PWS-app.

Primaire sleutel: ECK-iD (via portaal-token).
Geen wachtwoorden, geen gebruikersnamen.
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
import os

DB_PATH = Path(os.environ.get("PWS_DB_PATH", str(Path(__file__).parent / "pws.db")))


# ── Connectie ─────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db() -> None:
    """Altijd schema initialiseren — CREATE TABLE IF NOT EXISTS is idempotent."""
    _init_schema()


def _init_schema():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            eckid     TEXT PRIMARY KEY,
            naam      TEXT NOT NULL,
            rol       TEXT NOT NULL CHECK (rol IN ('student', 'begeleider', 'coordinator')),
            koppel_id INTEGER REFERENCES pws_koppel(id) ON DELETE SET NULL,
            klas      TEXT
        );

        CREATE TABLE IF NOT EXISTS pws_koppel (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            begeleider_id TEXT REFERENCES users(eckid) ON DELETE SET NULL,
            aangemaakt    TEXT
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
            koppel_id  INTEGER NOT NULL REFERENCES pws_koppel(id)  ON DELETE CASCADE,
            auteur_id  TEXT    NOT NULL REFERENCES users(eckid)     ON DELETE CASCADE,
            tekst      TEXT    NOT NULL,
            aangemaakt TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_users_koppel ON users(koppel_id);
        CREATE INDEX IF NOT EXISTS idx_koppel_bg    ON pws_koppel(begeleider_id);
        CREATE INDEX IF NOT EXISTS idx_comm_koppel  ON pws_commentaar(koppel_id);
    """)
    conn.commit()
    conn.close()


# ── SSO-login ─────────────────────────────────────────────────────────────────

def sso_upsert_user(eckid: str, naam: str, rol: str, klas: str = None) -> dict:
    conn = get_conn()
    conn.execute("""
        INSERT INTO users (eckid, naam, rol, klas)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(eckid) DO UPDATE SET
            naam = excluded.naam,
            rol  = excluded.rol,
            klas = excluded.klas
    """, (eckid, naam, rol, klas))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE eckid = ?", (eckid,)).fetchone()
    conn.close()
    return dict(user)


def get_user_by_eckid(eckid: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE eckid = ?", (eckid,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Koppel-beheer ─────────────────────────────────────────────────────────────

def _create_koppel(conn) -> int:
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (NULL, datetime('now'))"
    )
    return cur.lastrowid


def _assign_to_koppel(conn, eckid: str, koppel_id: int) -> None:
    conn.execute("UPDATE users SET koppel_id = ? WHERE eckid = ?", (koppel_id, eckid))


def _leave_and_cleanup(conn, eckid: str) -> None:
    row = conn.execute("SELECT koppel_id FROM users WHERE eckid = ?", (eckid,)).fetchone()
    if not row or not row["koppel_id"]:
        return
    koppel_id = row["koppel_id"]
    conn.execute("UPDATE users SET koppel_id = NULL WHERE eckid = ?", (eckid,))
    remaining = conn.execute(
        "SELECT COUNT(*) FROM users WHERE koppel_id = ?", (koppel_id,)
    ).fetchone()[0]
    if remaining == 0:
        conn.execute("DELETE FROM pws_koppel WHERE id = ?", (koppel_id,))


def get_koppel_members(koppel_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users WHERE koppel_id = ?", (koppel_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_available_partners(eckid: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.* FROM users u
        WHERE u.rol = 'student'
          AND u.eckid != ?
          AND (
            u.koppel_id IS NULL
            OR (SELECT COUNT(*) FROM users u2 WHERE u2.koppel_id = u.koppel_id) < 2
          )
        ORDER BY u.naam
    """, (eckid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_partner(eckid: str, partner_eckid: str | None) -> None:
    conn = get_conn()
    try:
        me = conn.execute("SELECT * FROM users WHERE eckid = ?", (eckid,)).fetchone()
        if not me:
            raise ValueError("Gebruiker niet gevonden.")

        _leave_and_cleanup(conn, eckid)

        if partner_eckid is None:
            koppel_id = _create_koppel(conn)
            _assign_to_koppel(conn, eckid, koppel_id)
        else:
            partner = conn.execute(
                "SELECT * FROM users WHERE eckid = ?", (partner_eckid,)
            ).fetchone()
            if not partner:
                raise ValueError("Partner niet gevonden.")

            if partner["koppel_id"]:
                members = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE koppel_id = ?",
                    (partner["koppel_id"],)
                ).fetchone()[0]
                if members >= 2:
                    raise ValueError("Dit koppel zit al vol.")
                koppel_id = partner["koppel_id"]
            else:
                koppel_id = _create_koppel(conn)
                _assign_to_koppel(conn, partner_eckid, koppel_id)

            _assign_to_koppel(conn, eckid, koppel_id)

        conn.commit()
    finally:
        conn.close()


def _enrich_koppel(conn, koppel: dict) -> dict:
    import json as _json
    k = dict(koppel)
    leden = conn.execute(
        "SELECT * FROM users WHERE koppel_id = ?", (k["id"],)
    ).fetchall()
    k["leden"] = [dict(l) for l in leden]

    onderzoek = conn.execute(
        "SELECT * FROM pws_onderzoek WHERE koppel_id = ?", (k["id"],)
    ).fetchone()
    if onderzoek:
        o = dict(onderzoek)
        o["deelvragen"] = _json.loads(o.get("deelvragen_json") or "[]")
        k["onderzoek"] = o
    else:
        k["onderzoek"] = {
            "onderwerp": None, "vak": None, "hoofdvraag": None,
            "deelvragen": [], "bijgewerkt": None,
        }

    voortgang = conn.execute(
        "SELECT sleutel, voltooid FROM pws_voortgang WHERE koppel_id = ?", (k["id"],)
    ).fetchall()
    k["voortgang"] = {r["sleutel"]: bool(r["voltooid"]) for r in voortgang}
    return k


def get_koppel(koppel_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM pws_koppel WHERE id = ?", (koppel_id,)).fetchone()
    if not row:
        conn.close()
        return None
    result = _enrich_koppel(conn, dict(row))
    conn.close()
    return result


def get_my_koppel(eckid: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT koppel_id FROM users WHERE eckid = ?", (eckid,)).fetchone()
    if not row or not row["koppel_id"]:
        conn.close()
        return None
    koppel = conn.execute("SELECT * FROM pws_koppel WHERE id = ?", (row["koppel_id"],)).fetchone()
    if not koppel:
        conn.close()
        return None
    result = _enrich_koppel(conn, dict(koppel))
    conn.close()
    return result


def get_koppels_by_begeleider(begeleider_eckid: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM pws_koppel WHERE begeleider_id = ?", (begeleider_eckid,)
    ).fetchall()
    result = [_enrich_koppel(conn, dict(r)) for r in rows]
    conn.close()
    return result


def get_unclaimed_koppels() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM pws_koppel WHERE begeleider_id IS NULL"
    ).fetchall()
    result = [_enrich_koppel(conn, dict(r)) for r in rows]
    conn.close()
    return result


def claim_koppel(koppel_id: int, begeleider_eckid: str) -> None:
    """Race-condition safe: alleen claimen als nog niemand anders het heeft."""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE pws_koppel SET begeleider_id = ? WHERE id = ? AND begeleider_id IS NULL",
        (begeleider_eckid, koppel_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise ValueError("Dit koppel is net door een collega aangenomen.")


def release_koppel(koppel_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE pws_koppel SET begeleider_id = NULL WHERE id = ?", (koppel_id,)
    )
    conn.commit()
    conn.close()


# ── Onderzoek ─────────────────────────────────────────────────────────────────

def save_onderzoek(koppel_id: int, onderwerp: str, vak: str,
                   hoofdvraag: str, deelvragen: list[str]) -> None:
    conn = get_conn()
    conn.execute("""
        INSERT INTO pws_onderzoek
            (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(koppel_id) DO UPDATE SET
            onderwerp       = excluded.onderwerp,
            vak             = excluded.vak,
            hoofdvraag      = excluded.hoofdvraag,
            deelvragen_json = excluded.deelvragen_json,
            bijgewerkt      = excluded.bijgewerkt
    """, (koppel_id, onderwerp, vak, hoofdvraag, json.dumps(deelvragen)))
    conn.commit()
    conn.close()


def get_onderzoek(koppel_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pws_onderzoek WHERE koppel_id = ?", (koppel_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    r["deelvragen"] = json.loads(r["deelvragen_json"] or "[]")
    return r


# ── Voortgang ─────────────────────────────────────────────────────────────────

def set_voortgang(koppel_id: int, sleutel: str, voltooid: bool) -> None:
    conn = get_conn()
    conn.execute("""
        INSERT INTO pws_voortgang (koppel_id, sleutel, voltooid, gewijzigd)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(koppel_id, sleutel) DO UPDATE SET
            voltooid  = excluded.voltooid,
            gewijzigd = excluded.gewijzigd
    """, (koppel_id, sleutel, int(voltooid)))
    conn.commit()
    conn.close()


def get_voortgang(koppel_id: int) -> dict[str, bool]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT sleutel, voltooid FROM pws_voortgang WHERE koppel_id = ?", (koppel_id,)
    ).fetchall()
    conn.close()
    return {r["sleutel"]: bool(r["voltooid"]) for r in rows}


# ── Commentaar ────────────────────────────────────────────────────────────────

def add_commentaar(koppel_id: int, auteur_eckid: str, tekst: str) -> None:
    conn = get_conn()
    conn.execute("""
        INSERT INTO pws_commentaar (koppel_id, auteur_id, tekst, aangemaakt)
        VALUES (?, ?, ?, datetime('now'))
    """, (koppel_id, auteur_eckid, tekst))
    conn.commit()
    conn.close()


def get_commentaar(koppel_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, u.naam AS auteur_naam, u.rol AS auteur_rol
        FROM pws_commentaar c
        JOIN users u ON c.auteur_id = u.eckid
        WHERE c.koppel_id = ?
        ORDER BY c.aangemaakt DESC
    """, (koppel_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_commentaar(commentaar_id: int, auteur_eckid: str) -> None:
    conn = get_conn()
    conn.execute(
        "DELETE FROM pws_commentaar WHERE id = ? AND auteur_id = ?",
        (commentaar_id, auteur_eckid)
    )
    conn.commit()
    conn.close()


# ── Coordinator helpers ───────────────────────────────────────────────────────

def get_all_koppels_enriched() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM pws_koppel ORDER BY id").fetchall()
    result = [_enrich_koppel(conn, dict(r)) for r in rows]
    conn.close()
    return result


def get_all_koppels_with_info() -> list[dict]:
    conn = get_conn()
    koppels = conn.execute("SELECT * FROM pws_koppel ORDER BY aangemaakt").fetchall()
    result = []
    for k in koppels:
        k = dict(k)
        k["members"] = get_koppel_members(k["id"])
        k["onderzoek"] = get_onderzoek(k["id"])
        if k["begeleider_id"]:
            beg = conn.execute(
                "SELECT naam FROM users WHERE eckid = ?", (k["begeleider_id"],)
            ).fetchone()
            k["begeleider_naam"] = beg["naam"] if beg else "Onbekend"
        else:
            k["begeleider_naam"] = None
        result.append(k)
    conn.close()
    return result


# ── Simulatie (testdata) ──────────────────────────────────────────────────────

def wis_simulatie_data() -> int:
    """Verwijder alle gebruikers waarvan eckid begint met 'sim_'."""
    conn = get_conn()
    # Verwijder eerst koppels die alleen sim-gebruikers bevatten
    conn.execute("""
        DELETE FROM pws_koppel WHERE id NOT IN (
            SELECT DISTINCT koppel_id FROM users
            WHERE koppel_id IS NOT NULL AND eckid NOT LIKE 'sim_%'
        )
    """)
    verwijderd = conn.execute(
        "DELETE FROM users WHERE eckid LIKE 'sim_%'"
    ).rowcount
    conn.commit()
    conn.close()
    return verwijderd


def genereer_simulatie(n_havo4: int = 100, n_vwo5: int = 100) -> int:
    """
    Genereer n leerlingen per klas met koppels, onderwerpen en willekeurige voortgang.
    Geeft aantal aangemaakte koppels terug.
    """
    import random

    ONDERWERPEN = [
        ("Wiskunde B",       "De invloed van vleugelgeometrie op lift bij schaalmodellen",
         "Hoe beïnvloedt de vleugelgeometrie de liftkracht bij schaalmodellen?"),
        ("Wiskunde A",       "Statistisch onderzoek naar studiekeuze na havo",
         "Welke factoren bepalen de studiekeuze van havoleerlingen?"),
        ("Natuurkunde",      "Luchtwrijving en aerodynamica van fietsers",
         "Hoe groot is de luchtwrijving op een fietser bij verschillende houdingen?"),
        ("Scheikunde",       "Waterreiniging met actief kool",
         "Hoe effectief is actief kool bij het verwijderen van verontreinigingen uit water?"),
        ("Biologie",         "Microplastics in zoetwaterorganismen",
         "In hoeverre zijn microplastics aantoonbaar in zoetwaterorganismen in de omgeving?"),
        ("Economie",         "Prijselasticiteit van vliegtickets",
         "Hoe reageert de vraag naar vliegtickets op prijsveranderingen?"),
        ("Bedrijfseconomie (M&O)", "Duurzaamheid en winstgevendheid bij mkb",
         "Is er een verband tussen duurzame bedrijfsvoering en winst bij mkb-bedrijven?"),
        ("Aardrijkskunde",   "Hittestress in stedelijke gebieden",
         "In welke mate verschilt de temperatuur tussen binnenstad en buitenwijk op hete dagen?"),
        ("Geschiedenis",     "Propaganda in de Tweede Wereldoorlog",
         "Hoe werd propaganda in WOII ingezet en wat was het effect op de bevolking?"),
        ("Maatschappijwetenschappen", "Sociale media en politieke polarisatie",
         "In hoeverre dragen sociale media bij aan politieke polarisatie onder jongeren?"),
        ("Nederlands",       "Taalverandering door social media",
         "Hoe beïnvloedt het gebruik van social media de schrijftaal van jongeren?"),
        ("Engels",           "Anglicismen in het Nederlands",
         "In welke domeinen zijn Engelse leenwoorden het meest ingeburgerd in het Nederlands?"),
        ("Biologie",         "Antibioticaresistentie in de omgeving",
         "In welke mate is antibioticaresistentie aantoonbaar in oppervlaktewater?"),
        ("Scheikunde",       "Zonnebrandcrème en UV-absorptie",
         "Hoe effectief zijn verschillende zonnebrandcrèmes bij het absorberen van UV-straling?"),
        ("Natuurkunde",      "Zonnepanelen en opbrengst bij verschillende hoeken",
         "Bij welke hoek ten opzichte van de zon is de opbrengst van een zonnepaneel maximaal?"),
        ("Wiskunde B",       "Kansberekening in kaartspellen",
         "Hoe groot is de kans op bepaalde combinaties in populaire kaartspellen?"),
        ("Economie",         "Gamification en consumentengedrag",
         "In hoeverre beïnvloedt gamification het koopgedrag van consumenten?"),
        ("Aardrijkskunde",   "Grondwaterstand en droogte in Nederland",
         "Hoe heeft de grondwaterstand zich ontwikkeld in droge zomers sinds 2010?"),
        ("Maatschappijwetenschappen", "Ongelijkheid in het onderwijs",
         "In hoeverre hangt schoolprestatie samen met sociaaleconomische achtergrond in Nederland?"),
        ("Biologie",         "Effect van lichtkleur op plantengroei",
         "Welke lichtkleur heeft de meeste invloed op de groeisnelheid van spinazie?"),
    ]

    BEGELEIDER_NAMEN = [
        "Mevr. Troostwijk", "Dhr. van der Maas", "Mevr. Bakker",
        "Dhr. de Groot", "Mevr. Jansen", "Dhr. Visser",
        "Mevr. Hendriks", "Dhr. Peters", "Mevr. Smit",
        "Dhr. van Dijk",
    ]

    VOORTGANG_SLEUTELS = ["plan_van_aanpak", "concept", "definitief", "presentatie"]

    NAMEN_H4 = [
        "Emma Jansen", "Noah Smit", "Lotte Bakker", "Sven Meijer", "Julia van den Berg",
        "Lars Visser", "Sophie de Groot", "Tim Hendriks", "Anna Mulder", "Bas Peters",
        "Eva Janssen", "Luuk de Vries", "Kim Bosman", "Max van Dijk", "Sara Kok",
        "Finn Jacobs", "Nora Brouwer", "Daan Vermeer", "Iris Dekker", "Ruben van Leeuwen",
        "Fleur Willems", "Milan Hoekstra", "Lisa Timmermans", "Jesse van der Laan",
        "Amber Kuiper", "Thijs Bos", "Roos Scholten", "Sam Vos", "Bo Martens", "Jade Nijhof",
        "Cas Huisman", "Fenna van Rijn", "Stef Bergman", "Floor van Os", "Pim Lammers",
        "Noor Schouten", "Owen Blom", "Merel Verhoeven", "Bram Schipper", "Eline Postma",
        "Ties van Houten", "Sofie Dijkstra", "Julian Manders", "Vera Steenbeek", "Joep Aarts",
        "Lena Fontein", "Rick Groothuis", "Mila Oost", "Wouter Kuijpers", "Nina de Boer",
        "Arjan Mol", "Tessa van Ee", "Koen Hartman", "Sien Franssen", "Gijs Verburg",
        "Lara Hubers", "Mats Joosten", "Fien van Leeuwen", "Quinten Blom", "Hanna Rijken",
        "Tom Gerritsen", "Anouk Claassen", "Bas Vermeulen", "Lot van Dam", "Stijn Huizinga",
        "Kirra van Eck", "Hugo Brands", "Manon Bakker", "Remi Vos", "Bo van der Heijden",
        "Isa Roos", "Floris Smeets", "Tine van Hout", "Jelle Pieters", "Zara van Beek",
        "Niels Kosten", "Elke Brons", "Joris Linden", "Maud Westra", "Lars van Zanten",
        "Fay Arendse", "Bram de Bruin", "Lien Veldman", "Dani Hugen", "Cato Boer",
        "Sander Prins", "Loes van Ommen", "Tijs Brink", "Janne Beekhof", "Rick Moes",
        "Lina van Wijnen", "Niek Slot", "Evie van der Wal", "Mus Kaya", "Ilse Kooij",
        "Pieter van Loon", "Demi Broers", "Tycho van Mil", "Sofie Koster", "Luc Verhoef",
        "Amy Scholte", "Hidde van Elk", "Pia Heins", "Teun Oomen", "Lisa Brands",
    ]

    NAMEN_V5 = [
        "Alexander van Rijn", "Valentina Rossi", "Michiel de Jong", "Laure van Pelt",
        "Thomas Bergmans", "Charlotte Vos", "Finn van der Berg", "Isabel Kuijper",
        "Bas Wolters", "Vera van Oss", "Niels Hendriks", "Maud Smeets", "Joost van Dam",
        "Eline Bos", "Thom Kerkhof", "Mila Stam", "Rik Janssen", "Noor van Dijk",
        "Guus de Haas", "Lisa Brouwer", "Bram van Leeuwen", "Roos Mulder", "Lars Dijkman",
        "Floor van den Brink", "Tim de Ruiter", "Zoë van Vliet", "Mark Hendriksen",
        "Anne van Schaik", "Pieter Loos", "Fleur Snijders", "Ruben van den Berg",
        "Emma Scholten", "Jasper Kooij", "Nina van der Laan", "Wouter Brons",
        "Sanne Teunissen", "David van Beek", "Lot Groenewegen", "Stefan de Vos",
        "Hanna Oosterbeek", "Jeroen van Dongen", "Tessa Vermeulen", "Koen van Elk",
        "Anouk Dijkstra", "Tijmen Bruins", "Vera Verhoeven", "Sven van Egmond",
        "Lena Bosch", "Daan van Laar", "Sophie Hoekstra", "Julian Meijer",
        "Roos van der Heijden", "Luk Brands", "Iris van Beusekom", "Victor Smit",
        "Amy van der Burg", "Maarten Kok", "Nienke Koster", "Bart van der Velden",
        "Elise Hendrix", "Joep van Zanten", "Merel de Waal", "Stijn Pieters",
        "Fien van Houten", "Aryan Bakker", "Lien van de Berg", "Quincy Veldman",
        "Manon van Elk", "Hugo Aarts", "Kim van der Aa", "Tom Claassen",
        "Lisa van Eck", "Ries Gerritsen", "Bo van Hout", "Gijs van Eijk",
        "Noor van Beusekom", "Jelle van Rijn", "Sofie Pietersma", "Lars van Elk",
        "Maud van den Hoek", "Sander van Loon", "Iris Brands", "Demi Jacobs",
        "Joris van Ommen", "Cato van Mil", "Rick Snijder", "Evie Postma",
        "Nick Verhoeven", "Lina de Bruin", "Mats Boer", "Janne van Beek",
        "Teun Bakkers", "Loes Linden", "Pim Oosterlo", "Vera van Dongen",
        "Floris Beekhof", "Isa Wolfs", "Remi van Oss", "Bo Stam",
        "Bram van der Waal", "Emma Kerkhof", "Luuk Teunissen", "Nora Bergmans",
    ]

    conn = get_conn()

    # Maak begeleiders aan
    begeleider_eckids = []
    for i, naam in enumerate(BEGELEIDER_NAMEN):
        eckid = f"sim_beg_{i:02d}"
        conn.execute("""
            INSERT INTO users (eckid, naam, rol)
            VALUES (?, ?, 'begeleider')
            ON CONFLICT(eckid) DO UPDATE SET naam=excluded.naam, rol=excluded.rol
        """, (eckid, naam))
        begeleider_eckids.append(eckid)

    conn.commit()
    n_koppels = 0

    def maak_koppels(namen, klas, prefix):
        nonlocal n_koppels
        random.shuffle(namen)
        i = 0
        while i < len(namen):
            # Wissel af: solo of paar (30% solo, 70% paar)
            solo = random.random() < 0.3 or i == len(namen) - 1
            leden = [namen[i]] if solo else [namen[i], namen[i+1]]

            # Koppel aanmaken
            cur = conn.execute(
                "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (NULL, datetime('now'))"
            )
            koppel_id = cur.lastrowid

            # Leerlingen aanmaken en koppelen
            for j, naam in enumerate(leden):
                eckid = f"sim_{prefix}_{i+j:03d}"
                conn.execute("""
                    INSERT INTO users (eckid, naam, rol, koppel_id, klas)
                    VALUES (?, ?, 'student', ?, ?)
                    ON CONFLICT(eckid) DO UPDATE SET
                        naam=excluded.naam, koppel_id=excluded.koppel_id, klas=excluded.klas
                """, (eckid, naam, koppel_id, klas))

            # Begeleider toewijzen (80% kans)
            if random.random() < 0.8:
                beg_eckid = random.choice(begeleider_eckids)
                conn.execute(
                    "UPDATE pws_koppel SET begeleider_id=? WHERE id=?",
                    (beg_eckid, koppel_id)
                )

            # Onderzoek (85% kans)
            if random.random() < 0.85:
                ond = random.choice(ONDERWERPEN)
                conn.execute("""
                    INSERT OR IGNORE INTO pws_onderzoek
                        (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
                    VALUES (?, ?, ?, ?, '[]', datetime('now'))
                """, (koppel_id, ond[1], ond[0], ond[2]))

            # Voortgang (random subset van deadlines)
            n_voltooid = random.randint(0, len(VOORTGANG_SLEUTELS))
            for sleutel in VOORTGANG_SLEUTELS[:n_voltooid]:
                conn.execute("""
                    INSERT OR IGNORE INTO pws_voortgang (koppel_id, sleutel, voltooid, gewijzigd)
                    VALUES (?, ?, 1, datetime('now'))
                """, (koppel_id, sleutel))

            n_koppels += 1
            i += len(leden)

    maak_koppels(NAMEN_H4[:n_havo4], "havo4", "h4")
    maak_koppels(NAMEN_V5[:n_vwo5], "vwo5",  "v5")

    conn.commit()
    conn.close()
    return n_koppels
