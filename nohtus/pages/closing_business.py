from __future__ import annotations

import streamlit as st

from nohtus.pages.closing import page_closing as _page_closing


def page_closing():
    st.markdown(
        """
        <style>
        .today-out-table{
            width:60vw!important;
            max-width:60vw!important;
            min-width:760px!important;
        }
        @media(max-width:900px){
            .today-out-table{width:100%!important;max-width:100%!important;min-width:0!important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    return _page_closing()
