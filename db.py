"""
db.py — SQLite helpers voor de PWS-app.

Primaire sleutel: ECK-iD (via portaal-token).
Geen wachtwoorden, geen gebruikersnamen.

Datamodel:
    users         — leerlingen, begeleiders, coordinatoren (ECK-iD als PK)
    pws_koppel    — groep van 1 of 2 leerlingen, optioneel gekoppeld aan begeleider
    pws_onderzoek — onderwerp/vak/hoofdvraag/deelvragen per koppel
    pws_voortgang — afgevinkte deadlines per koppel
    pws_commentaar — feedback van begeleider aan koppel
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
    if not DB_PATH.exists():
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
    """
    Sla gebruiker op na SSO-login via portaal-token.
    Maakt aan als nieuw, updatet naam/klas als bestaand.
    Rol wordt altijd overschreven vanuit het token (beheerd door portaal).
    """
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
    """Leerlingen zonder koppel of in een koppel met maar 1 lid (niet de aanvrager zelf)."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.* FROM users u
        WHERE u.rol = 'student'
          AND u.eckid != ?
          AND (
            u.koppel_id IS NULL
            OR (
              SELECT COUNT(*) FROM users u2 WHERE u2.koppel_id = u.koppel_id
            ) < 2
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
            return

        _leave_and_cleanup(conn, eckid)

        if partner_eckid is None:
            koppel_id = _create_koppel(conn)
            _assign_to_koppel(conn, eckid, koppel_id)
        else:
            partner = conn.execute(
                "SELECT * FROM users WHERE eckid = ?", (partner_eckid,)
            ).fetchone()
            if not partner:
                return

            if partner["koppel_id"]:
                members = conn.execute(
                    "SELECT COUNT(*) FROM users WHERE koppel_id = ?",
                    (partner["koppel_id"],)
                ).fetchone()[0]
                if members >= 2:
                    return
                koppel_id = partner["koppel_id"]
            else:
                koppel_id = _create_koppel(conn)
                _assign_to_koppel(conn, partner_eckid, koppel_id)

            _assign_to_koppel(conn, eckid, koppel_id)

        conn.commit()
    finally:
        conn.close()




def _enrich_koppel(conn, koppel: dict) -> dict:
    """Verrijk een koppel-rij met leden, onderzoek en voortgang."""
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
    conn = get_conn()
    conn.execute(
        "UPDATE pws_koppel SET begeleider_id = ? WHERE id = ?",
        (begeleider_eckid, koppel_id)
    )
    conn.commit()
    conn.close()


def release_koppel(koppel_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE pws_koppel SET begeleider_id = NULL WHERE id = ?", (koppel_id,)
    )
    conn.commit()
    conn.close()


# ── Onderzoek ─────────────────────────────────────────────────────────────────

def save_onderzoek(
    koppel_id: int,
    onderwerp: str,
    vak: str,
    hoofdvraag: str,
    deelvragen: list[str],
) -> None:
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


# ── Overzicht voor coordinator ────────────────────────────────────────────────

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


# ── Coordinator helpers ───────────────────────────────────────────────────────

def get_all_koppels_enriched() -> list[dict]:
    """Alle koppels verrijkt met leden, onderzoek en voortgang."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM pws_koppel ORDER BY id").fetchall()
    result = [_enrich_koppel(conn, dict(r)) for r in rows]
    conn.close()
    return result
