"""
app.py — PWS Voortgang platform

Authenticatie via JWT-token van bovenbouwsucces.nl portaal.
Rol-logica:
  - leerling  → automatisch student
  - docent    → automatisch begeleider
  - coordinator in app_rollen.pws → coordinator (handmatig via portaal-beheer)
"""

import streamlit as st
import jwt
import os
import db
from pws_data import SCHOOLJAAR
from view_begeleider import render_begeleider
from view_coordinator import render_coordinator
from view_student import render_student

JWT_SECRET    = os.environ.get("JWT_SECRET", "verander-dit-naar-een-lang-geheim")
JWT_ALGORITHM = "HS256"


def main() -> None:
    st.set_page_config(
        page_title=f"PWS {SCHOOLJAAR}",
        layout="wide",
        initial_sidebar_state="auto",
    )
    db.ensure_db()
    _verwerk_sso_token()

    if "eckid" not in st.session_state:
        _render_geen_toegang()
        return

    user = db.get_user_by_eckid(st.session_state["eckid"])
    if user is None:
        del st.session_state["eckid"]
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


def _verwerk_sso_token() -> None:
    """Lees JWT-token uit query params na doorlink vanuit het portaal."""
    if "eckid" in st.session_state:
        return

    token = st.query_params.get("token")
    if not token:
        return

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        eckid      = payload.get("eckid")
        naam       = payload.get("naam", "Onbekend")
        klas       = payload.get("klas")
        portal_rol = payload.get("rol", "")
        app_rollen = payload.get("app_rollen", {})

        # Rol-logica:
        # coordinator expliciet ingesteld → coordinator
        # leerling → student
        # docent/beheerder → begeleider
        if app_rollen.get("pws") == "coordinator":
            pws_rol = "coordinator"
        elif portal_rol == "leerling":
            pws_rol = "student"
        elif portal_rol in ("docent", "beheerder"):
            pws_rol = "begeleider"
        else:
            pws_rol = None

        if not eckid or not pws_rol:
            st.query_params.clear()
            st.warning(
                "Je hebt nog geen toegang tot de PWS-app. "
                "Neem contact op met de beheerder."
            )
            return

        user = db.sso_upsert_user(eckid=eckid, naam=naam, rol=pws_rol, klas=klas)
        st.session_state["eckid"] = user["eckid"]
        st.query_params.clear()
        st.rerun()

    except jwt.ExpiredSignatureError:
        st.query_params.clear()
        st.warning("Je sessie is verlopen. Ga terug naar het portaal en probeer opnieuw.")
    except jwt.InvalidTokenError:
        st.query_params.clear()
        st.error("Ongeldig token. Neem contact op met de beheerder.")


def _render_geen_toegang() -> None:
    st.title(f"PWS-platform {SCHOOLJAAR}")
    st.warning(
        "Je hebt geen directe toegang tot deze pagina. "
        "Log in via het portaal op [bovenbouwsucces.nl](https://bovenbouwsucces.nl)."
    )


def _render_sidebar(user: dict) -> None:
    with st.sidebar:
        st.markdown(f"### {user['naam']}")
        rol_label = {
            "student":     "Leerling",
            "begeleider":  "Begeleider",
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
