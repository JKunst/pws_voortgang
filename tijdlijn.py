"""Visuele tijdlijn (gedeeld door student- en begeleider-view).

Let op: Streamlit's markdown-parser ziet regels met 4+ spaties inspringing
als code-block. Daarom staan alle HTML-strings hier zonder leading whitespace.
"""

from datetime import date

import streamlit as st

from pws_data import FASEN, MIJLPALEN


def huidige_fase_index(vandaag: date) -> int | None:
    for i, fase in enumerate(FASEN):
        if fase["start"] <= vandaag <= fase["eind"]:
            return i
    return None


def volgende_mijlpaal(vandaag: date) -> dict | None:
    for m in MIJLPALEN:
        if m["datum"] >= vandaag:
            return m
    return None


def render_tijdlijn(vandaag: date) -> None:
    totaal_dagen = (FASEN[-1]["eind"] - FASEN[0]["start"]).days

    blokken = ""
    for fase in FASEN:
        dagen = (fase["eind"] - fase["start"]).days + 1
        breedte_pct = 100 * dagen / totaal_dagen
        blokken += (
            f'<div style="flex:0 0 {breedte_pct:.2f}%;background:{fase["kleur"]};'
            f'padding:10px 4px;text-align:center;color:white;'
            f'border-right:1px solid white;min-width:0;">'
            f'<div style="font-weight:600;font-size:13px;">{fase["naam"]}</div>'
            f'<div style="font-size:10px;opacity:0.9;">'
            f'{fase["start"].strftime("%d %b")} &ndash; '
            f'{fase["eind"].strftime("%d %b %Y")}'
            f'</div>'
            f'</div>'
        )

    marker = ""
    if FASEN[0]["start"] <= vandaag <= FASEN[-1]["eind"]:
        pos_pct = 100 * (vandaag - FASEN[0]["start"]).days / totaal_dagen
        marker = (
            f'<div style="position:absolute;left:{pos_pct:.2f}%;top:-8px;'
            f'height:calc(100% + 16px);width:3px;background:#111;z-index:2;">'
            f'<div style="position:absolute;top:-22px;left:-32px;width:70px;'
            f'text-align:center;font-size:11px;font-weight:700;color:#111;">'
            f'vandaag</div></div>'
        )

    html = (
        '<div style="position:relative;margin:30px 0 15px 0;">'
        '<div style="display:flex;border-radius:6px;overflow:hidden;'
        'box-shadow:0 1px 3px rgba(0,0,0,0.12);">'
        + blokken +
        '</div>' + marker + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_status_cards(vandaag: date) -> None:
    """Twee kaartjes onder de tijdlijn: huidige fase + volgende deadline."""
    col_fase, col_deadline = st.columns(2)
    idx = huidige_fase_index(vandaag)
    with col_fase:
        if idx is not None:
            fase = FASEN[idx]
            html = (
                f'<div style="padding:10px 14px;border-radius:6px;'
                f'background:{fase["kleur"]}22;'
                f'border-left:4px solid {fase["kleur"]};">'
                f'<div style="font-size:12px;color:#666;">Huidige fase</div>'
                f'<div style="font-size:16px;font-weight:600;">{fase["naam"]}</div>'
                f'</div>'
            )
            st.markdown(html, unsafe_allow_html=True)
        elif vandaag < FASEN[0]["start"]:
            st.info("PWS-periode is nog niet begonnen.")
        else:
            st.success("PWS-periode afgerond.")
    with col_deadline:
        v = volgende_mijlpaal(vandaag)
        if v:
            dagen = (v["datum"] - vandaag).days
            if dagen == 0:
                tekst = f"**Vandaag:** {v['titel']}"
            else:
                tekst = f"**Over {dagen} dagen:** {v['titel']} ({v['datum'].strftime('%d %b')})"
            st.warning(tekst)
        else:
            st.info("Geen volgende deadline meer.")
