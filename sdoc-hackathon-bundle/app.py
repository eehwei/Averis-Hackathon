from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from loader import Inbox


# ============================================================
# Application configuration
# ============================================================

st.set_page_config(
    page_title="Shipping Document Verification",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIRECTORY = PROJECT_ROOT / "output"
SUBMISSION_FILE = OUTPUT_DIRECTORY / "submission.json"

VALID_CATEGORIES = {
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
}

VALID_STATUSES = {
    "OK",
    "MISMATCH",
    "NEEDS_REVIEW",
}

VALID_REVIEW_REASONS = {
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
}

COMPARISON_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

CATEGORY_DISPLAY_NAMES = {
    "BL_COMPARISON": "BL Comparison",
    "SI_REQUEST": "SI Request",
    "INVOICE_QUERY": "Invoice Query",
    "GENERAL": "General",
    "SPAM": "Spam",
}

STATUS_DISPLAY_NAMES = {
    "OK": "No Mismatch",
    "MISMATCH": "Mismatch",
    "NEEDS_REVIEW": "Needs Review",
    "NOT_PROCESSED": "Not Processed",
    "NOT_APPLICABLE": "Not Applicable",
}


# ============================================================
# Styling
# ============================================================

st.markdown(
    """
    <style>
        /* ==========================================
           Main application
           ========================================== */

        :root {
            --averis-orange: #F28A18;
            --averis-dark-orange: #D96F00;
            --averis-black: #111111;
            --averis-white: #FFFFFF;
            --averis-light-grey: #F2F2F2;
            --averis-border: #DEDEDE;
            --averis-secondary-text: #5F5F5F;
        }

        .stApp {
            background-color: var(--averis-white);
            color: var(--averis-black);
        }

        .block-container {
            max-width: 1450px;
            padding-top: 1.3rem;
            padding-bottom: 4rem;
            padding-left: 3rem;
            padding-right: 3rem;
        }

        /* Remove Streamlit's default top decoration */
        [data-testid="stHeader"] {
            background-color: rgba(255, 255, 255, 0.96);
        }

        /* ==========================================
           Brand header
           ========================================== */

        .brand-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border-bottom: 1px solid #E8E8E8;
            padding: 10px 0 16px 0;
            margin-bottom: 4px;
        }

        .brand-area {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-mark {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 46px;
            height: 46px;
            border-radius: 4px 4px 18px 4px;
            background: var(--averis-orange);
            color: #FFFFFF;
            font-size: 24px;
            font-weight: 800;
        }

        .brand-name {
            color: var(--averis-black);
            font-size: 27px;
            font-weight: 800;
            letter-spacing: -0.6px;
            line-height: 1.05;
        }

        .brand-description {
            color: var(--averis-secondary-text);
            font-size: 12px;
            margin-top: 3px;
            letter-spacing: 0.2px;
        }

        .system-ready {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #222222;
            background: #FFFFFF;
            border: 1px solid #DADADA;
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
        }

        .system-dot {
            width: 9px;
            height: 9px;
            background: var(--averis-orange);
            border-radius: 50%;
            display: inline-block;
        }

        /* ==========================================
           Horizontal navigation
           ========================================== */

        .st-key-top_navigation {
            background: #FFFFFF;
            border-bottom: 1px solid #E6E6E6;
            margin-bottom: 30px;
        }

        .st-key-top_navigation div[role="radiogroup"] {
            display: flex;
            flex-direction: row;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
        }

        .st-key-top_navigation div[role="radiogroup"] label {
            position: relative;
            background: transparent;
            border: none;
            border-radius: 0;
            padding: 14px 18px 13px 18px;
            margin: 0;
            cursor: pointer;
            transition:
                color 0.2s ease,
                background-color 0.2s ease;
        }

        /* Hide the normal radio circles */
        .st-key-top_navigation div[role="radiogroup"]
        label > div:first-child {
            display: none;
        }

        .st-key-top_navigation div[role="radiogroup"] label p {
            color: #111111;
            font-size: 15px;
            font-weight: 600;
            white-space: nowrap;
            transition: color 0.2s ease;
        }

        /* Orange when the mouse moves over a navigation item */
        .st-key-top_navigation div[role="radiogroup"]
        label:hover {
            background: #FFF7ED;
        }

        .st-key-top_navigation div[role="radiogroup"]
        label:hover p {
            color: var(--averis-orange) !important;
        }

        /* Orange underline for the selected page */
        .st-key-top_navigation div[role="radiogroup"]
        label:has(input:checked) {
            border-bottom: 4px solid var(--averis-orange);
        }

        .st-key-top_navigation div[role="radiogroup"]
        label:has(input:checked) p {
            color: var(--averis-black) !important;
            font-weight: 800;
        }

        /* ==========================================
           Headings
           ========================================== */

        .main-title {
            color: var(--averis-black);
            font-size: 38px;
            font-weight: 800;
            font-style: italic;
            letter-spacing: -0.8px;
            line-height: 1.15;
            margin-top: 3px;
            margin-bottom: 4px;
        }

        .subtitle {
            color: var(--averis-secondary-text);
            font-size: 17px;
            font-style: italic;
            margin-top: 5px;
            margin-bottom: 27px;
        }

        h1, h2, h3 {
            color: var(--averis-black) !important;
        }

        h2 {
            font-weight: 750 !important;
            letter-spacing: -0.3px;
        }

        h3 {
            font-weight: 700 !important;
        }

        /* Orange heading decoration */
        h2::after {
            content: "";
            display: block;
            width: 54px;
            height: 4px;
            background: var(--averis-orange);
            margin-top: 8px;
            margin-bottom: 13px;
        }

        /* ==========================================
           Metric cards
           ========================================== */

        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid var(--averis-border);
            border-top: 5px solid var(--averis-orange);
            border-radius: 4px 4px 22px 4px;
            padding: 18px 18px 17px 18px;
            box-shadow: 0 5px 16px rgba(0, 0, 0, 0.06);
            transition:
                transform 0.2s ease,
                box-shadow 0.2s ease;
        }

        [data-testid="stMetric"]:hover {
            transform: translateY(-3px);
            box-shadow: 0 9px 22px rgba(0, 0, 0, 0.10);
        }

        [data-testid="stMetricLabel"] {
            color: var(--averis-secondary-text);
            font-size: 14px;
            font-weight: 600;
        }

        [data-testid="stMetricValue"] {
            color: var(--averis-black);
            font-size: 31px;
            font-weight: 800;
        }

        /* ==========================================
           Buttons
           ========================================== */

        div.stButton > button,
        div.stDownloadButton > button {
            min-height: 44px;
            background: var(--averis-orange);
            color: #FFFFFF;
            border: 2px solid var(--averis-orange);
            border-radius: 5px 5px 22px 5px;
            padding: 8px 22px;
            font-size: 14px;
            font-weight: 750;
            transition:
                background-color 0.2s ease,
                border-color 0.2s ease,
                transform 0.2s ease,
                box-shadow 0.2s ease;
        }

        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            color: #FFFFFF;
            background: var(--averis-dark-orange);
            border-color: var(--averis-dark-orange);
            transform: translateY(-2px);
            box-shadow: 0 7px 15px rgba(242, 138, 24, 0.25);
        }

        div.stButton > button:focus,
        div.stDownloadButton > button:focus {
            color: #FFFFFF;
            border-color: var(--averis-dark-orange);
            box-shadow: 0 0 0 3px rgba(242, 138, 24, 0.25);
        }

        div.stButton > button:disabled {
            color: #777777;
            background: #E7E7E7;
            border-color: #E7E7E7;
            box-shadow: none;
        }

        /* ==========================================
           Inputs
           ========================================== */

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-testid="stSelectbox"] > div > div {
            border-radius: 5px 5px 15px 5px;
        }

        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {
            border-color: var(--averis-orange);
            box-shadow: 0 0 0 1px var(--averis-orange);
        }

        /* ==========================================
           Tabs
           ========================================== */

        [data-baseweb="tab-list"] {
            gap: 22px;
            border-bottom: 1px solid #DDDDDD;
        }

        [data-baseweb="tab"] {
            color: #333333;
            font-size: 15px;
            font-weight: 600;
            padding-left: 2px;
            padding-right: 2px;
        }

        [data-baseweb="tab"]:hover {
            color: var(--averis-orange);
        }

        [aria-selected="true"][data-baseweb="tab"] {
            color: var(--averis-black);
            font-weight: 800;
        }

        [data-baseweb="tab-highlight"] {
            background-color: var(--averis-orange);
        }

        /* ==========================================
           Status messages
           ========================================== */

        .status-ok {
            color: #14532D;
            background: #F0FDF4;
            border-left: 6px solid #238636;
            border-radius: 4px 4px 18px 4px;
            padding: 15px 17px;
            font-weight: 700;
        }

        .status-mismatch {
            color: #7F1D1D;
            background: #FEF2F2;
            border-left: 6px solid #C62828;
            border-radius: 4px 4px 18px 4px;
            padding: 15px 17px;
            font-weight: 700;
        }

        .status-review {
            color: #7C3D00;
            background: #FFF7ED;
            border-left: 6px solid var(--averis-orange);
            border-radius: 4px 4px 18px 4px;
            padding: 15px 17px;
            font-weight: 700;
        }

        .status-neutral {
            color: #333333;
            background: #F3F3F3;
            border-left: 6px solid #777777;
            border-radius: 4px 4px 18px 4px;
            padding: 15px 17px;
            font-weight: 700;
        }

        /* ==========================================
           Data tables
           ========================================== */

        [data-testid="stDataFrame"] {
            border: 1px solid var(--averis-border);
            border-radius: 4px 4px 20px 4px;
            overflow: hidden;
        }

        /* ==========================================
           Expanders and containers
           ========================================== */

        [data-testid="stExpander"] {
            border: 1px solid var(--averis-border);
            border-radius: 4px 4px 18px 4px;
            background: #FFFFFF;
        }

        hr {
            border-color: #E5E5E5;
        }

        .small-note {
            color: var(--averis-secondary-text);
            font-size: 13px;
        }

        /* ==========================================
           Mobile adjustments
           ========================================== */

        @media (max-width: 900px) {
            .block-container {
                padding-left: 1.2rem;
                padding-right: 1.2rem;
            }

            .brand-header {
                align-items: flex-start;
                gap: 12px;
            }

            .system-ready {
                display: none;
            }

            .main-title {
                font-size: 31px;
            }

            .st-key-top_navigation div[role="radiogroup"] {
                gap: 0;
            }

            .st-key-top_navigation div[role="radiogroup"] label {
                padding: 10px 10px;
            }

            .st-key-top_navigation div[role="radiogroup"] label p {
                font-size: 13px;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Dark Averis dashboard theme
#
# This second style layer intentionally overrides the earlier base styles.
# Keeping it separate makes the visual theme easy to replace without changing
# the application's data, validation, comparison, or export logic.
# ============================================================

st.markdown(
    """
    <style>
        :root {
            --brand-orange: #F4A62A;
            --brand-orange-dark: #D98912;
            --page-bg: #080D12;
            --nav-bg: #0D131A;
            --panel-bg: #111821;
            --panel-hover: #151E29;
            --panel-soft: #0E151D;
            --border: #202A36;
            --border-strong: #2C3744;
            --text-main: #F4F7FB;
            --text-soft: #99A5B7;
            --text-muted: #697689;
            --success: #33D69F;
            --danger: #F35D77;
            --warning: #F4A62A;
            --info: #6C89FF;
        }

        html,
        body,
        [class*="css"] {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .stApp,
        [data-testid="stAppViewContainer"] {
            background: var(--page-bg);
            color: var(--text-main);
        }

        [data-testid="stHeader"] {
            background: rgba(8, 13, 18, 0.94);
            border-bottom: 1px solid rgba(32, 42, 54, 0.65);
        }

        [data-testid="stToolbar"] {
            color: var(--text-soft);
        }

        [data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            max-width: 1500px;
            padding: 1.15rem 1.25rem 4rem;
        }

        /* ---------- Brand and top navigation ---------- */

        .app-brand-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            margin: 0 0 8px;
        }

        .app-wordmark {
            color: #FFFFFF;
            font-size: 24px;
            font-weight: 900;
            font-style: italic;
            letter-spacing: -1.2px;
            line-height: 1;
        }

        .app-wordmark-accent {
            display: inline-block;
            width: 19px;
            height: 5px;
            margin-right: -18px;
            margin-bottom: 18px;
            border-radius: 50% 50% 0 0;
            background: var(--brand-orange);
            transform: rotate(-7deg);
        }

        .app-system-state {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 12px;
            color: var(--text-soft);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 999px;
            font-size: 12px;
            font-weight: 650;
        }

        .app-system-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--brand-orange);
            box-shadow: 0 0 0 4px rgba(244, 166, 42, 0.10);
        }

        .st-key-top_navigation {
            margin: 0 0 12px;
            padding: 0;
            background: transparent;
            border: 0;
        }

        .st-key-top_navigation div[role="radiogroup"] {
            display: flex;
            flex-flow: row wrap;
            align-items: center;
            gap: 8px;
        }

        .st-key-top_navigation div[role="radiogroup"] label {
            min-height: 37px;
            margin: 0;
            padding: 8px 17px;
            color: var(--text-soft);
            background: transparent;
            border: 1px solid var(--border);
            border-radius: 999px;
            cursor: pointer;
            transition: color 160ms ease, background 160ms ease,
                border-color 160ms ease, transform 160ms ease;
        }

        .st-key-top_navigation div[role="radiogroup"]
        label > div:first-child {
            display: none;
        }

        .st-key-top_navigation [data-baseweb="radio"] > div:first-child {
            display: none !important;
        }

        .st-key-top_navigation div[role="radiogroup"] label p {
            margin: 0;
            color: inherit !important;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
        }

        .st-key-top_navigation div[role="radiogroup"] label:hover {
            color: var(--brand-orange);
            background: rgba(244, 166, 42, 0.08);
            border-color: rgba(244, 166, 42, 0.46);
            transform: translateY(-1px);
        }

        .st-key-top_navigation div[role="radiogroup"]
        label:has(input:checked) {
            color: #111820;
            background: var(--brand-orange);
            border-color: var(--brand-orange);
            box-shadow: 0 5px 16px rgba(244, 166, 42, 0.20);
        }

        .st-key-top_navigation div[role="radiogroup"]
        label:has(input:focus-visible) {
            outline: 3px solid rgba(244, 166, 42, 0.28);
            outline-offset: 2px;
        }

        .top-divider {
            height: 1px;
            margin: 4px 0 32px;
            background: var(--border);
        }

        /* ---------- Typography ---------- */

        .main-title {
            margin: 0 0 5px;
            color: var(--text-main);
            font-size: clamp(31px, 3vw, 43px);
            font-weight: 850;
            font-style: normal;
            letter-spacing: -1.2px;
            line-height: 1.08;
        }

        .subtitle {
            margin: 0 0 23px;
            color: var(--text-muted);
            font-size: 14px;
            font-style: italic;
            line-height: 1.55;
        }

        h1,
        h2,
        h3,
        h4,
        p,
        label,
        li {
            color: var(--text-main);
        }

        h2,
        h3 {
            letter-spacing: -0.25px;
        }

        h2::after {
            display: none;
        }

        [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] p,
        small {
            color: var(--text-muted) !important;
        }

        /* ---------- Data controls ---------- */

        .st-key-data_controls [data-testid="stExpander"] {
            margin: 0 0 26px;
        }

        [data-testid="stExpander"] {
            overflow: hidden;
            color: var(--text-main);
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
        }

        [data-testid="stExpander"] summary:hover {
            color: var(--brand-orange);
            background: var(--panel-hover);
        }

        /* ---------- Metric cards ---------- */

        [data-testid="stMetric"] {
            min-height: 118px;
            padding: 18px 18px 16px;
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-left: 4px solid var(--brand-orange);
            border-radius: 10px;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.14);
            transition: transform 160ms ease, border-color 160ms ease,
                background 160ms ease;
        }

        [data-testid="stMetric"]:hover {
            background: var(--panel-hover);
            border-color: #344152;
            border-left-color: var(--brand-orange);
            transform: translateY(-2px);
        }

        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] p {
            color: var(--text-soft) !important;
            font-size: 13px;
            font-weight: 550;
        }

        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] div {
            color: var(--text-main) !important;
            font-size: 31px;
            font-weight: 800;
        }

        /* ---------- Buttons ---------- */

        div.stButton > button,
        div.stDownloadButton > button {
            min-height: 41px;
            padding: 8px 18px;
            color: #10161E;
            background: var(--brand-orange);
            border: 1px solid var(--brand-orange);
            border-radius: 9px;
            font-size: 13px;
            font-weight: 750;
            box-shadow: none;
            transition: background 160ms ease, border-color 160ms ease,
                transform 160ms ease, box-shadow 160ms ease;
        }

        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            color: #FFFFFF;
            background: var(--brand-orange-dark);
            border-color: var(--brand-orange-dark);
            box-shadow: 0 7px 18px rgba(244, 166, 42, 0.18);
            transform: translateY(-1px);
        }

        div.stButton > button:focus-visible,
        div.stDownloadButton > button:focus-visible {
            outline: 3px solid rgba(244, 166, 42, 0.25);
            outline-offset: 2px;
        }

        div.stButton > button:disabled {
            color: #606B7A;
            background: #1A222D;
            border-color: #252F3C;
        }

        /* ---------- Form controls ---------- */

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea,
        [data-baseweb="select"] > div,
        [data-testid="stFileUploaderDropzone"] {
            color: var(--text-main) !important;
            background: var(--panel-bg) !important;
            border-color: var(--border-strong) !important;
            border-radius: 9px !important;
        }

        [data-testid="stTextInput"] input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder {
            color: var(--text-muted);
        }

        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus,
        [data-baseweb="select"] > div:focus-within {
            border-color: var(--brand-orange) !important;
            box-shadow: 0 0 0 2px rgba(244, 166, 42, 0.16) !important;
        }

        [data-testid="stTextArea"] textarea:disabled {
            color: #C4CDDA !important;
            -webkit-text-fill-color: #C4CDDA !important;
            opacity: 1;
        }

        [data-testid="stFileUploaderDropzone"] button {
            color: var(--text-main);
            background: #1A2430;
            border-color: var(--border-strong);
        }

        /* ---------- Tabs ---------- */

        [data-baseweb="tab-list"] {
            gap: 24px;
            border-bottom: 1px solid var(--border);
        }

        [data-baseweb="tab"] {
            color: var(--text-soft);
            background: transparent;
            font-size: 13px;
            font-weight: 600;
        }

        [data-baseweb="tab"]:hover,
        [aria-selected="true"][data-baseweb="tab"] {
            color: var(--brand-orange);
        }

        [data-baseweb="tab-highlight"] {
            background: var(--brand-orange);
        }

        /* ---------- Alerts and status banners ---------- */

        [data-testid="stAlert"] {
            color: var(--text-main);
            background: #1B1711;
            border: 1px solid #5B401A;
            border-radius: 9px;
        }

        [data-testid="stAlert"] p {
            color: inherit;
        }

        .status-ok,
        .status-mismatch,
        .status-review,
        .status-neutral {
            padding: 14px 16px;
            color: var(--text-main);
            background: var(--panel-bg);
            border-radius: 9px;
            font-size: 13px;
            font-weight: 650;
        }

        .status-ok {
            border: 1px solid rgba(51, 214, 159, 0.35);
            border-left: 4px solid var(--success);
        }

        .status-mismatch {
            border: 1px solid rgba(243, 93, 119, 0.35);
            border-left: 4px solid var(--danger);
        }

        .status-review {
            border: 1px solid rgba(244, 166, 42, 0.35);
            border-left: 4px solid var(--warning);
        }

        .status-neutral {
            border: 1px solid var(--border-strong);
            border-left: 4px solid #697689;
        }

        /* ---------- Dataframes and charts ---------- */

        [data-testid="stDataFrame"] {
            overflow: hidden;
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
        }

        [data-testid="stPlotlyChart"] {
            overflow: hidden;
            padding: 10px;
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
        }

        /* ---------- Dividers and links ---------- */

        hr {
            border-color: var(--border);
        }

        a {
            color: var(--brand-orange);
        }

        code {
            color: #FFD18A;
            background: #161D26;
        }

        /* ---------- Responsive layout ---------- */

        @media (max-width: 900px) {
            .block-container {
                padding-right: 0.9rem;
                padding-left: 0.9rem;
            }

            .app-system-state {
                display: none;
            }

            .st-key-top_navigation div[role="radiogroup"] {
                gap: 6px;
            }

            .st-key-top_navigation div[role="radiogroup"] label {
                padding: 7px 11px;
            }

            .st-key-top_navigation div[role="radiogroup"] label p {
                font-size: 12px;
            }

            [data-testid="stMetric"] {
                min-height: 102px;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Data-loading functions
# ============================================================

@st.cache_resource
def create_inbox(source: str) -> Inbox:
    """Create one reusable Inbox connection."""
    return Inbox(source)


@st.cache_data
def load_emails(source: str) -> list[dict[str, Any]]:
    """Load all email records from the supplied bundle or HTTP server."""
    inbox = Inbox(source)
    return inbox.emails()


@st.cache_data
def load_submission_from_file(
    path_text: str,
    modified_time: float,
) -> dict[str, dict[str, Any]]:
    """
    Load the team's generated results.

    modified_time is included so Streamlit refreshes its cache when
    submission.json changes.
    """
    del modified_time

    path = Path(path_text)

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "submission.json must contain one JSON object keyed by email ID."
        )

    return data


def get_submission() -> dict[str, dict[str, Any]]:
    """Load output/submission.json if it exists."""
    if not SUBMISSION_FILE.exists():
        return {}

    return load_submission_from_file(
        str(SUBMISSION_FILE),
        SUBMISSION_FILE.stat().st_mtime,
    )


def load_uploaded_submission(uploaded_file) -> dict[str, dict[str, Any]]:
    """Load a result JSON selected through the sidebar."""
    uploaded_file.seek(0)
    data = json.load(uploaded_file)

    if not isinstance(data, dict):
        raise ValueError(
            "The uploaded file must contain one JSON object keyed by email ID."
        )

    return data


def normalise_result(
    email_id: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a safe result object for displaying in the dashboard."""
    if not isinstance(result, dict):
        return {
            "email_id": email_id,
            "category": "NOT_PROCESSED",
            "status": "NOT_PROCESSED",
            "review_reason": None,
            "defect_fields": [],
            "has_defect": False,
        }

    category = result.get("category", "NOT_PROCESSED")
    status = result.get("status")

    if category != "BL_COMPARISON":
        status = status or "NOT_APPLICABLE"
    else:
        status = status or "NOT_PROCESSED"

    defect_fields = result.get("defect_fields") or []

    if not isinstance(defect_fields, list):
        defect_fields = []

    return {
        **result,
        "email_id": email_id,
        "category": category,
        "status": status,
        "review_reason": result.get("review_reason"),
        "defect_fields": defect_fields,
        "has_defect": bool(result.get("has_defect", False)),
    }


def create_results_dataframe(
    emails: list[dict[str, Any]],
    submission: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Combine source email information with generated results."""
    rows = []

    for email in emails:
        email_id = email["email_id"]
        result = normalise_result(
            email_id,
            submission.get(email_id),
        )

        rows.append(
            {
                "Email ID": email_id,
                "Sender": email.get("from", ""),
                "Subject": email.get("subject", ""),
                "Attachments": len(email.get("attachments", [])),
                "Category": result["category"],
                "Category Display": CATEGORY_DISPLAY_NAMES.get(
                    result["category"],
                    result["category"].replace("_", " ").title(),
                ),
                "Status": result["status"],
                "Status Display": STATUS_DISPLAY_NAMES.get(
                    result["status"],
                    result["status"].replace("_", " ").title(),
                ),
                "Has Defect": result["has_defect"],
                "Defect Fields": ", ".join(result["defect_fields"]),
                "Issue Count": len(result["defect_fields"]),
                "Review Reason": result["review_reason"] or "",
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# Validation functions
# ============================================================

def validate_submission(
    emails: list[dict[str, Any]],
    submission: dict[str, dict[str, Any]],
) -> list[str]:
    """Check the final output before download or self-evaluation."""
    errors: list[str] = []
    expected_ids = {email["email_id"] for email in emails}
    actual_ids = set(submission)

    missing_ids = sorted(expected_ids - actual_ids)
    extra_ids = sorted(actual_ids - expected_ids)

    if missing_ids:
        errors.append(
            f"{len(missing_ids)} email IDs are missing from the results."
        )

    if extra_ids:
        errors.append(
            f"{len(extra_ids)} unexpected email IDs are present."
        )

    for email_id in sorted(expected_ids & actual_ids):
        result = submission[email_id]

        if not isinstance(result, dict):
            errors.append(f"{email_id}: the result must be a JSON object.")
            continue

        category = result.get("category")
        status = result.get("status")
        has_defect = result.get("has_defect")
        defect_fields = result.get("defect_fields")
        review_reason = result.get("review_reason")

        if category not in VALID_CATEGORIES:
            errors.append(
                f"{email_id}: invalid category {category!r}."
            )

        if status not in VALID_STATUSES:
            errors.append(
                f"{email_id}: invalid status {status!r}."
            )

        if not isinstance(has_defect, bool):
            errors.append(
                f"{email_id}: has_defect must be true or false."
            )

        if not isinstance(defect_fields, list):
            errors.append(
                f"{email_id}: defect_fields must be a list."
            )
            defect_fields = []

        invalid_fields = [
            field
            for field in defect_fields
            if field not in COMPARISON_FIELDS
        ]

        if invalid_fields:
            errors.append(
                f"{email_id}: invalid defect fields: "
                f"{', '.join(invalid_fields)}."
            )

        if status == "MISMATCH":
            if not has_defect:
                errors.append(
                    f"{email_id}: MISMATCH must have has_defect=true."
                )

            if not defect_fields:
                errors.append(
                    f"{email_id}: MISMATCH must identify defect_fields."
                )

        if status == "OK" and has_defect:
            errors.append(
                f"{email_id}: OK cannot have has_defect=true."
            )

        if status == "NEEDS_REVIEW":
            if review_reason not in VALID_REVIEW_REASONS:
                errors.append(
                    f"{email_id}: NEEDS_REVIEW requires a valid "
                    "review_reason."
                )
        elif review_reason is not None:
            errors.append(
                f"{email_id}: review_reason should be null unless "
                "status is NEEDS_REVIEW."
            )

    return errors


# ============================================================
# Presentation functions
# ============================================================

def render_page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<p class="main-title">{title}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="subtitle">{subtitle}</p>',
        unsafe_allow_html=True,
    )


def render_status_banner(result: dict[str, Any]) -> None:
    status = result["status"]
    defect_fields = result.get("defect_fields", [])

    if status == "OK":
        st.markdown(
            '<div class="status-ok">'
            "✓ No mismatch detected. All seven required fields match."
            "</div>",
            unsafe_allow_html=True,
        )

    elif status == "MISMATCH":
        issue_count = len(defect_fields)
        st.markdown(
            '<div class="status-mismatch">'
            f"⚠ Mismatch detected. {issue_count} field(s) require attention."
            "</div>",
            unsafe_allow_html=True,
        )

    elif status == "NEEDS_REVIEW":
        reason = result.get("review_reason") or "uncertain result"

        st.markdown(
            '<div class="status-review">'
            f"! Human review required: {reason.replace('_', ' ')}."
            "</div>",
            unsafe_allow_html=True,
        )

    else:
        st.markdown(
            '<div class="status-neutral">'
            "This email has not been processed yet."
            "</div>",
            unsafe_allow_html=True,
        )


def build_comparison_dataframe(
    result: dict[str, Any],
) -> pd.DataFrame:
    """
    Build the seven-field comparison table.

    For the richest dashboard, the team pipeline may include:
    "comparisons": {
        "shipper": {
            "si_value": "...",
            "bl_value": "...",
            "result": "MATCH"
        }
    }

    The formal submission fields remain unchanged.
    """
    comparisons = result.get("comparisons", {})
    defect_fields = set(result.get("defect_fields", []))
    rows = []

    for field in COMPARISON_FIELDS:
        evidence = comparisons.get(field, {})

        if evidence:
            field_result = evidence.get(
                "result",
                "MISMATCH" if field in defect_fields else "MATCH",
            )
        elif result["status"] == "NOT_PROCESSED":
            field_result = "Not processed"
        elif field in defect_fields:
            field_result = "Mismatch"
        else:
            field_result = "Match"

        rows.append(
            {
                "Field": field.replace("_", " ").title(),
                "SI Value": evidence.get("si_value", "Not available"),
                "BL Value": evidence.get("bl_value", "Not available"),
                "Result": str(field_result).replace("_", " ").title(),
                "Confidence": evidence.get("confidence", "—"),
            }
        )

    return pd.DataFrame(rows)


def display_attachment(
    inbox: Inbox,
    attachment_path: str,
    key_prefix: str,
) -> None:
    """Display TXT attachments and provide downloads for every format."""
    filename = Path(attachment_path).name
    extension = Path(attachment_path).suffix.lower()

    try:
        attachment_bytes = inbox.read_bytes(attachment_path)
    except Exception as error:
        st.error(f"Could not open {filename}: {error}")
        return

    st.markdown(f"**{filename}**")

    st.download_button(
        label=f"Download {filename}",
        data=attachment_bytes,
        file_name=filename,
        mime="application/octet-stream",
        key=f"{key_prefix}_{filename}",
    )

    if extension == ".txt":
        text = attachment_bytes.decode(
            "utf-8",
            errors="replace",
        )

        st.text_area(
            label=f"Contents of {filename}",
            value=text,
            height=350,
            disabled=True,
            key=f"text_{key_prefix}_{filename}",
        )
    else:
        st.info(
            f"{extension.upper().replace('.', '')} attachment detected. "
            "Use the download button or connect the team's document "
            "preview/extraction component here."
        )


# ============================================================
# Dark top navigation and compact data controls
# ============================================================

st.markdown(
    '<div class="app-brand-row">'
    '<div class="app-wordmark">'
    '<span class="app-wordmark-accent"></span>'
    'averis'
    '</div>'
    '<div class="app-system-state">'
    '<span class="app-system-dot"></span>'
    'System Ready'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

page = st.radio(
    "Navigation",
    options=[
        "Dashboard",
        "Inbox",
        "Document Comparison",
        "Review Queue",
        "Results & Analytics",
        "System Information",
    ],
    horizontal=True,
    label_visibility="collapsed",
    key="top_navigation",
)

st.markdown(
    '<div class="top-divider"></div>',
    unsafe_allow_html=True,
)

default_source = os.getenv(
    "DATA_SOURCE",
    str(PROJECT_ROOT),
)

with st.expander("Data controls", expanded=False):
    control_col_1, control_col_2, control_col_3 = st.columns(
        [2.2, 1.6, 0.7],
        vertical_alignment="bottom",
    )

    with control_col_1:
        data_source = st.text_input(
            "Data source",
            value=default_source,
            help=(
                "Use the project directory for the static bundle or an "
                "HTTP address such as http://data-server:8080."
            ),
        )

    with control_col_2:
        uploaded_submission = st.file_uploader(
            "Load results JSON",
            type=["json"],
            help=(
                "Optional: upload the team's generated submission. "
                "Otherwise output/submission.json is used."
            ),
        )

    with control_col_3:
        if st.button(
            "Refresh",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()


# ============================================================
# Load application data
# ============================================================

try:
    inbox = create_inbox(data_source)
    emails = load_emails(data_source)

except Exception as error:
    render_page_header(
        "Shipping Document Verification",
        "From inbox classification to discrepancy reporting",
    )

    st.error(
        "The inbox could not be loaded. Check that loader.py, inbox/, "
        "and attachments/ are in the project directory."
    )

    with st.expander("Technical details"):
        st.exception(error)

    st.stop()


try:
    if uploaded_submission is not None:
        submission = load_uploaded_submission(uploaded_submission)
        submission_source = "Uploaded JSON"
    else:
        submission = get_submission()
        submission_source = (
            "output/submission.json"
            if submission
            else "No result file"
        )

except Exception as error:
    st.error(f"The result JSON could not be loaded: {error}")
    submission = {}
    submission_source = "Invalid result file"

results_df = create_results_dataframe(
    emails,
    submission,
)

email_lookup = {
    email["email_id"]: email
    for email in emails
}


# ============================================================
# Dashboard page
# ============================================================

if page == "Dashboard":
    render_page_header(
        "Dashboard",
        "From inbox classification to explainable discrepancy reporting",
    )

    top_left, top_right = st.columns(
        [4, 1],
        vertical_alignment="center",
    )

    with top_left:
        st.caption(
            f"Data source: {data_source} · "
            f"Results: {submission_source}"
        )

    with top_right:
        st.caption(
            "Updated "
            + datetime.now().strftime("%d %b %Y, %H:%M")
        )

    processed_df = results_df[
        results_df["Category"] != "NOT_PROCESSED"
    ]

    comparison_count = int(
        (processed_df["Category"] == "BL_COMPARISON").sum()
    )
    ok_count = int(
        (processed_df["Status"] == "OK").sum()
    )
    mismatch_count = int(
        (processed_df["Status"] == "MISMATCH").sum()
    )
    review_count = int(
        (processed_df["Status"] == "NEEDS_REVIEW").sum()
    )

    metric_columns = st.columns(5)

    metric_columns[0].metric(
        "Total Emails",
        len(emails),
    )
    metric_columns[1].metric(
        "Comparison Requests",
        comparison_count,
    )
    metric_columns[2].metric(
        "No Mismatch",
        ok_count,
    )
    metric_columns[3].metric(
        "Mismatches",
        mismatch_count,
    )
    metric_columns[4].metric(
        "Needs Review",
        review_count,
    )

    st.write("")

    if not submission:
        st.warning(
            "No generated result file was found. The inbox is available, "
            "but classification and comparison statistics will appear only "
            "after your team's pipeline creates output/submission.json."
        )

    else:
        chart_left, chart_right = st.columns(2)

        with chart_left:
            st.subheader("Email Classification Summary")

            category_counts = (
                processed_df["Category Display"]
                .value_counts()
                .rename_axis("Category")
                .reset_index(name="Count")
            )

            category_chart = px.bar(
                category_counts,
                x="Category",
                y="Count",
                text="Count",
                color="Category",
                color_discrete_sequence=[
                    "#F4A62A",
                    "#6C89FF",
                    "#33D69F",
                    "#8B97A9",
                    "#F35D77",
                ],
            )

            category_chart.update_layout(
                showlegend=False,
                height=380,
                margin=dict(l=20, r=20, t=20, b=20),
                xaxis_title="",
                yaxis_title="Number of emails",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#99A5B7",
                xaxis=dict(gridcolor="#202A36"),
                yaxis=dict(gridcolor="#202A36"),
            )

            st.plotly_chart(
                category_chart,
                use_container_width=True,
            )

        with chart_right:
            st.subheader("Document Verification Outcomes")

            comparison_df = processed_df[
                processed_df["Category"] == "BL_COMPARISON"
            ]

            status_counts = (
                comparison_df["Status Display"]
                .value_counts()
                .rename_axis("Status")
                .reset_index(name="Count")
            )

            status_chart = px.bar(
                status_counts,
                x="Count",
                y="Status",
                orientation="h",
                text="Count",
                color="Status",
                color_discrete_map={
                    "No Mismatch": "#33D69F",
                    "Mismatch": "#F35D77",
                    "Needs Review": "#F4A62A",
                },
            )

            status_chart.update_layout(
                showlegend=False,
                height=380,
                margin=dict(l=20, r=20, t=20, b=20),
                xaxis_title="Number of cases",
                yaxis_title="",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#99A5B7",
                xaxis=dict(gridcolor="#202A36"),
                yaxis=dict(gridcolor="#202A36"),
            )

            st.plotly_chart(
                status_chart,
                use_container_width=True,
            )

    st.subheader("Recent Cases")

    recent_columns = [
        "Email ID",
        "Subject",
        "Category Display",
        "Status Display",
        "Issue Count",
    ]

    st.dataframe(
        results_df[recent_columns].tail(15),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category Display": "Category",
            "Status Display": "Status",
            "Issue Count": "Issues",
        },
    )


# ============================================================
# Inbox page
# ============================================================

elif page == "Inbox":
    render_page_header(
        "Inbox Classification",
        "Browse all emails and inspect their classification results.",
    )

    filter_col_1, filter_col_2, filter_col_3 = st.columns(
        [2, 1, 1]
    )

    with filter_col_1:
        search_term = st.text_input(
            "Search",
            placeholder="Email ID, subject, or sender",
        )

    with filter_col_2:
        category_options = ["All"] + sorted(
            results_df["Category Display"].unique().tolist()
        )

        selected_category = st.selectbox(
            "Category",
            category_options,
        )

    with filter_col_3:
        attachment_filter = st.selectbox(
            "Attachments",
            [
                "All",
                "Has attachments",
                "No attachments",
            ],
        )

    filtered_df = results_df.copy()

    if search_term:
        search_mask = (
            filtered_df["Email ID"]
            .str.contains(search_term, case=False, na=False)
            | filtered_df["Subject"]
            .str.contains(search_term, case=False, na=False)
            | filtered_df["Sender"]
            .str.contains(search_term, case=False, na=False)
        )
        filtered_df = filtered_df[search_mask]

    if selected_category != "All":
        filtered_df = filtered_df[
            filtered_df["Category Display"] == selected_category
        ]

    if attachment_filter == "Has attachments":
        filtered_df = filtered_df[
            filtered_df["Attachments"] > 0
        ]
    elif attachment_filter == "No attachments":
        filtered_df = filtered_df[
            filtered_df["Attachments"] == 0
        ]

    st.caption(f"{len(filtered_df)} email(s) displayed")

    inbox_columns = [
        "Email ID",
        "Sender",
        "Subject",
        "Attachments",
        "Category Display",
        "Status Display",
    ]

    st.dataframe(
        filtered_df[inbox_columns],
        use_container_width=True,
        hide_index=True,
        height=430,
        column_config={
            "Category Display": "Category",
            "Status Display": "Status",
        },
    )

    if filtered_df.empty:
        st.info("No emails match the selected filters.")
    else:
        selected_email_id = st.selectbox(
            "Open an email",
            filtered_df["Email ID"].tolist(),
        )

        selected_email = email_lookup[selected_email_id]
        selected_result = normalise_result(
            selected_email_id,
            submission.get(selected_email_id),
        )

        st.divider()
        st.subheader(selected_email.get("subject", "No subject"))

        detail_col_1, detail_col_2, detail_col_3 = st.columns(3)

        detail_col_1.markdown(
            f"**Email ID:** {selected_email_id}"
        )
        detail_col_2.markdown(
            f"**Sender:** {selected_email.get('from', 'Unknown')}"
        )
        detail_col_3.markdown(
            "**Category:** "
            + CATEGORY_DISPLAY_NAMES.get(
                selected_result["category"],
                selected_result["category"]
                .replace("_", " ")
                .title(),
            )
        )

        email_tab, attachment_tab = st.tabs(
            ["Email Body", "Attachments"]
        )

        with email_tab:
            st.text_area(
                "Message",
                value=selected_email.get("body", ""),
                height=350,
                disabled=True,
            )

        with attachment_tab:
            attachments = selected_email.get("attachments", [])

            if not attachments:
                st.info("This email has no attachments.")
            else:
                for index, attachment_path in enumerate(
                    attachments
                ):
                    display_attachment(
                        inbox,
                        attachment_path,
                        f"inbox_{selected_email_id}_{index}",
                    )
                    st.divider()


# ============================================================
# Document Comparison page
# ============================================================

elif page == "Document Comparison":
    render_page_header(
        "Document Comparison",
        "Inspect SI and draft BL values side by side.",
    )

    comparison_email_ids = results_df.loc[
        results_df["Category"] == "BL_COMPARISON",
        "Email ID",
    ].tolist()

    if not comparison_email_ids:
        st.info(
            "No emails are currently classified as BL comparison requests. "
            "Load your team's generated output to display comparisons."
        )

    else:
        selected_email_id = st.selectbox(
            "Select comparison request",
            comparison_email_ids,
        )

        selected_email = email_lookup[selected_email_id]
        selected_result = normalise_result(
            selected_email_id,
            submission.get(selected_email_id),
        )

        summary_col_1, summary_col_2 = st.columns([3, 1])

        with summary_col_1:
            st.subheader(
                selected_email.get("subject", "No subject")
            )
            st.caption(
                f"{selected_email_id} · "
                f"{selected_email.get('from', 'Unknown sender')}"
            )

        with summary_col_2:
            st.metric(
                "Issues",
                len(selected_result.get("defect_fields", [])),
            )

        render_status_banner(selected_result)
        st.write("")

        email_tab, si_tab, bl_tab = st.tabs(
            [
                "Email",
                "Shipping Instruction",
                "Draft Bill of Lading",
            ]
        )

        with email_tab:
            st.text_area(
                "Email body",
                value=selected_email.get("body", ""),
                height=320,
                disabled=True,
            )

        attachments = selected_email.get("attachments", [])

        si_attachments = [
            path
            for path in attachments
            if "_SI" in Path(path).stem.upper()
        ]

        bl_attachments = [
            path
            for path in attachments
            if "_BL" in Path(path).stem.upper()
        ]

        with si_tab:
            if not si_attachments:
                st.warning(
                    "No Shipping Instruction attachment was found."
                )
            else:
                for index, path in enumerate(si_attachments):
                    display_attachment(
                        inbox,
                        path,
                        f"si_{selected_email_id}_{index}",
                    )

        with bl_tab:
            if not bl_attachments:
                st.warning(
                    "No draft Bill of Lading attachment was found."
                )
            else:
                for index, path in enumerate(bl_attachments):
                    display_attachment(
                        inbox,
                        path,
                        f"bl_{selected_email_id}_{index}",
                    )

        st.subheader("Seven-Field Comparison")

        comparison_table = build_comparison_dataframe(
            selected_result
        )

        st.dataframe(
            comparison_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "SI Value": st.column_config.TextColumn(
                    width="large"
                ),
                "BL Value": st.column_config.TextColumn(
                    width="large"
                ),
            },
        )

        if selected_result["status"] == "MISMATCH":
            readable_fields = [
                field.replace("_", " ").title()
                for field in selected_result["defect_fields"]
            ]

            st.error(
                "Fields requiring attention: "
                + ", ".join(readable_fields)
            )

        elif selected_result["status"] == "NEEDS_REVIEW":
            st.warning(
                "Review reason: "
                + str(selected_result.get("review_reason"))
                .replace("_", " ")
                .title()
            )


# ============================================================
# Review Queue page
# ============================================================

elif page == "Review Queue":
    render_page_header(
        "Human Review Queue",
        "Inspect cases that the system could not decide reliably.",
    )

    review_df = results_df[
        results_df["Status"] == "NEEDS_REVIEW"
    ].copy()

    review_metric_columns = st.columns(5)

    reason_counter = Counter(
        review_df["Review Reason"].tolist()
    )

    review_metric_columns[0].metric(
        "Awaiting Review",
        len(review_df),
    )
    review_metric_columns[1].metric(
        "Missing Attachments",
        reason_counter.get("missing_attachment", 0),
    )
    review_metric_columns[2].metric(
        "Missing Values",
        reason_counter.get("missing_value", 0),
    )
    review_metric_columns[3].metric(
        "Unreadable",
        reason_counter.get("unreadable", 0),
    )
    review_metric_columns[4].metric(
        "Wrong Document",
        reason_counter.get("wrong_doc_type", 0),
    )

    st.write("")

    if review_df.empty:
        st.success("There are no cases awaiting human review.")

    else:
        review_columns = [
            "Email ID",
            "Subject",
            "Review Reason",
            "Defect Fields",
        ]

        st.dataframe(
            review_df[review_columns],
            use_container_width=True,
            hide_index=True,
        )

        selected_email_id = st.selectbox(
            "Review a case",
            review_df["Email ID"].tolist(),
        )

        selected_email = email_lookup[selected_email_id]
        selected_result = normalise_result(
            selected_email_id,
            submission.get(selected_email_id),
        )

        render_status_banner(selected_result)

        st.text_area(
            "Email context",
            value=selected_email.get("body", ""),
            height=250,
            disabled=True,
        )

        reviewer_note = st.text_area(
            "Reviewer note",
            placeholder=(
                "Record why the result was confirmed or corrected."
            ),
        )

        decision = st.selectbox(
            "Human decision",
            [
                "Keep as NEEDS_REVIEW",
                "Confirm OK",
                "Confirm MISMATCH",
            ],
        )

        if st.button(
            "Save Review Decision",
            type="primary",
        ):
            st.info(
                "Connect this button to your team's persistent review "
                "service before final deployment."
            )

            if reviewer_note:
                st.success(
                    f"Review decision prepared: {decision}"
                )


# ============================================================
# Results and analytics page
# ============================================================

elif page == "Results & Analytics":
    render_page_header(
        "Results & Analytics",
        "Validate, inspect, and download the final system output.",
    )

    if not submission:
        st.warning(
            "No result file is available. Generate "
            "output/submission.json or upload a result JSON."
        )

    else:
        validation_errors = validate_submission(
            emails,
            submission,
        )

        validation_col_1, validation_col_2 = st.columns(
            [3, 1]
        )

        with validation_col_1:
            if validation_errors:
                st.error(
                    f"Validation found {len(validation_errors)} issue(s)."
                )

                with st.expander(
                    "View validation issues",
                    expanded=True,
                ):
                    for error in validation_errors[:100]:
                        st.write(f"- {error}")

                    if len(validation_errors) > 100:
                        st.write(
                            "- Additional validation issues were omitted."
                        )
            else:
                st.success(
                    f"Validation passed: {len(submission)} "
                    "email results are ready."
                )

        with validation_col_2:
            st.download_button(
                "Download Results JSON",
                data=json.dumps(
                    submission,
                    indent=2,
                    ensure_ascii=False,
                ),
                file_name="submission.json",
                mime="application/json",
                use_container_width=True,
            )

        display_columns = [
            "Email ID",
            "Category Display",
            "Status Display",
            "Has Defect",
            "Defect Fields",
            "Review Reason",
        ]

        st.dataframe(
            results_df[display_columns],
            use_container_width=True,
            hide_index=True,
            height=500,
            column_config={
                "Category Display": "Category",
                "Status Display": "Status",
            },
        )

        mismatch_df = results_df[
            results_df["Status"] == "MISMATCH"
        ]

        all_defect_fields: list[str] = []

        for result in submission.values():
            fields = result.get("defect_fields") or []

            if isinstance(fields, list):
                all_defect_fields.extend(fields)

        if all_defect_fields:
            st.subheader("Most Frequently Mismatched Fields")

            field_counts = (
                pd.Series(all_defect_fields)
                .value_counts()
                .rename_axis("Field")
                .reset_index(name="Count")
            )

            field_counts["Field"] = (
                field_counts["Field"]
                .str.replace("_", " ")
                .str.title()
            )

            defect_chart = px.bar(
                field_counts,
                x="Field",
                y="Count",
                text="Count",
                color_discrete_sequence=["#F35D77"],
            )

            defect_chart.update_layout(
                showlegend=False,
                xaxis_title="",
                yaxis_title="Mismatch count",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#99A5B7",
                xaxis=dict(gridcolor="#202A36"),
                yaxis=dict(gridcolor="#202A36"),
            )

            st.plotly_chart(
                defect_chart,
                use_container_width=True,
            )

        st.caption(
            f"{len(mismatch_df)} mismatch case(s) in the current results."
        )

        if inbox.is_http:
            if st.button(
                "Run Self-Evaluation",
                disabled=bool(validation_errors),
            ):
                try:
                    with st.spinner(
                        "Submitting results for self-evaluation..."
                    ):
                        scoreboard = inbox.submit(submission)

                    st.success("Self-evaluation completed.")
                    st.json(scoreboard)

                except Exception as error:
                    st.error(
                        f"Self-evaluation failed: {error}"
                    )
        else:
            st.info(
                "Self-evaluation requires the HTTP data server. "
                "The completed JSON can still be downloaded."
            )


# ============================================================
# System information page
# ============================================================

elif page == "System Information":
    render_page_header(
        "System Information",
        "Application workflow, supported inputs, and health status.",
    )

    st.subheader("Workflow")

    st.markdown(
        """
        1. Read every email from the inbox.
        2. Classify the email into one of five categories.
        3. Continue only `BL_COMPARISON` cases to document checking.
        4. Extract SI and draft BL shipment fields.
        5. Compare the seven required fields.
        6. Report `OK`, `MISMATCH`, or `NEEDS_REVIEW`.
        7. Export one final result for every email ID.
        """
    )

    information_col_1, information_col_2 = st.columns(2)

    with information_col_1:
        st.subheader("Required Categories")

        for category in sorted(VALID_CATEGORIES):
            st.write(
                "• "
                + CATEGORY_DISPLAY_NAMES.get(
                    category,
                    category,
                )
            )

        st.subheader("Compared Fields")

        for field in COMPARISON_FIELDS:
            st.write(
                "• " + field.replace("_", " ").title()
            )

    with information_col_2:
        st.subheader("System Health")

        health_data = {
            "Inbox connected": "Yes",
            "Emails loaded": len(emails),
            "Result source": submission_source,
            "Results loaded": len(submission),
            "Data mode": (
                "HTTP server"
                if inbox.is_http
                else "Static bundle"
            ),
            "Application version": "1.0",
        }

        st.json(health_data)

        if st.button("Run Health Check"):
            if len(emails) > 0:
                st.success(
                    f"Health check passed: {len(emails)} "
                    "emails are accessible."
                )
            else:
                st.error(
                    "Health check failed: no emails were loaded."
                )
