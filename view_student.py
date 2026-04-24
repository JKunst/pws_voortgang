"""Student-weergave: tijdlijn, partner kiezen, onderzoek, feedback, handleiding, Word."""

from datetime import date

import streamlit as st

import db
from pws_data import MIJLPALEN, SCHOOLJAAR, VAK_SUGGESTIES
from tijdlijn import render_status_cards, render_tijdlijn


DAG_NL = {
    "Monday": "maandag", "Tuesday": "dinsdag", "Wednesday": "woensdag",
    "Thursday": "donderdag", "Friday": "vrijdag", "Saturday": "zaterdag",
    "Sunday": "zondag",
}
MAAND_NL = {
    1: "januari", 2: "februari", 3: "maart", 4: "april", 5: "mei", 6: "juni",
    7: "juli", 8: "augustus", 9: "september", 10: "oktober", 11: "november",
    12: "december",
}


def _fmt_datum(d: date) -> str:
    return f"{DAG_NL[d.strftime('%A')]} {d.day} {MAAND_NL[d.month]} {d.year}"


def render_student(user: dict) -> None:
    # Geen koppel? Dan eerst verplicht partner kiezen.
    koppel = db.get_my_koppel(user["eckid"])
    if koppel is None:
        _render_partner_onboarding(user)
        return

    st.title(f"Profielwerkstuk {SCHOOLJAAR}")
    _render_header(user, koppel)

    vandaag = date.today()
    render_tijdlijn(vandaag)
    render_status_cards(vandaag)

    tab_tijd, tab_ond, tab_fb, tab_hand, tab_word = st.tabs([
        "Tijdlijn en voortgang",
        "Mijn onderzoek",
        "Feedback van begeleider",
        "Handleiding",
        "Word-tips",
    ])
    with tab_tijd:
        _tab_tijdlijn(user, koppel, vandaag)
    with tab_ond:
        _tab_onderzoek(user, koppel)
    with tab_fb:
        _tab_feedback(user, koppel)
    with tab_hand:
        _tab_handleiding()
    with tab_word:
        _tab_word_tips()


# ===================== Header / onboarding =====================

def _render_header(user: dict, koppel: dict) -> None:
    partners = [m for m in koppel["leden"] if m["eckid"] != user["eckid"]]
    klas = f" — klas {user['klas']}" if user.get("klas") else ""
    if partners:
        partner_naam = partners[0]["naam"]
        st.caption(f"{user['naam']}{klas}  ·  partner: **{partner_naam}**")
    else:
        st.caption(f"{user['naam']}{klas}  ·  solo")


def _render_partner_onboarding(user: dict) -> None:
    st.title(f"Welkom, {user['naam'].split()[0]}")
    st.markdown(
        "Voordat je aan de slag kunt, kies je eerst je partner. "
        "Je PWS maak je **in tweetallen** of in overleg alleen."
    )
    _render_partner_selector(user, prefix="ob", toon_current=False)


def _render_partner_selector(user: dict, prefix: str, toon_current: bool = True) -> None:
    """Herbruikbare partner-picker. Prefix zorgt voor unieke widget-keys."""
    beschikbaar = db.get_available_partners(user["eckid"])
    opties = ["— Solo (geen partner) —"] + [p["naam"] for p in beschikbaar]
    id_per_naam = {p["naam"]: p["eckid"] for p in beschikbaar}

    huidige_koppel = db.get_my_koppel(user["eckid"])
    huidige_partner = None
    if huidige_koppel:
        partners = [m for m in huidige_koppel["leden"] if m["eckid"] != user["eckid"]]
        if partners:
            huidige_partner = partners[0]

    if toon_current:
        if huidige_partner:
            st.info(f"Je bent op dit moment gekoppeld aan **{huidige_partner['naam']}**.")
        else:
            st.info("Je werkt op dit moment **solo**.")

    # Voorselecteer de huidige partner (als die in de lijst staat)
    index = 0
    if huidige_partner and huidige_partner["naam"] in opties:
        index = opties.index(huidige_partner["naam"])

    keuze = st.selectbox(
        "Partner kiezen",
        opties,
        index=index,
        key=f"{prefix}_partner_select_{user['id']}",
    )

    if huidige_partner is not None:
        st.caption(
            "Let op: van partner wisselen betekent dat je met je nieuwe partner "
            "een leeg onderzoek start. Bestaande data blijft bij het oude koppel."
        )

    if st.button("Opslaan", type="primary", key=f"{prefix}_save_{user['id']}"):
        partner_id = None
        if keuze != "— Solo (geen partner) —":
            partner_id = id_per_naam[keuze]
        try:
            db.set_partner(user["eckid"], partner_id)
            st.success("Opgeslagen.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


# ===================== Tabs =====================

def _tab_tijdlijn(user: dict, koppel: dict, vandaag: date) -> None:
    st.subheader("Mijlpalen en deadlines")
    voortgang = koppel["voortgang"]

    for m in MIJLPALEN:
        is_deadline = m["sleutel"] is not None
        is_verstreken = m["datum"] < vandaag
        kleur = "#999" if is_verstreken and not voortgang.get(m["sleutel"], False) else "#111"
        prefix = "◆" if is_deadline else "○"

        if is_deadline:
            col_cb, col_txt = st.columns([1, 30])
            with col_cb:
                huidig = voortgang.get(m["sleutel"], False)
                nieuw = st.checkbox(
                    " ",
                    value=huidig,
                    key=f"cb_{koppel['id']}_{m['sleutel']}",
                    label_visibility="collapsed",
                )
                if nieuw != huidig:
                    db.set_voortgang(koppel["id"], m["sleutel"], nieuw)
                    st.rerun()
            with col_txt:
                html = (
                    f'<div style="color:{kleur};">'
                    f'<strong>{prefix} {m["titel"]}</strong> — {_fmt_datum(m["datum"])}'
                    f'</div>'
                )
                st.markdown(html, unsafe_allow_html=True)
                st.caption(m["toelichting"])
        else:
            html = (
                f'<div style="color:{kleur};padding-left:3.5em;">'
                f'{prefix} <em>{m["titel"]}</em> — {_fmt_datum(m["datum"])}'
                f'</div>'
            )
            st.markdown(html, unsafe_allow_html=True)

        st.divider()


def _tab_onderzoek(user: dict, koppel: dict) -> None:
    # Partner-sectie bovenaan
    with st.expander("Partner en koppel", expanded=False):
        _render_partner_selector(user, prefix="ond", toon_current=True)

    st.subheader("Onderwerp en onderzoeksvragen")
    partners = [m for m in koppel["leden"] if m["eckid"] != user["eckid"]]
    if partners:
        st.caption(
            f"Wat je hier invult, wordt gedeeld met **{partners[0]['naam']}**. "
            "Jullie begeleider kan het ook zien en feedback geven."
        )
    else:
        st.caption("Je werkt solo. Je begeleider kan je onderzoek zien en feedback geven.")

    onderzoek = koppel["onderzoek"]

    # Session-state init: laad één keer uit DB per koppel
    flag = f"ond_loaded_{koppel['id']}"
    if flag not in st.session_state:
        st.session_state[flag] = True
        st.session_state[f"ond_onderwerp_{koppel['id']}"]  = onderzoek["onderwerp"]
        st.session_state[f"ond_vak_{koppel['id']}"]        = (
            onderzoek["vak"] if onderzoek["vak"] in VAK_SUGGESTIES else VAK_SUGGESTIES[0]
        )
        st.session_state[f"ond_hoofdvraag_{koppel['id']}"] = onderzoek["hoofdvraag"]
        st.session_state[f"ond_dv_count_{koppel['id']}"]   = max(len(onderzoek["deelvragen"]), 1)
        for i, dv in enumerate(onderzoek["deelvragen"]):
            st.session_state[f"ond_dv_{koppel['id']}_{i}"] = dv

    st.text_input("Onderwerp", key=f"ond_onderwerp_{koppel['id']}")
    st.selectbox("Vak", VAK_SUGGESTIES, key=f"ond_vak_{koppel['id']}")
    st.text_area(
        "Hoofdvraag",
        key=f"ond_hoofdvraag_{koppel['id']}",
        height=100,
        help="Duidelijk, niet te breed, geen ja/nee-vraag, geen waarom-vraag.",
    )

    st.markdown("**Deelvragen**")
    st.caption("Opsplitsing van je hoofdvraag — samen leiden ze tot het antwoord.")

    count_key = f"ond_dv_count_{koppel['id']}"
    count = st.session_state[count_key]

    for i in range(count):
        cols = st.columns([20, 2])
        with cols[0]:
            st.text_input(
                f"Deelvraag {i+1}",
                key=f"ond_dv_{koppel['id']}_{i}",
                label_visibility="collapsed",
                placeholder=f"Deelvraag {i+1}",
            )
        with cols[1]:
            if st.button("Verwijderen", key=f"ond_del_{koppel['id']}_{i}"):
                for j in range(i, count - 1):
                    st.session_state[f"ond_dv_{koppel['id']}_{j}"] = st.session_state.get(
                        f"ond_dv_{koppel['id']}_{j+1}", ""
                    )
                last_key = f"ond_dv_{koppel['id']}_{count-1}"
                if last_key in st.session_state:
                    del st.session_state[last_key]
                st.session_state[count_key] = max(count - 1, 1)
                st.rerun()

    col_add, col_save = st.columns([1, 3])
    with col_add:
        if st.button("Deelvraag toevoegen", key=f"ond_add_{koppel['id']}"):
            st.session_state[count_key] = count + 1
            st.rerun()
    with col_save:
        if st.button("Opslaan", type="primary", key=f"ond_save_{koppel['id']}"):
            deelvragen = []
            for i in range(st.session_state[count_key]):
                val = st.session_state.get(f"ond_dv_{koppel['id']}_{i}", "").strip()
                if val:
                    deelvragen.append(val)
            db.save_onderzoek(
                koppel["id"],
                st.session_state[f"ond_onderwerp_{koppel['id']}"].strip(),
                st.session_state[f"ond_vak_{koppel['id']}"],
                st.session_state[f"ond_hoofdvraag_{koppel['id']}"].strip(),
                deelvragen,
            )
            st.success("Opgeslagen.")

    if onderzoek.get("bijgewerkt"):
        st.caption(f"Laatst opgeslagen: {onderzoek['bijgewerkt']}")


def _tab_feedback(user: dict, koppel: dict) -> None:
    st.subheader("Feedback van je begeleider")

    if koppel["begeleider_id"] is None:
        st.info(
            "Jullie koppel heeft nog geen begeleider. Zodra een docent jullie "
            "aanneemt, verschijnt hun feedback hier."
        )
        return

    commentaren = db.get_commentaar(koppel["id"])
    if not commentaren:
        st.info("Nog geen feedback ontvangen.")
        return

    for c in commentaren:
        auteur = c["auteur_naam"]
        rol_label = "begeleider" if c["auteur_rol"] == "begeleider" else "leerling"
        bg = "#eef5ff" if c["auteur_rol"] == "begeleider" else "#f8f8f8"
        html = (
            f'<div style="padding:10px 14px;background:{bg};'
            f'border-left:3px solid #4A90E2;border-radius:4px;margin-bottom:8px;">'
            f'<div style="font-size:12px;color:#666;margin-bottom:4px;">'
            f'{auteur} ({rol_label}) — {c["aangemaakt"]}'
            f'</div>'
            f'<div>{_escape_html(c["tekst"])}</div>'
            f'</div>'
        )
        st.markdown(html, unsafe_allow_html=True)


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace("\n", "<br>")
    )


# ===================== Handleiding =====================

def _tab_handleiding() -> None:
    st.subheader("Handleiding PWS")
    st.caption(
        "Samenvatting van de officiële handleiding. Raadpleeg Magister "
        "(studiewijzer profielwerkstuk en toolbox vaardigheden) voor het "
        "volledige document en bijbehorende formulieren."
    )

    with st.expander("Wat is het PWS?"):
        st.markdown(
            "Een profielwerkstuk is een werkstuk waarin je gebruik maakt van kennis "
            "en vaardigheden uit een van je examenvakken. Je maakt het PWS in "
            "**tweetallen**. Het cijfer telt mee in het **combinatiecijfer** "
            "(samen met maatschappijleer en ckv) en is een van de cijfers op je "
            "eindlijst. Zonder voldoende PWS geen diploma."
        )

    with st.expander("Fase 1 — Oriëntatie"):
        st.markdown(
            "- **Onderwerp en partner kiezen** — kies iets waar je echt interesse "
            "in hebt; kies een partner met dezelfde instelling en inzet.\n"
            "- **Hoofdvraag formuleren** — duidelijk, niet te breed, niet met "
            "ja/nee te beantwoorden, geen waarom-vraag.\n"
            "- **Deelvragen formuleren** — opsplitsing van de hoofdvraag; samen "
            "leiden ze tot het antwoord op de hoofdvraag.\n"
            "- **Werkplan maken** — activiteiten, tijdsplanning en taakverdeling."
        )
        st.markdown("**Voorbeelden van goede hoofdvragen:**")
        st.markdown(
            "- Van welke factoren hangt de luchtwrijving op een voertuig af?\n"
            "- Hoe ontwerp ik een vliegtuigvleugel voor een modelvliegtuig?\n"
            "- Welke verschillen zijn er tussen het spectrum van een gloeilamp, "
            "een TL-buis en de zon?"
        )
        st.markdown("**Minder goede hoofdvragen:**")
        st.markdown(
            "- *Kan ik de wrijving op een modelauto meten?* (ja/nee)\n"
            "- *Hoe werkt een laser?* (knip-en-plak uit een boek)\n"
            "- *Waarom blijft een vliegtuig vliegen?* (waarom-vraag)"
        )

    with st.expander("Fase 2 — Voorbereiding en onderzoek"):
        st.markdown(
            "- **Bronnen verzamelen** — één bron is geen bron; spreid over type "
            "(boek, artikel, website) en diepgang.\n"
            "- **Bronnen bijhouden** — noteer vanaf dag één elke bron die je "
            "gebruikt, inclusief zoektermen.\n"
            "- **Betrouwbaarheid beoordelen** — primaire bron, peer review, "
            "auteurs bekend, literatuurverwijzingen aanwezig.\n"
            "- **Onderzoek uitvoeren** — volgens je werkplan; experimenteel, "
            "literatuur of ontwerp.\n\n"
            "**Aanbevolen zoekmachines:** Google Scholar, DuckDuckGo, "
            "Wolfram Alpha, PubMed."
        )

    with st.expander("Fase 3 — Verwerking: opbouw van het verslag"):
        st.markdown(
            "Een gangbare indeling:\n"
            "1. Inhoudsopgave\n"
            "2. Voorwoord (persoonlijk; ik/wij-vorm mag)\n"
            "3. Inleiding (hoofdvraag, deelvragen, hypothese)\n"
            "4. Theoretisch kader — wat is er al bekend\n"
            "5. Eigen onderzoek (methode en resultaten)\n"
            "6. Conclusie\n"
            "7. Bespreking / discussie\n"
            "8. Dankwoord\n"
            "9. Bronvermelding\n"
            "10. Bijlagen (logboek, meetgegevens)\n\n"
            "Een **conceptversie** is het PWS zoals jullie denken dat het af is — "
            "niet een ruwe versie. Op basis van de feedback mag je één keer een "
            "verbeterde, definitieve versie inleveren."
        )

    with st.expander("Fase 3 — Presentatie"):
        st.markdown(
            "Op de presentatieavond krijg je **15 minuten**. Mogelijke vormen:\n"
            "- Mondelinge presentatie met PowerPoint (geen Prezi)\n"
            "- Posterpresentatie\n"
            "- Videopresentatie\n"
            "- Demonstratie bij een ontwerp of prototype"
        )

    with st.expander("Fase 4 — Reflectie en beoordeling"):
        st.markdown(
            "Na de presentatie volgt de eindbespreking met je begeleider. Jullie "
            "ondertekenen samen het beoordelingsformulier.\n\n"
            "**Als een deadline niet haalbaar is:** bespreek dit **tijdig** met "
            "je begeleider. Zonder toestemming te laat inleveren betekent "
            "dagelijks van 8:00 tot 17:00 op school zijn tot het PWS af is."
        )

    with st.expander("Logboek"):
        st.markdown(
            "Houd vanaf dag één een logboek bij in Word. Per activiteit noteer je:\n"
            "- **Datum**\n"
            "- **Activiteit**\n"
            "- **Uren**\n"
            "- **Wie** (jij, je partner, of beiden)\n"
            "- **Problemen en oplossingen**\n\n"
            "Neem het logboek **altijd mee** naar besprekingen met je begeleider. "
            "Het logboek gaat als bijlage bij zowel de conceptversie als de "
            "definitieve versie."
        )


def _tab_word_tips() -> None:
    st.subheader("Een nette inhoudsopgave en bronvermelding in Word")

    st.markdown("### Automatische inhoudsopgave")
    st.markdown(
        "Een inhoudsopgave maak je **niet handmatig**. Laat Word het werk doen — "
        "dan update hij automatisch als paginanummers of titels veranderen."
    )
    st.markdown(
        "**Stap 1 — Gebruik kopstijlen.** Selecteer elk hoofdstuktitel en kies "
        "op het **Start**-tabblad de stijl **Kop 1**. Voor subkoppen gebruik je "
        "**Kop 2** en **Kop 3**. Zonder kopstijlen geen goede inhoudsopgave.\n\n"
        "**Stap 2 — Plaats de cursor** op de plek waar de inhoudsopgave moet "
        "komen (na het voorwoord, vóór de inleiding).\n\n"
        "**Stap 3 — Voeg de inhoudsopgave in.** Ga naar "
        "**Verwijzingen → Inhoudsopgave → Automatische inhoudsopgave 1**.\n\n"
        "**Stap 4 — Bijwerken.** Verander je later iets in de koppen of de "
        "paginanummers? Klik met rechts op de inhoudsopgave → "
        "**Veld bijwerken → Hele tabel bijwerken**. Sneltoets: selecteer de "
        "inhoudsopgave en druk **F9**."
    )
    st.info(
        "Tip: zet de kop 'Inhoudsopgave' zelf niet als Kop 1, anders komt hij "
        "in de inhoudsopgave terecht."
    )

    st.markdown("### Bronvermelding met Word")
    st.markdown(
        "Word heeft een ingebouwde bronnenmanager. Je vult je bronnen één keer "
        "in; Word zorgt voor de citaten in de tekst én de bronnenlijst achterin."
    )
    st.markdown(
        "**Stap 1 — Kies een stijl.** Ga naar **Verwijzingen → Stijl** en kies "
        "**APA**. Dit sluit aan bij de voorbeelden in de PWS-handleiding.\n\n"
        "**Stap 2 — Nieuwe bron toevoegen.** "
        "**Verwijzingen → Bronnen beheren → Nieuw…** Kies het brontype "
        "(boek, artikel in tijdschrift, website) en vul alle velden in. "
        "Vergeet bij internetbronnen niet de **datum van raadpleging** en de "
        "**volledige URL**.\n\n"
        "**Stap 3 — Verwijzen in de tekst.** Op de plek waar je naar de bron "
        "verwijst: **Verwijzingen → Citaat invoegen** → kies de bron. Word "
        "plaatst dan bijvoorbeeld *(Lockley, 1976)* in je tekst.\n\n"
        "**Stap 4 — Bronnenlijst genereren.** Aan het eind van je PWS (vóór "
        "de bijlagen): **Verwijzingen → Bibliografie → Bibliografie invoegen**. "
        "Word maakt een alfabetische lijst van alle bronnen die je hebt "
        "ingevoerd en gebruikt."
    )

    with st.expander("Voorbeelden uit de PWS-handleiding (schoolstijl)"):
        st.markdown(
            "**Boek**  \n"
            "Lockley, R.M. (1976), *Het leven der konijnen*. Utrecht: Het Spectrum\n\n"
            "**Artikel**  \n"
            "Achternaam, V. (jaar), *titel artikel*. Naam krant of tijdschrift, "
            "datum / nummer jaargang, begin- en eindpagina.\n\n"
            "**Internet**  \n"
            "Scholte, G. en Marree, I. (1999), *Bioplek: Maken van een verslag*. "
            "Geraadpleegd op 10 juni 2007, "
            "http://www.bioplek.org/techniekkaartenbovenbouw/techniek91verslag.html\n\n"
            "Bij geen datum: gebruik **(z.d.)**. Verwijs **nooit** alleen naar "
            "`www.google.nl` — altijd de werkelijke site waar de informatie staat."
        )

    st.warning(
        "Plagiaat-waarschuwing: neem nooit letterlijk teksten over zonder "
        "aanhalingstekens én bronvermelding. Je PWS wordt gecontroleerd op "
        "plagiaat."
    )
