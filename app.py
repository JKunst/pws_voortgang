"""PWS-platform: hoofd-entrypoint met login en routing per rol."""

import streamlit as st
import jwt
import os

import db

# Gedeeld geheim met bovenbouwsucces — zet als environment variable:
# export JWT_SECRET="zelfde-geheim-als-portal"
JWT_SECRET = os.environ.get("JWT_SECRET", "verander-dit-naar-een-lang-geheim")
JWT_ALGORITHM = "HS256"
from pws_data import SCHOOLJAAR
from view_begeleider import render_begeleider
from view_coordinator import render_coordinator
from view_student import render_student



def _verwerk_sso_token() -> None:
    """
    Lees JWT-token uit query params na doorlink vanuit bovenbouwsucces.nl.
    Token bevat: email, rol, leerlingnummer.
    """
    if "user_id" in st.session_state:
        return  # Al ingelogd

    token = st.query_params.get("token")
    if not token:
        return

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        if not email:
            st.query_params.clear()
            return

        user = db.get_user_by_email(email)
        if user:
            st.session_state["user_id"] = user["id"]
            st.query_params.clear()
            st.rerun()
        else:
            st.query_params.clear()
            st.warning(
                f"Je account ({email}) is nog niet aangemaakt in de PWS-app. "
                "Neem contact op met je begeleider of coördinator."
            )
    except jwt.ExpiredSignatureError:
        st.query_params.clear()
        st.warning("Je sessie is verlopen. Ga terug naar het portaal en probeer opnieuw.")
    except jwt.InvalidTokenError:
        st.query_params.clear()
        st.error("Ongeldig token. Neem contact op met de beheerder.")


def main() -> None:
    st.set_page_config(
        page_title=f"PWS {SCHOOLJAAR}",
        layout="wide",
        initial_sidebar_state="auto",
    )
    db.ensure_db()
    db.migrate_add_email()
    _verwerk_sso_token()

    if "user_id" not in st.session_state:
        _render_login()
        return

    user = db.get_user_by_id(st.session_state["user_id"])
    if user is None:
        del st.session_state["user_id"]
        st.rerun()
        return

    _render_sidebar(user)

    if user["rol"] == "student":
        render_student(user)
    elif user["rol"] == "begeleider":
        render_begeleider(user)
    elif user["rol"] == "coordinator":
        render_coordinator(user)
    else:
        st.error(f"Onbekende rol: {user['rol']}")


def _render_login() -> None:
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title(f"PWS-platform {SCHOOLJAAR}")
        st.caption("Log in met je schoolaccount.")

        with st.form("login_form"):
            username = st.text_input("Gebruikersnaam")
            password = st.text_input("Wachtwoord", type="password")
            submit = st.form_submit_button("Inloggen", type="primary")

        if submit:
            user = db.get_user_by_username(username.strip())
            if user is None or not db.check_password(password, user["password_hash"]):
                st.error("Gebruikersnaam of wachtwoord onjuist.")
            else:
                st.session_state["user_id"] = user["id"]
                st.rerun()

        _render_demo_buttons()


def _quick_login(username: str) -> None:
    """Log direct in als de gegeven gebruiker (voor demo-doeleinden)."""
    user = db.get_user_by_username(username)
    if user:
        st.session_state["user_id"] = user["id"]
        st.rerun()


def _render_demo_buttons() -> None:
    st.divider()
    st.caption("Snel inloggen als test-gebruiker:")

    # Rij 1: coördinator + begeleiders
    st.markdown(
        '<div style="font-size:12px;color:#666;margin-bottom:4px;">'
        'Coördinator / Begeleiders</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("M. Gijsbers\n(coördinator)", key="demo_gijsbers",
                      use_container_width=True):
            _quick_login("m.gijsbers")
    with c2:
        if st.button("C. Troostwijk\n(begeleider, 2 koppels)", key="demo_troost",
                      use_container_width=True):
            _quick_login("c.troostwijk")
    with c3:
        if st.button("J. van der Maas\n(begeleider, 0 koppels)", key="demo_vdmaas",
                      use_container_width=True):
            _quick_login("j.vandermaas")

    # Rij 2: leerlingen
    st.markdown(
        '<div style="font-size:12px;color:#666;margin:8px 0 4px 0;">'
        'Leerlingen</div>',
        unsafe_allow_html=True,
    )
    DEMO_LEERLINGEN = [
        ("jaap.degoede",    "Jaap de Goede",     "koppel, onderzoek af, 1 deadline"),
        ("eva.jansen",      "Eva Jansen",        "koppel, alleen onderwerp"),
        ("amira.yildiz",    "Amira Yildiz",      "koppel, volledig, geen begeleider"),
        ("lars.visser",     "Lars Visser",       "solo, niks ingevuld"),
        ("nieuwe.leerling", "Sam Okonkwo",       "nog geen koppel (onboarding)"),
    ]
    cols = st.columns(len(DEMO_LEERLINGEN))
    for col, (username, naam, info) in zip(cols, DEMO_LEERLINGEN):
        with col:
            if st.button(f"{naam}\n({info})", key=f"demo_{username}",
                          use_container_width=True):
                _quick_login(username)


def _render_sidebar(user: dict) -> None:
    with st.sidebar:
        st.markdown(f"### {user['naam']}")
        rol_label = {
            "student": "Leerling",
            "begeleider": "Begeleider",
            "coordinator": "Coördinator",
        }.get(user["rol"], user["rol"])
        details = rol_label
        if user.get("klas"):
            details += f" — klas {user['klas']}"
        st.caption(details)
        st.divider()
        if st.button("Uitloggen", use_container_width=True):
            st.session_state.clear()
            st.rerun()


if __name__ == "__main__":
    main()
