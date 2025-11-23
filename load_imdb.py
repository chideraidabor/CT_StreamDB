import gzip
import csv
import sqlite3
from collections import defaultdict

IMDB_PATH = "imdb_data/"
DB_PATH = "ct_streamdb.db"

BATCH_SIZE = 5000


# ------------------------------------------------------------
#  FAST CONNECTION
# ------------------------------------------------------------
def connect_fast():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Speed settings
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

    series_batch = []
    seasons_batch = []
    episodes_batch = []

    # Insert series + seasons + episodes
    for imdb_series_id, info in series.items():

        if imdb_series_id not in episodes:
            continue

        # -----------------------------
        # Insert Series Row
        # -----------------------------
        series_batch.append(
            (
                info["title"],
                info["genre"],
                None,             # description (NULL for now)
                info["start"],
                info["end"],
                imdb_series_id
            )
        )

        if len(series_batch) >= BATCH_SIZE:
            batch_insert(
                cur,
                """INSERT INTO Series
                   (title, genre, description, start_year, end_year, imdb_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                series_batch,
            )

        # -----------------------------
        # Organize episodes by season
        # -----------------------------
        season_map = defaultdict(list)
        for ep in episodes[imdb_series_id]:
            season_map[ep["season"]].append(ep)

        # -----------------------------
        # Insert Seasons + Temp Episodes
        # -----------------------------
        for season_num, ep_list in season_map.items():

            # Insert season now (SQLite assigns season_id later)
            seasons_batch.append((imdb_series_id, season_num))

            # Insert episodes with placeholder season_id (NULL)
            for ep in ep_list:
                episodes_batch.append(
                    (
                        None,                     # season_id (filled later)
                        ep["episode"],
                        f"Episode {ep['episode']}",
                        None,                     # air_date
                        ratings.get(ep["id"]),     # rating
                        ep["id"],                  # imdb_id
                        imdb_series_id,            # series_imdb
                        season_num                 # season_tmp
                    )
                )

                if len(episodes_batch) >= BATCH_SIZE:
                    batch_insert(
                        cur,
                        """INSERT INTO Episodes
                           (season_id, episode_number, title, air_date, rating,
                            imdb_id, series_imdb, season_tmp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        episodes_batch,
                    )

    # Final large commits
    batch_insert(
        cur,
        """INSERT INTO Series
           (title, genre, description, start_year, end_year, imdb_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        series_batch,
    )

    batch_insert(
        cur,
        """INSERT INTO Seasons (series_id, season_number)
           VALUES (?, ?)""",
        seasons_batch,
    )

    batch_insert(
        cur,
        """INSERT INTO Episodes
           (season_id, episode_number, title, air_date, rating,
            imdb_id, series_imdb, season_tmp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        episodes_batch,
    )


    print("\n=== PHASE 3: LINK EPISODES TO SEASONS ===")

    # 1. Load season rows (we need series_imdb + season_number)
    cur.execute("""
        SELECT s.season_id, se.imdb_id AS series_imdb, s.season_number
        FROM Seasons s
        JOIN Series se ON s.series_id = se.series_id
    """)

    seasons = cur.fetchall()

    for season_id, series_imdb, season_number in seasons:

        # 2. Update episodes that belong to this season
        cur.execute("""
            UPDATE Episodes
            SET season_id = ?
            WHERE series_imdb = ?
              AND season_tmp = ?
        """, (season_id, series_imdb, season_number))

        # 3. Compute stats for the season
        cur.execute("""
            SELECT COUNT(*), AVG(rating)
            FROM Episodes
            WHERE season_id = ?
        """, (season_id,))

        count, avg_rating = cur.fetchone()

        cur.execute("""
            UPDATE Seasons
            SET num_episodes = ?, avg_rating = ?
            WHERE season_id = ?
        """, (count, avg_rating, season_id))

    print("✔ Episode linking complete")


    conn.commit()
    conn.close()

    print("\n🎉 DONE! IMDb dataset loaded successfully.")


if __name__ == "__main__":
    main()
