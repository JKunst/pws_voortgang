"""Coördinator-weergave: overzicht van alle koppels met begeleider, vak, onderwerp."""

from datetime import date

import pandas as pd
import streamlit as st

import db
from pws_data import MIJLPALEN, SCHOOLJAAR
from tijdlijn import render_status_cards, render_tijdlijn


def render_coordinator(user: dict) -> None:
    st.title(f"Coördinator-overzicht {SCHOOLJAAR}")
    st.caption(user["naam"])

    vandaag = date.today()
    render_tijdlijn(vandaag)
    render_status_cards(vandaag)

    alle_koppels = _fetch_all_koppels()
    if not alle_koppels:
        st.info("Er zijn nog geen koppels aangemaakt.")
        return

    _render_stats(alle_koppels, vandaag)
    st.divider()
    _render_tabel(alle_koppels, vandaag)


# ===================== Data =====================

def _fetch_all_koppels() -> list[dict]:
    """Haal alle koppels op (zowel met als zonder begeleider)."""
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT id FROM pws_koppel ORDER BY id").fetchall()
    finally:
        conn.close()
    return [db.get_koppel(r["id"]) for r in rows]


def _bepaal_status(k: dict, vandaag: date) -> str:
    verstreken = [m for m in MIJLPALEN if m["sleutel"] and m["datum"] <= vandaag]
    has_ond = bool(k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"])
    done_passed = sum(1 for m in verstreken if k["voortgang"].get(m["sleutel"]))

    if not has_ond:
        return "Onderzoek niet ingevuld"
    if done_passed < len(verstreken):
        return f"Achter ({done_passed}/{len(verstreken)} deadlines)"
    return "Op schema"


def _begeleider_naam(begeleider_id: int | None) -> str:
    if begeleider_id is None:
        return "— (nog geen begeleider)"
    user = db.get_user_by_id(begeleider_id)
    return user["naam"] if user else "— (onbekend)"


# ===================== Stats =====================

def _render_stats(koppels: list[dict], vandaag: date) -> None:
    totaal = len(koppels)
    met_bg = sum(1 for k in koppels if k["begeleider_id"] is not None)
    zonder_bg = totaal - met_bg
    solo = sum(1 for k in koppels if len(k["leden"]) == 1)
    paren = totaal - solo
    met_ond = sum(
        1 for k in koppels
        if k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"]
    )
    achter = sum(
        1 for k in koppels
        if _bepaal_status(k, vandaag).startswith("Achter")
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Koppels", totaal)
    c2.metric("Paren", paren)
    c3.metric("Solo", solo)
    c4.metric("Met begeleider", met_bg)
    c5.metric("Zonder begeleider", zonder_bg)
    c6.metric("Achter op schema", achter)

    if met_ond < totaal:
        st.caption(
            f"{totaal - met_ond} van de {totaal} koppels hebben hun onderzoek "
            "nog niet (volledig) ingevuld."
        )


# ===================== Tabel =====================

def _render_tabel(koppels: list[dict], vandaag: date) -> None:
    st.subheader("Alle koppels")

    # Bouw rijen op voor het dataframe
    rijen = []
    for k in koppels:
        leden = k["leden"]
        ond = k["onderzoek"]
        naam_str = " & ".join(m["naam"] for m in leden) or "(leeg koppel)"
        klas_set = sorted({m.get("klas") or "?" for m in leden})
        rijen.append({
            "Koppel": naam_str,
            "Klas": ", ".join(klas_set),
            "Vak": ond["vak"] or "— (nog niet gekozen)",
            "Onderwerp": ond["onderwerp"] or "— (nog niet ingevuld)",
            "Begeleider": _begeleider_naam(k["begeleider_id"]),
            "Status": _bepaal_status(k, vandaag),
            "Type": "Solo" if len(leden) == 1 else "Paar",
        })
    df = pd.DataFrame(rijen)

    # Filters
    cf1, cf2, cf3 = st.columns(3)
    with cf1:
        vak_opties = ["Alle"] + sorted(df["Vak"].unique().tolist())
        vak_keuze = st.selectbox("Vak", vak_opties, key="coord_vak")
    with cf2:
        bg_opties = ["Alle"] + sorted(df["Begeleider"].unique().tolist())
        bg_keuze = st.selectbox("Begeleider", bg_opties, key="coord_bg")
    with cf3:
        status_opties = ["Alle", "Op schema", "Achter", "Onderzoek niet ingevuld"]
        status_keuze = st.selectbox("Status", status_opties, key="coord_status")

    zoek = st.text_input(
        "Zoeken (koppel, onderwerp)", key="coord_zoek"
    ).strip().lower()

    # Filtering
    mask = pd.Series([True] * len(df))
    if vak_keuze != "Alle":
        mask &= df["Vak"] == vak_keuze
    if bg_keuze != "Alle":
        mask &= df["Begeleider"] == bg_keuze
    if status_keuze == "Achter":
        mask &= df["Status"].str.startswith("Achter")
    elif status_keuze == "Op schema":
        mask &= df["Status"] == "Op schema"
    elif status_keuze == "Onderzoek niet ingevuld":
        mask &= df["Status"] == "Onderzoek niet ingevuld"
    if zoek:
        hay = (df["Koppel"] + " " + df["Onderwerp"]).str.lower()
        mask &= hay.str.contains(zoek, regex=False)

    gefilterd = df[mask].reset_index(drop=True)
    st.caption(f"{len(gefilterd)} van {len(df)} koppels getoond.")

    st.dataframe(
        gefilterd,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Koppel":     st.column_config.TextColumn(width="medium"),
            "Klas":       st.column_config.TextColumn(width="small"),
            "Vak":        st.column_config.TextColumn(width="medium"),
            "Onderwerp":  st.column_config.TextColumn(width="large"),
            "Begeleider": st.column_config.TextColumn(width="medium"),
            "Status":     st.column_config.TextColumn(width="small"),
            "Type":       st.column_config.TextColumn(width="small"),
        },
    )

    # CSV-export
    csv = gefilterd.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Exporteer selectie als CSV",
        data=csv,
        file_name=f"pws_koppels_{SCHOOLJAAR}.csv",
        mime="text/csv",
    )
