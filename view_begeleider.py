"""Begeleider-dashboard: mijn koppels + beschikbare koppels + feedback schrijven."""

from datetime import date

import streamlit as st

import db
from pws_data import MIJLPALEN, SCHOOLJAAR
from tijdlijn import render_status_cards, render_tijdlijn


def render_begeleider(user: dict) -> None:
    st.title(f"Begeleider-dashboard {SCHOOLJAAR}")
    st.caption(user["naam"])

    vandaag = date.today()
    render_tijdlijn(vandaag)
    render_status_cards(vandaag)

    eigen = db.get_koppels_by_begeleider(user["eckid"])
    beschikbaar = db.get_unclaimed_koppels()

    tab_mijn, tab_beschikbaar = st.tabs([
        f"Mijn koppels ({len(eigen)})",
        f"Beschikbare koppels ({len(beschikbaar)})",
    ])
    with tab_mijn:
        _tab_mijn_koppels(user, eigen, vandaag)
    with tab_beschikbaar:
        _tab_beschikbare_koppels(user, beschikbaar)


# ===================== Mijn koppels =====================

def _tab_mijn_koppels(user: dict, koppels: list[dict], vandaag: date) -> None:
    if not koppels:
        st.info(
            "Je hebt nog geen koppels. Kijk bij **Beschikbare koppels** om er "
            "een of meer aan te nemen."
        )
        return

    verstreken_deadlines = [
        m for m in MIJLPALEN if m["sleutel"] and m["datum"] <= vandaag
    ]
    alle_deadlines = [m for m in MIJLPALEN if m["sleutel"]]

    totaal = len(koppels)
    met_onderzoek = sum(
        1 for k in koppels
        if k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"]
    )
    achter = sum(
        1 for k in koppels
        if sum(1 for m in verstreken_deadlines if k["voortgang"].get(m["sleutel"]))
           < len(verstreken_deadlines)
    )
    compleet = sum(
        1 for k in koppels
        if sum(1 for m in alle_deadlines if k["voortgang"].get(m["sleutel"]))
           == len(alle_deadlines)
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Koppels totaal", totaal)
    c2.metric("Onderzoek ingevuld", f"{met_onderzoek} / {totaal}")
    c3.metric("Achter op schema", achter)
    c4.metric("Alle deadlines af", compleet)

    st.subheader("Koppels")

    cf1, cf2 = st.columns([2, 1])
    with cf1:
        zoek = st.text_input("Zoeken (naam, onderwerp)", "").strip().lower()
    with cf2:
        filter_status = st.selectbox(
            "Status",
            ["Alle", "Onderzoek niet ingevuld", "Achter op schema", "Op schema"],
            key="filter_status_mijn",
        )

    getoond = 0
    for k in koppels:
        leden_namen = [m["naam"] for m in k["leden"]]
        zoekbaar = " ".join(leden_namen + [k["onderzoek"]["onderwerp"] or ""]).lower()
        if zoek and zoek not in zoekbaar:
            continue

        has_ond = bool(k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"])
        done_passed = sum(
            1 for m in verstreken_deadlines if k["voortgang"].get(m["sleutel"])
        )
        is_behind = done_passed < len(verstreken_deadlines)

        if filter_status == "Onderzoek niet ingevuld" and has_ond:
            continue
        if filter_status == "Achter op schema" and not is_behind:
            continue
        if filter_status == "Op schema" and is_behind:
            continue

        _render_koppel_kaart(user, k, verstreken_deadlines, eigen=True)
        getoond += 1

    if getoond == 0:
        st.caption("Geen koppels voldoen aan de filter.")


# ===================== Beschikbare koppels =====================

def _tab_beschikbare_koppels(user: dict, koppels: list[dict]) -> None:
    if not koppels:
        st.info("Er zijn op dit moment geen koppels zonder begeleider.")
        return

    # Vak-filter: alleen vakken die daadwerkelijk voorkomen
    vakken_in_lijst = sorted({
        k["onderzoek"]["vak"] for k in koppels if k["onderzoek"]["vak"]
    })
    zonder_vak_aanwezig = any(not k["onderzoek"]["vak"] for k in koppels)

    cf1, cf2 = st.columns([1, 2])
    with cf1:
        vak_opties = ["Alle vakken"] + vakken_in_lijst
        if zonder_vak_aanwezig:
            vak_opties.append("(nog niet gekozen)")
        vak_keuze = st.selectbox("Vak", vak_opties, key="bg_bk_vak")
    with cf2:
        zoek = st.text_input(
            "Zoeken (naam, onderwerp)", "", key="bg_bk_zoek"
        ).strip().lower()

    def _matches(k: dict) -> bool:
        vak = k["onderzoek"]["vak"]
        if vak_keuze == "(nog niet gekozen)" and vak:
            return False
        if vak_keuze not in ("Alle vakken", "(nog niet gekozen)") and vak != vak_keuze:
            return False
        if zoek:
            hay = " ".join(
                [m["naam"] for m in k["leden"]]
                + [k["onderzoek"]["onderwerp"] or ""]
            ).lower()
            if zoek not in hay:
                return False
        return True

    getoond = [k for k in koppels if _matches(k)]
    st.caption(
        f"{len(getoond)} van {len(koppels)} beschikbare koppels getoond. "
        "Klik op **Neem aan** om een koppel toe te voegen aan jouw dashboard."
    )

    if not getoond:
        st.info("Geen koppels voldoen aan de filter.")
        return

    for k in getoond:
        leden_namen = [m["naam"] for m in k["leden"]]
        leden_klas = ", ".join(
            [f"{m['naam']} ({m.get('klas') or '?'})" for m in k["leden"]]
        )
        solo = len(k["leden"]) == 1
        ond = k["onderzoek"]
        header = (
            (ond["onderwerp"] or "Nog geen onderwerp")
            + "  —  "
            + " & ".join(leden_namen)
            + ("  (solo)" if solo else "")
        )

        with st.expander(header):
            st.markdown(f"**Leerlingen:** {leden_klas}")
            st.markdown(f"**Vak:** {ond['vak'] or '_Nog niet ingevuld_'}")
            st.markdown(f"**Hoofdvraag:**")
            st.write(ond["hoofdvraag"] or "_Nog niet ingevuld_")
            if ond["deelvragen"]:
                st.markdown("**Deelvragen:**")
                for i, dv in enumerate(ond["deelvragen"], 1):
                    st.write(f"{i}. {dv}")

            if st.button("Neem aan", type="primary", key=f"claim_{k['id']}"):
                try:
                    db.claim_koppel(k["id"], user["eckid"])
                    st.success("Koppel toegevoegd aan je dashboard.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ===================== Koppel-kaart (gedetailleerd) =====================

def _render_koppel_kaart(
    begeleider: dict, k: dict, verstreken: list[dict], eigen: bool
) -> None:
    has_ond = bool(k["onderzoek"]["onderwerp"] and k["onderzoek"]["hoofdvraag"])
    done_passed = sum(1 for m in verstreken if k["voortgang"].get(m["sleutel"]))

    if not has_ond:
        kleur, status = "#d9534f", "Onderzoek niet (volledig) ingevuld"
    elif done_passed < len(verstreken):
        kleur = "#f0ad4e"
        status = (
            f"Achter op schema "
            f"({done_passed} / {len(verstreken)} verstreken deadlines afgevinkt)"
        )
    else:
        kleur, status = "#5cb85c", "Op schema"

    leden_namen = [m["naam"] for m in k["leden"]]
    leden_klas = ", ".join(
        [f"{m['naam']} ({m.get('klas') or '?'})" for m in k["leden"]]
    )
    onderwerp = k["onderzoek"]["onderwerp"] or "Nog geen onderwerp"
    header = f"{onderwerp}  —  " + " & ".join(leden_namen)
    if len(k["leden"]) == 1:
        header += "  (solo)"

    with st.expander(header):
        status_html = (
            f'<div style="padding:6px 10px;background:{kleur}22;'
            f'border-left:4px solid {kleur};margin-bottom:14px;">'
            f'<strong>Status:</strong> {status}'
            f'</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)

        col_info, col_vortg = st.columns([2, 1])
        with col_info:
            st.markdown(f"**Leerlingen:** {leden_klas}")
            cc1, cc2 = st.columns(2)
            with cc1:
                st.markdown("**Onderwerp**")
                st.write(k["onderzoek"]["onderwerp"] or "_Nog niet ingevuld_")
            with cc2:
                st.markdown("**Vak**")
                st.write(k["onderzoek"]["vak"] or "_Nog niet ingevuld_")

            st.markdown("**Hoofdvraag**")
            st.write(k["onderzoek"]["hoofdvraag"] or "_Nog niet ingevuld_")

            st.markdown("**Deelvragen**")
            if k["onderzoek"]["deelvragen"]:
                for i, dv in enumerate(k["onderzoek"]["deelvragen"], 1):
                    st.write(f"{i}. {dv}")
            else:
                st.write("_Nog geen deelvragen_")

            if k["onderzoek"].get("bijgewerkt"):
                st.caption(f"Laatst bijgewerkt: {k['onderzoek']['bijgewerkt']}")

        with col_vortg:
            st.markdown("**Voortgang (door leerlingen afgevinkt)**")
            for m in [mp for mp in MIJLPALEN if mp["sleutel"]]:
                is_done = k["voortgang"].get(m["sleutel"], False)
                st.checkbox(
                    f"{m['titel']} ({m['datum'].strftime('%d %b')})",
                    value=is_done,
                    disabled=True,
                    key=f"bg_view_{k['id']}_{m['sleutel']}",
                )

        # Feedback / commentaar
        st.divider()
        _render_commentaar_sectie(begeleider, k)

        # Koppel teruggeven
        if eigen:
            st.divider()
            if st.button(
                "Koppel teruggeven (verwijderen uit mijn dashboard)",
                key=f"release_{k['id']}",
            ):
                db.release_koppel(k["id"])
                st.rerun()


def _render_commentaar_sectie(begeleider: dict, k: dict) -> None:
    st.markdown("**Feedback voor dit koppel**")
    commentaren = db.get_commentaar(k["id"])

    nieuwe_key = f"nieuw_fb_{k['id']}"
    tekst = st.text_area(
        "Nieuw bericht",
        key=nieuwe_key,
        height=90,
        placeholder="Bericht aan dit koppel …",
        label_visibility="collapsed",
    )
    if st.button("Feedback versturen", key=f"send_fb_{k['id']}"):
        if tekst.strip():
            db.add_commentaar(k["id"], begeleider["eckid"], tekst.strip())
            st.session_state[nieuwe_key] = ""
            st.rerun()
        else:
            st.warning("Leeg bericht niet verzonden.")

    if not commentaren:
        st.caption("Nog geen feedback geplaatst.")
        return

    for c in commentaren:
        rol_label = "begeleider" if c["auteur_rol"] == "begeleider" else "leerling"
        bg = "#eef5ff" if c["auteur_rol"] == "begeleider" else "#f8f8f8"
        html = (
            f'<div style="padding:10px 14px;background:{bg};'
            f'border-left:3px solid #4A90E2;border-radius:4px;margin:6px 0;">'
            f'<div style="font-size:12px;color:#666;margin-bottom:4px;">'
            f'{c["auteur_naam"]} ({rol_label}) — {c["aangemaakt"]}'
            f'</div>'
            f'<div>{_escape_html(c["tekst"])}</div>'
            f'</div>'
        )
        st.markdown(html, unsafe_allow_html=True)
        # Alleen eigen berichten mogen verwijderd worden
        if c.get("auteur_rol") == "begeleider":
            # (We kunnen niet zomaar weten of deze begeleider de auteur is zonder
            # auteur_id in de row; laten we dat simpel houden en delete weglaten
            # om per ongeluk verwijderen te voorkomen.)
            pass


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace("\n", "<br>")
    )
