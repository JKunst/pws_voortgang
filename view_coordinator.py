"""Coördinator-weergave: overzicht van alle koppels + simulatieknop."""

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

    # Simulatieknop bovenaan — alleen zichtbaar als er weinig data is
    _render_simulatie_sectie()

    alle_koppels = _fetch_all_koppels()
    if not alle_koppels:
        st.info("Er zijn nog geen koppels aangemaakt. Gebruik de simulatieknop hierboven om testdata te laden.")
        return

    _render_stats(alle_koppels, vandaag)
    st.divider()
    _render_tabel(alle_koppels, vandaag)


# ===================== Simulatie =====================

def _render_simulatie_sectie() -> None:
    with st.expander("🧪 Simulatie — testdata genereren", expanded=False):
        st.caption(
            "Genereer nep-leerlingen om de app te testen met een realistische hoeveelheid data. "
            "Simulatiedata heeft ECK-iDs die beginnen met 'sim_' en is los te wissen."
        )

        n_sim = db.get_conn().execute(
            "SELECT COUNT(*) FROM users WHERE eckid LIKE 'sim_%'"
        ).fetchone()[0]

        if n_sim > 0:
            st.info(f"Er zijn momenteel **{n_sim} simulatieleerlingen** in de database.")
            if st.button("🗑 Wis alle simulatiedata", type="secondary"):
                verwijderd = db.wis_simulatie_data()
                st.success(f"{verwijderd} simulatiegebruikers verwijderd.")
                st.rerun()
            st.divider()

        col1, col2 = st.columns(2)
        n_havo4 = col1.number_input("Havo 4 leerlingen", min_value=10, max_value=100,
                                     value=100, step=10)
        n_vwo5  = col2.number_input("VWO 5 leerlingen",  min_value=10, max_value=100,
                                     value=100, step=10)

        if st.button("⚡ Genereer simulatiedata", type="primary", use_container_width=True):
            with st.spinner("Data genereren..."):
                n_koppels = db.genereer_simulatie(int(n_havo4), int(n_vwo5))
            st.success(
                f"✅ {int(n_havo4) + int(n_vwo5)} leerlingen aangemaakt in "
                f"{n_koppels} koppels (mix van solo en paren, havo4 en vwo5)."
            )
            st.rerun()


# ===================== Data =====================

def _fetch_all_koppels() -> list[dict]:
    return db.get_all_koppels_enriched()


def _bepaal_status(k: dict, vandaag: date) -> str:
    verstreken = [m for m in MIJLPALEN if m["sleutel"] and m["datum"] <= vandaag]
    has_ond = bool(k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"])
    done_passed = sum(1 for m in verstreken if k["voortgang"].get(m["sleutel"]))

    if not has_ond:
        return "Onderzoek niet ingevuld"
    if done_passed < len(verstreken):
        return f"Achter ({done_passed}/{len(verstreken)} deadlines)"
    return "Op schema"


def _begeleider_naam(begeleider_id: str | None) -> str:
    if begeleider_id is None:
        return "— (nog geen begeleider)"
    user = db.get_user_by_eckid(begeleider_id)
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

    rijen = []
    for k in koppels:
        leden = k["leden"]
        ond = k["onderzoek"]
        naam_str = " & ".join(m["naam"] for m in leden) or "(leeg koppel)"
        klas_set = sorted({m.get("klas") or "?" for m in leden})
        rijen.append({
            "Koppel":     naam_str,
            "Klas":       ", ".join(klas_set),
            "Vak":        ond["vak"] or "— (nog niet gekozen)",
            "Onderwerp":  ond["onderwerp"] or "— (nog niet ingevuld)",
            "Begeleider": _begeleider_naam(k["begeleider_id"]),
            "Status":     _bepaal_status(k, vandaag),
            "Type":       "Solo" if len(leden) == 1 else "Paar",
        })
    df = pd.DataFrame(rijen)

    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        vak_opties = ["Alle"] + sorted(df["Vak"].unique().tolist())
        vak_keuze = st.selectbox("Vak", vak_opties, key="coord_vak")
    with cf2:
        bg_opties = ["Alle"] + sorted(df["Begeleider"].unique().tolist())
        bg_keuze = st.selectbox("Begeleider", bg_opties, key="coord_bg")
    with cf3:
        status_opties = ["Alle", "Op schema", "Achter", "Onderzoek niet ingevuld"]
        status_keuze = st.selectbox("Status", status_opties, key="coord_status")
    with cf4:
        klas_opties = ["Alle"] + sorted(df["Klas"].unique().tolist())
        klas_keuze = st.selectbox("Klas", klas_opties, key="coord_klas")

    zoek = st.text_input("Zoeken (koppel, onderwerp)", key="coord_zoek").strip().lower()

    mask = pd.Series([True] * len(df))
    if vak_keuze != "Alle":
        mask &= df["Vak"] == vak_keuze
    if bg_keuze != "Alle":
        mask &= df["Begeleider"] == bg_keuze
    if status_keuze == "Achter":
        mask &= df["Status"].str.startswith("Achter")
    elif status_keuze != "Alle":
        mask &= df["Status"] == status_keuze
    if klas_keuze != "Alle":
        mask &= df["Klas"].str.contains(klas_keuze, regex=False)
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

    csv = gefilterd.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Exporteer selectie als CSV",
        data=csv,
        file_name=f"pws_koppels_{SCHOOLJAAR}.csv",
        mime="text/csv",
    )
