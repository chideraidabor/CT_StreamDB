# Fixed SQLite-only version of load_imdb.py
# Fully compatible with your ct_streamdb.db schema

import gzip
import csv
import sqlite3
from pathlib import Path
from collections import defaultdict

IMDB_PATH = "imdb_data/"
DB_PATH = Path("ct_streamdb.db")
BATCH_SIZE = 5000

# ------------------------------------------------------------
#  FAST SQLITE CONNECTION
# ------------------------------------------------------------
def connect_fast():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Speed settings for bulk insert
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=OFF;")
    cur.execute("PRAGMA temp_store=MEMORY;")
    cur.execute("PRAGMA locking_mode=EXCLUSIVE;")

    return conn, cur


def batch_insert(cursor, query, batch):
    if batch:
        cursor.executemany(query, batch)
        batch.clear()

# ------------------------------------------------------------
#  LOAD SERIES (tvSeries ONLY)
# ------------------------------------------------------------
def load_series():
    print("Loading TV series...")
    series = {}

    with gzip.open(IMDB_PATH + "title.basics.tsv.gz", "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            if row["titleType"] != "tvSeries":
                continue

            tconst = row["tconst"]

            series[tconst] = {
                "title": row["primaryTitle"],
                "start": None if row["startYear"] == "\\N" else int(row["startYear"]),
                "end": None if row["endYear"] == "\\N" else int(row["endYear"]),
                "genre": None if row["genres"] == "\\N" else row["genres"],
            }

    print(f"✔ Loaded {len(series)} series")
    return series

# ------------------------------------------------------------
#  LOAD EPISODES FOR THOSE SERIES
# ------------------------------------------------------------
def load_episodes_for_series(series_dict):
    print("Filtering episode mappings...")
    episodes_by_series = defaultdict(list)

    with gzip.open(IMDB_PATH + "title.episode.tsv.gz", "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            parent = row["parentTconst"]
            if parent not in series_dict:
                continue

            if row["seasonNumber"] == "\\N" or row["episodeNumber"] == "\\N":
                continue

            episodes_by_series[parent].append(
                {
                    "id": row["tconst"],
                    "season": int(row["seasonNumber"]),
                    "episode": int(row["episodeNumber"]),
                }
            )

    print(f"✔ Found episodes for {len(episodes_by_series)} series")
    return episodes_by_series

# ------------------------------------------------------------
#  LOAD RATINGS
# ------------------------------------------------------------
def load_ratings():
    print("Loading ratings...")
    ratings = {}

    with gzip.open(IMDB_PATH + "title.ratings.tsv.gz", "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")

        for row in reader:
            try:
                ratings[row["tconst"]] = float(row["averageRating"])
            except:
                continue

    print(f"✔ Loaded {len(ratings)} ratings")
    return ratings

# ------------------------------------------------------------
#  MAIN LOAD PROCEDURE
# ------------------------------------------------------------
def main():
    conn, cur = connect_fast()

    print("\n=== PHASE 1: LOAD RAW DATA ===")
    series = load_series()
    episodes = load_episodes_for_series(series)
    ratings = load_ratings()

    print("\n=== PHASE 2: INSERT INTO DATABASE ===")

    # 1. Insert series
    print("Inserting series into DB...")
    series_batch = []
    for imdb_id, info in series.items():
        if imdb_id not in episodes:
            continue
        series_batch.append(
            (
                info["title"],
                info["genre"],
                None,
                info["start"],
                info["end"],
                imdb_id,
                None,
            )
        )
        if len(series_batch) >= BATCH_SIZE:
            batch_insert(
                cur,
                """INSERT OR IGNORE INTO Series
                    (title, genre, description, start_year, end_year, imdb_id, poster_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                series_batch,
            )

    # final insert
    batch_insert(
        cur,
        """INSERT OR IGNORE INTO Series
            (title, genre, description, start_year, end_year, imdb_id, poster_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
        series_batch,
    )

    # Reload mapping from imdb_id → PK
    cur.execute("SELECT series_id, imdb_id FROM Series")
    imdb_to_pk = {row[1]: row[0] for row in cur.fetchall()}

    # 2. Insert seasons + episodes
    print("Inserting seasons and episodes...")
    seasons_batch = []
    episodes_batch = []

    for imdb_series_id, ep_list in episodes.items():
        series_pk = imdb_to_pk.get(imdb_series_id)
        if not series_pk:
            continue

        season_map = defaultdict(list)
        for ep in ep_list:
            season_map[ep["season"]].append(ep)

        for season_num, eps in season_map.items():
            seasons_batch.append((series_pk, season_num))

            if len(seasons_batch) >= BATCH_SIZE:
                batch_insert(cur, "INSERT OR IGNORE INTO Seasons (series_id, season_number) VALUES (?, ?)", seasons_batch)

            for ep in eps:
                episodes_batch.append(
                    (
                        None,                 # season_id (linked later)
                        ep["episode"],
                        f"Episode {ep['episode']}",
                        None,
                        ratings.get(ep["id"]),
                        ep["id"],
                        series_pk,
                        season_num,
                    )
                )

                if len(episodes_batch) >= BATCH_SIZE:
                    batch_insert(
                        cur,
                        """INSERT INTO Episodes
                            (season_id, episode_number, title, air_date, rating, imdb_id, series_id, season_tmp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        episodes_batch,
                    )

    # final bulk
    batch_insert(cur, "INSERT OR IGNORE INTO Seasons (series_id, season_number) VALUES (?, ?)", seasons_batch)

    batch_insert(
        cur,
        """INSERT INTO Episodes
            (season_id, episode_number, title, air_date, rating, imdb_id, series_id, season_tmp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        episodes_batch,
    )

    print("\n=== PHASE 3: LINK EPISODES TO SEASONS ===")

    cur.execute(
        """
        SELECT e.rowid, s.season_id
        FROM Episodes e
        JOIN Seasons s
          ON s.series_id = e.series_id AND s.season_number = e.season_tmp
        WHERE e.season_id IS NULL
        """
    )
    pairs = cur.fetchall()

    print(f"Found {len(pairs)} episode-season pairs to link.")

    for episode_rowid, season_id in pairs:
        cur.execute("UPDATE Episodes SET season_id = ? WHERE rowid = ?", (season_id, episode_rowid))

    print(f"Bulk linking complete: {len(pairs)} episodes updated.")

    print("Updating season statistics...")

    cur.execute("SELECT season_id FROM Seasons")
    for (season_id,) in cur.fetchall():
        cur.execute(
            "SELECT COUNT(*), AVG(rating) FROM Episodes WHERE season_id = ?", (season_id,)
        )
        count, avg_rating = cur.fetchone()

        cur.execute(
            "UPDATE Seasons SET num_episodes = ?, avg_rating = ? WHERE season_id = ?",
            (count, avg_rating, season_id),
        )

    conn.commit()
    conn.close()

    print("\n✔ Episode linking complete")
    print("\n🎉 DONE! IMDb dataset loaded successfully.")


if __name__ == "__main__":
    main()