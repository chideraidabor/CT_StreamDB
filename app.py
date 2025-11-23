from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
import requests
import re

TMDB_API_KEY = "1ee35db2f7c81fe96d65852423b76a83"
app = Flask(__name__)

# ------------------------
# DATABASE CONNECTION
# ------------------------
def get_conn():
    conn = sqlite3.connect("ct_streamdb.db")
    conn.row_factory = sqlite3.Row
    return conn

# ------------------------
# LOAD USER SETTINGS
# ------------------------
def load_settings():
    conn = get_conn()
    row = conn.execute("SELECT * FROM UserSettings WHERE id = 1").fetchone()
    conn.close()
    if not row:
        # Fallback defaults
        return {"dark_mode": 0, "poster_only": 0, "fallback_enabled": 1, "pagination_size": 100}
    return dict(row)

@app.context_processor
def inject_settings():
    return {"settings": load_settings()}

# ------------------------
# TITLE CLEANING
# ------------------------
def clean_title(title):
    t = title.strip()
    t = t.lstrip("#").strip()
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# ------------------------
# TMDB SEARCH
# ------------------------
def tmdb_search(endpoint, query):
    url = f"https://api.themoviedb.org/3/search/{endpoint}?api_key={TMDB_API_KEY}&query={query}"
    return requests.get(url).json()

# ------------------------
# SUPER POSTER FETCHER (settings aware)
# ------------------------
def get_poster(title, start_year=None, fallback_enabled=True):
    BASE = "https://image.tmdb.org/t/p/w500"
    cleaned = clean_title(title)

    queries = [cleaned]
    alpha = re.sub(r"[^a-zA-Z\s]", " ", cleaned).strip()
    if alpha and alpha not in queries:
        queries.append(alpha)
    if cleaned:
        fw = cleaned.split()[0]
        if fw and fw not in queries:
            queries.append(fw)
    if start_year:
        queries.append(f"{cleaned} {start_year}")

    endpoints = ["tv", "multi"]
    for q in queries:
        for ep in endpoints:
            r = tmdb_search(ep, q)
            if not r.get("results"):
                continue
            best = r["results"][0]
            poster = best.get("poster_path")
            backdrop = best.get("backdrop_path")
            if poster:
                return BASE + poster
            if backdrop:
                return BASE + backdrop

    # If fallback disabled, return None (so you can skip/handle)
    if not fallback_enabled:
        return None
    # fallback image
    return url_for('static', filename='img/no_img.png')

# ------------------------
# ROUTES
# ------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/series_list")
def series_list():
    settings = load_settings()

    page = int(request.args.get("page", 1))
    limit = settings["pagination_size"]
    poster_only = settings["poster_only"]
    fallback_enabled = settings["fallback_enabled"]

    offset = (page - 1) * limit
    conn = get_conn()
    rows = conn.execute(
        "SELECT series_id, title, genre, start_year, end_year FROM Series ORDER BY title LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()

    final = []
    for s in rows:
        poster = get_poster(s["title"], s["start_year"], fallback_enabled)
        has_real_poster = poster and 'no_img.png' not in poster

        if poster_only and not has_real_poster:
            continue

        final.append({
            "series_id": s["series_id"],
            "title": s["title"],
            "genre": s["genre"],
            "start_year": s["start_year"],
            "end_year": s["end_year"],
            "poster_path": poster or url_for('static', filename='img/no_img.png')
        })

    has_prev = page > 1
    # A simple way to check next page: if we got fewer rows than limit => maybe no next
    has_next = len(final) == limit

    return render_template("series_list.html",
                           series=final,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next)

@app.route("/genre")
def genre():
    settings = load_settings()

    selected_genre = request.args.get("g")
    page = int(request.args.get("page", 1))
    limit = settings["pagination_size"]
    poster_only = settings["poster_only"]
    fallback_enabled = settings["fallback_enabled"]

    conn = get_conn()
    genre_rows = conn.execute("SELECT genre FROM Series WHERE genre IS NOT NULL").fetchall()
    genres_set = set()
    for row in genre_rows:
        for g in (row["genre"] or "").split(","):
            g = g.strip()
            if g and g != "\\N":
                genres_set.add(g)
    genres = sorted(genres_set)

    series_results = []
    has_prev = False
    has_next = False

    if selected_genre:
        all_series = conn.execute("SELECT series_id, title, genre, start_year, end_year FROM Series WHERE genre LIKE ? ORDER BY title",
                                   (f"%{selected_genre}%",)).fetchall()
        conn.close()

        start = (page - 1) * limit
        stop = start + limit
        page_slice = all_series[start:stop]

        for s in page_slice:
            poster = get_poster(s["title"], s["start_year"], fallback_enabled)
            has_real_poster = poster and 'no_img.png' not in poster
            if poster_only and not has_real_poster:
                continue
            series_results.append({
                "series_id": s["series_id"],
                "title": s["title"],
                "genre": s["genre"],
                "start_year": s["start_year"],
                "end_year": s["end_year"],
                "poster_path": poster or url_for('static', filename='img/no_img.png')
            })

        has_prev = page > 1
        has_next = len(page_slice) == limit

    else:
        conn.close()

    return render_template("genre.html",
                           genres=genres,
                           selected_genre=selected_genre,
                           series=series_results,
                           page=page,
                           has_prev=has_prev,
                           has_next=has_next)

@app.route("/api/settings/get")
def get_settings():
    return jsonify(load_settings())

@app.route("/api/settings/update", methods=["POST"])
def update_settings():
    data = request.json
    conn = get_conn()
    conn.execute("""
        UPDATE UserSettings SET
            dark_mode = ?,
            poster_only = ?,
            fallback_enabled = ?,
            pagination_size = ?
        WHERE id = 1
    """, (
        data.get("dark_mode", 0),
        data.get("poster_only", 0),
        data.get("fallback_enabled", 1),
        data.get("pagination_size", 100)
    ))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/settings")
def settings_page():
    return render_template("settings.html")

@app.route("/account")
def account():
    return render_template("account.html")

if __name__ == "__main__":
    app.run(debug=True)
