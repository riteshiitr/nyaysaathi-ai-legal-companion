"""NyaySaathi – Your AI Legal Companion. Start it with: streamlit run app.py"""

import streamlit as st

from ui.common import LANGUAGE_OPTIONS, delete_everything, init_state, is_mock_mode, t
from ui.pages import PAGES
from ui.styles import CSS

st.set_page_config(page_title="NyaySaathi – Your AI Legal Companion", page_icon="⚖️", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)
init_state()

with st.sidebar:
    st.markdown('<p class="ns-brand">NyaySaathi</p><p class="ns-brand-sub">Your AI Legal Companion</p>', unsafe_allow_html=True)
    st.radio("Go to", list(PAGES), format_func=t, key="page", label_visibility="collapsed")
    st.divider()
    st.selectbox(
        t("language"),
        list(LANGUAGE_OPTIONS),
        format_func=LANGUAGE_OPTIONS.get,
        key="language_pref",
    )
    st.button(t("delete"), on_click=delete_everything, use_container_width=True)
    st.caption("Legal information only. Not a lawyer.")

if is_mock_mode():
    st.markdown(
        '<div class="ns-mock">MOCK MODE: answers are scripted to test the screens. They are not real AI or legal information.</div>',
        unsafe_allow_html=True,
    )
if st.session_state.pop("just_deleted", False):
    st.success("Your conversation and case have been deleted from this session.")

PAGES[st.session_state.page]()
