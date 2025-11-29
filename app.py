from flask import Flask, render_template, request, url_for, jsonify
import sqlite3
import requests
import re

TMDB_API_KEY = "1ee35db2f7c81fe96d65852423b76a83"
app = Flask(__name__)
poster_cache = {}

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
    # --- Check cache first ---
    key = (title, start_year)
    if key in poster_cache:
        return poster_cache[key]

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

    poster_url = None

    for q in queries:
        for ep in endpoints:
            r = tmdb_search(ep, q)
            if not r.get("results"):
                continue
            best = r["results"][0]

            poster = best.get("poster_path")
            backdrop = best.get("backdrop_path")

            if poster:
                poster_url = BASE + poster
                break
            if backdrop:
                poster_url = BASE + backdrop
                break
        if poster_url:
            break

    if not poster_url:
        if not fallback_enabled:
            poster_cache[key] = None
            return None

        poster_url = url_for('static', filename='img/no_img.png')

    # --- Store in cache before returning ---
    poster_cache[key] = poster_url
    return poster_url


# ------------------------
# ROUTES
# ------------------------
@app.route("/")
def home():
    settings = load_settings()
    fallback_enabled = settings.get("fallback_enabled", 1)

    conn = get_conn()

    top_rows = conn.execute("""
        SELECT 
            s.series_id,
            s.title,
            s.start_year,
            AVG(e.rating) AS avg_rating,
            COUNT(e.rating) AS rated_count
        FROM Series s
        JOIN Seasons se ON se.series_id = s.series_id
        JOIN Episodes e ON e.season_id = se.season_id
        WHERE e.rating IS NOT NULL
        GROUP BY s.series_id
        HAVING COUNT(e.rating) >= 6
        ORDER BY avg_rating DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    # Add poster paths
    top_series = []
    for row in top_rows:
        poster = get_poster(row["title"], row["start_year"], fallback_enabled)

        top_series.append({
            "series_id": row["series_id"],
            "title": row["title"],
            "avg_rating": row["avg_rating"],
            "rated_count": row["rated_count"],
            "poster_path": poster,
        })

    return render_template("index.html", top_series=top_series)

# @app.route("/")
# def home():
#     return render_template("index.html")

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

    final.sort(key=lambda x: "no_img.png" in x["poster_path"])
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
        series_results.sort(key=lambda x: "no_img.png" in x["poster_path"])
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

@app.route("/search_page")
def search_page():
    settings = load_settings()

    query = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    limit = settings["pagination_size"]
    poster_only = settings["poster_only"]
    fallback_enabled = settings["fallback_enabled"]

    if not query:
        return render_template(
            "search.html",
            query="",
            results=[],
            page=1,
            has_next=False,
            has_prev=False
        )

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT *
        FROM Series
        WHERE title LIKE ?
        ORDER BY title
        """,
        (f"%{query}%",)
    ).fetchall()
    conn.close()

    # Add posters and filter
    results = []
    for r in rows:
        poster = get_poster(r["title"], r["start_year"], fallback_enabled)
        is_real = poster and "no_img.png" not in poster

        if poster_only and not is_real:
            continue

        results.append({
            "series_id": r["series_id"],
            "title": r["title"],
            "genre": r["genre"],
            "start_year": r["start_year"],
            "end_year": r["end_year"],
            "poster_path": poster or "/static/img/no_img.png"
        })
    results.sort(key=lambda x: "no_img.png" in x["poster_path"])

    # pagination
    total = len(results)
    start = (page - 1) * limit
    end = start + limit
    page_slice = results[start:end]

    return render_template(
        "search.html",
        query=query,
        results=page_slice,
        page=page,
        has_prev=page > 1,
        has_next=end < total
    )


@app.route("/series/<int:series_id>")
def series_detail(series_id):
    settings = load_settings()
    fallback_enabled = settings.get("fallback_enabled", 1)

    conn = get_conn()

    # ---------------------------
    # 1. SERIES METADATA
    # ---------------------------
    row = conn.execute(
        "SELECT * FROM Series WHERE series_id = ?", (series_id,)
    ).fetchone()

    if not row:
        conn.close()
        return render_template("series_detail.html", series=None)

    series = dict(row)
    poster = get_poster(series["title"], series["start_year"], fallback_enabled)
    series["poster_path"] = poster or url_for('static', filename='img/no_img.png')

    # ---------------------------
    # 2. OVERALL AVERAGE RATING
    # ---------------------------
    total_row = conn.execute(
        """
        SELECT AVG(e.rating) AS avg_rating
        FROM Episodes e
        JOIN Seasons s ON e.season_id = s.season_id
        WHERE s.series_id = ? AND e.rating IS NOT NULL
        """,
        (series_id,)
    ).fetchone()

    total_avg = total_row["avg_rating"] if total_row["avg_rating"] is not None else None

    # ---------------------------
    # 3. GET ALL SEASONS
    # ---------------------------
    seasons_rows = conn.execute(
        """
        SELECT season_id, season_number
        FROM Seasons
        WHERE series_id = ?
        ORDER BY season_number
        """,
        (series_id,)
    ).fetchall()

    seasons = []
    total_episodes = 0

    # Season-level chart data
    season_chart = []

    # ---------------------------
    # 4. LOAD EPISODES PER SEASON
    # ---------------------------
    for s in seasons_rows:
        episodes = conn.execute(
            """
            SELECT episode_number, title, rating
            FROM Episodes
            WHERE season_id = ?
            ORDER BY episode_number
            """,
            (s["season_id"],)
        ).fetchall()

        ep_list = []
        rated_values = []

        for e in episodes:
            ep_list.append({
                "episode_number": e["episode_number"],
                "title": e["title"],
                "rating": e["rating"]
            })
            if e["rating"] is not None:
                rated_values.append(e["rating"])

        # compute season average (only rated episodes)
        avg_rating = sum(rated_values) / len(rated_values) if rated_values else None

        # add to total episode count
        total_episodes += len(ep_list)

        # append full season block for template
        seasons.append({
            "season_id": s["season_id"],
            "season_number": s["season_number"],
            "avg_rating": avg_rating,
            "num_episodes": len(ep_list),
            "episodes": ep_list
        })

        # chart data
        season_chart.append({
            "season": s["season_number"],
            "avg": avg_rating if avg_rating is not None else 0,
            "rated": len(rated_values),
            "total": len(ep_list)
        })

    conn.close()

    return render_template(
        "series_detail.html",
        series=series,
        total_avg=total_avg,
        seasons=seasons,
        num_seasons=len(seasons),
        total_episodes=total_episodes,
        season_chart=season_chart
    ) 

if __name__ == "__main__":
    app.run(debug=True)
