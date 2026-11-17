"""Nodi Telecom (fictional) - Prepaid Loyalty & CLV Decision Engine. All data is synthetic.

Run locally:  streamlit run app/streamlit_app.py
Reads only app_data/ (built by `python run.py`); no API key needed.
"""
import streamlit as st

st.set_page_config(page_title="Nodi Loyalty Decision Engine", page_icon=":material/cell_tower:", layout="wide")

pages = [
    st.Page("pages/executive.py", title="Executive summary", icon=":material/insights:", default=True),
    st.Page("pages/segments.py", title="Segment explorer", icon=":material/groups:"),
    st.Page("pages/allocator.py", title="Budget allocator", icon=":material/tune:"),
    st.Page("pages/studio.py", title="Campaign studio", icon=":material/sms:"),
]
st.navigation(pages).run()
