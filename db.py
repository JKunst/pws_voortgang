"""SQLite-helpers voor de PWS-app.

Datamodel:
    users
        begeleiders en leerlingen; elke leerling zit in een pws_koppel.
    pws_koppel
        groep van 1 of 2 leerlingen. Eventueel gekoppeld aan een begeleider.
    pws_onderzoek
        onderwerp/vak/hoofdvraag/deelvragen, één rij per koppel (partners delen).
    pws_voortgang
        afgevinkte deadlines, per koppel.
    pws_commentaar
        feedback van begeleider aan koppel (thread, nieuwste bovenaan).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "pws.db"


# ========== Connectie ==========

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db() -> None:
    if DB_PATH.exists():
        return
    from init_db import initialize
    initialize()


# ========== Wachtwoorden ==========

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + h.hex()


def check_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return h.hex() == hash_hex
    except Exception:
        return False


# ========== Gebruikers ==========

def get_user_by_username(username: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ========== Koppel-beheer ==========

def _create_koppel(conn) -> int:
    cur = conn.execute(
        "INSERT INTO pws_koppel (begeleider_id, aangemaakt) VALUES (NULL, datetime('now'))"
    )
    return cur.lastrowid


def _assign_to_koppel(conn, student_id: int, koppel_id: int) -> None:
    conn.execute("UPDATE users SET koppel_id = ? WHERE id = ?", (koppel_id, student_id))


def _leave_and_cleanup(conn, student_id: int) -> None:
    """Haal student uit huidige koppel; verwijder het koppel als het leeg achterblijft."""
    row = conn.execute(
        "SELECT koppel_id FROM users WHERE id = ?", (student_id,)
    ).fetchone()
    if not row or row["koppel_id"] is None:
        return
    kid = row["koppel_id"]
    conn.execute("UPDATE users SET koppel_id = NULL WHERE id = ?", (student_id,))
    nog_leden = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE koppel_id = ?", (kid,)
    ).fetchone()["n"]
    if nog_leden == 0:
        conn.execute("DELETE FROM pws_koppel WHERE id = ?", (kid,))


def get_koppel_members(koppel_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM users WHERE koppel_id = ? ORDER BY naam", (koppel_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_available_partners(student_id: int) -> list[dict]:
    """Leerlingen die als partner gekozen kunnen worden:
    - solo (eigen koppel met alleen zichzelf) of zonder koppel
    - óf al gekoppeld aan deze leerling zelf
    Uitgesloten: de leerling zelf, leerlingen die al met iemand anders zijn gekoppeld.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT u.* FROM users u
            WHERE u.rol = 'student'
              AND u.id != ?
              AND (
                u.koppel_id IS NULL
                OR (
                  SELECT COUNT(*) FROM users u2
                  WHERE u2.koppel_id = u.koppel_id AND u2.id != u.id AND u2.id != ?
                ) = 0
              )
            ORDER BY u.naam
            """,
            (student_id, student_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_partner(student_id: int, partner_id: int | None) -> None:
    """Koppel leerling aan partner, of maak zelfstandig (solo) koppel aan.

    Semantiek:
    - partner_id=None: leerling komt in eigen (solo) koppel.
    - partner_id=X: leerling komt samen met X in een koppel.
      X moet vrij zijn (solo of geen koppel).

    Bij koppel-wissel blijven bestaande onderzoeks- en voortgangsgegevens achter bij
    het oude koppel (dus bij de eventuele andere partner die daar nog zit). Als het
    oude koppel leeg achterblijft, wordt het verwijderd inclusief alle data.
    """
    conn = get_conn()
    try:
        student = conn.execute(
            "SELECT * FROM users WHERE id = ?", (student_id,)
        ).fetchone()
        if student is None:
            raise ValueError("Leerling bestaat niet.")
        huidig_kid = student["koppel_id"]

        # Solo
        if partner_id is None:
            if huidig_kid is not None:
                n = conn.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE koppel_id = ?",
                    (huidig_kid,),
                ).fetchone()["n"]
                if n == 1:
                    conn.commit()
                    return
            _leave_and_cleanup(conn, student_id)
            new_kid = _create_koppel(conn)
            _assign_to_koppel(conn, student_id, new_kid)
            conn.commit()
            return

        # Partner opgegeven
        partner = conn.execute(
            "SELECT * FROM users WHERE id = ?", (partner_id,)
        ).fetchone()
        if partner is None or partner["rol"] != "student":
            raise ValueError("Ongeldige partner.")

        partner_kid = partner["koppel_id"]

        # Al samen?
        if partner_kid is not None and partner_kid == huidig_kid:
            leden = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE koppel_id = ?",
                (huidig_kid,),
            ).fetchone()["n"]
            if leden == 2:
                conn.commit()
                return

        # Partner beschikbaar?
        if partner_kid is not None:
            anderen = conn.execute(
                "SELECT id FROM users WHERE koppel_id = ? AND id != ?",
                (partner_kid, partner_id),
            ).fetchall()
            andere_ids = [r["id"] for r in anderen]
            if andere_ids and andere_ids != [student_id]:
                raise ValueError(f"{partner['naam']} is al gekoppeld aan een andere leerling.")

        # Voer de koppeling uit
        _leave_and_cleanup(conn, student_id)
        if partner_kid is not None:
            _assign_to_koppel(conn, student_id, partner_kid)
        else:
            new_kid = _create_koppel(conn)
            _assign_to_koppel(conn, student_id, new_kid)
            _assign_to_koppel(conn, partner_id, new_kid)
        conn.commit()
    finally:
        conn.close()


def get_koppel(koppel_id: int) -> dict | None:
    """Koppel met leden, begeleider-id, onderzoek (als dict), voortgang (als dict)."""
    conn = get_conn()
    try:
        k = conn.execute(
            "SELECT * FROM pws_koppel WHERE id = ?", (koppel_id,)
        ).fetchone()
        if k is None:
            return None
        leden = conn.execute(
            "SELECT * FROM users WHERE koppel_id = ? ORDER BY naam", (koppel_id,)
        ).fetchall()

        ond_row = conn.execute(
            "SELECT * FROM pws_onderzoek WHERE koppel_id = ?", (koppel_id,)
        ).fetchone()
        if ond_row is None:
            onderzoek = {
                "onderwerp": "", "vak": "", "hoofdvraag": "",
                "deelvragen": [], "bijgewerkt": None,
            }
        else:
            d = dict(ond_row)
            try:
                d["deelvragen"] = json.loads(d.pop("deelvragen_json") or "[]")
            except Exception:
                d["deelvragen"] = []
            onderzoek = d

        vrows = conn.execute(
            "SELECT sleutel, voltooid FROM pws_voortgang WHERE koppel_id = ?",
            (koppel_id,),
        ).fetchall()
        voortgang = {r["sleutel"]: bool(r["voltooid"]) for r in vrows}

        return {
            "id": koppel_id,
            "begeleider_id": k["begeleider_id"],
            "aangemaakt": k["aangemaakt"],
            "leden": [dict(r) for r in leden],
            "onderzoek": onderzoek,
            "voortgang": voortgang,
        }
    finally:
        conn.close()


def get_my_koppel(student_id: int) -> dict | None:
    user = get_user_by_id(student_id)
    if not user or not user.get("koppel_id"):
        return None
    return get_koppel(user["koppel_id"])


def get_koppels_by_begeleider(begeleider_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id FROM pws_koppel WHERE begeleider_id = ? ORDER BY id",
            (begeleider_id,),
        ).fetchall()
    finally:
        conn.close()
    return [get_koppel(r["id"]) for r in rows]


def get_unclaimed_koppels() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id FROM pws_koppel WHERE begeleider_id IS NULL ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [get_koppel(r["id"]) for r in rows]


def claim_koppel(koppel_id: int, begeleider_id: int) -> None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT begeleider_id FROM pws_koppel WHERE id = ?", (koppel_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Koppel bestaat niet.")
        if row["begeleider_id"] is not None and row["begeleider_id"] != begeleider_id:
            raise ValueError("Dit koppel heeft al een andere begeleider.")
        conn.execute(
            "UPDATE pws_koppel SET begeleider_id = ? WHERE id = ?",
            (begeleider_id, koppel_id),
        )
        conn.commit()
    finally:
        conn.close()


def release_koppel(koppel_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE pws_koppel SET begeleider_id = NULL WHERE id = ?", (koppel_id,)
        )
        conn.commit()
    finally:
        conn.close()


# ========== Onderzoek (per koppel) ==========

def save_onderzoek(
    koppel_id: int,
    onderwerp: str,
    vak: str,
    hoofdvraag: str,
    deelvragen: list[str],
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pws_onderzoek
              (koppel_id, onderwerp, vak, hoofdvraag, deelvragen_json, bijgewerkt)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(koppel_id) DO UPDATE SET
              onderwerp       = excluded.onderwerp,
              vak             = excluded.vak,
              hoofdvraag      = excluded.hoofdvraag,
              deelvragen_json = excluded.deelvragen_json,
              bijgewerkt      = excluded.bijgewerkt
            """,
            (
                koppel_id, onderwerp, vak, hoofdvraag,
                json.dumps(deelvragen, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ========== Voortgang (per koppel) ==========

def set_voortgang(koppel_id: int, sleutel: str, voltooid: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pws_voortgang (koppel_id, sleutel, voltooid, gewijzigd)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(koppel_id, sleutel) DO UPDATE SET
              voltooid  = excluded.voltooid,
              gewijzigd = excluded.gewijzigd
            """,
            (koppel_id, sleutel, int(voltooid)),
        )
        conn.commit()
    finally:
        conn.close()


# ========== Commentaar (feedback van begeleider) ==========

def add_commentaar(koppel_id: int, auteur_id: int, tekst: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO pws_commentaar (koppel_id, auteur_id, tekst, aangemaakt)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (koppel_id, auteur_id, tekst),
        )
        conn.commit()
    finally:
        conn.close()


def get_commentaar(koppel_id: int) -> list[dict]:
    """Nieuwste eerst."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.tekst, c.aangemaakt, u.naam AS auteur_naam, u.rol AS auteur_rol
            FROM pws_commentaar c
            JOIN users u ON u.id = c.auteur_id
            WHERE c.koppel_id = ?
            ORDER BY c.aangemaakt DESC, c.id DESC
            """,
            (koppel_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_commentaar(commentaar_id: int, auteur_id: int) -> None:
    """Alleen de auteur mag zijn/haar commentaar verwijderen."""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM pws_commentaar WHERE id = ? AND auteur_id = ?",
            (commentaar_id, auteur_id),
        )
        conn.commit()
    finally:
        conn.close()


# ========== SSO-koppeling ==========

def migrate_add_email() -> None:
    """Voeg email-kolom toe als die nog niet bestaat (eenmalige migratie)."""
    conn = get_conn()
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.commit()
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    """Zoek gebruiker op via e-mailadres (voor SSO-login)."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def sso_of_maak_student(email: str, naam: str, leerlingnummer: str) -> dict | None:
    """
    Zoek student op via email. Geeft None als de student niet bestaat —
    beheerder moet student eerst aanmaken in de PWS-app.
    """
    return get_user_by_email(email)
