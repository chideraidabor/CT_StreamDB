import sqlite3
from pathlib import Path

DB_PATH = Path("ct_streamdb.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---- SELECT QUERIES — USED BY STREAMLIT ----

def get_all_series():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Series ORDER BY title")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_series_by_id(series_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Series WHERE series_id = ?", (series_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_seasons_for_series(series_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM Seasons WHERE series_id = ? ORDER BY season_number",
        (series_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_season_by_id(season_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM Seasons WHERE season_id = ?", (season_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_episodes_for_season(season_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM Episodes WHERE season_id = ? ORDER BY episode_number",
        (season_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows
