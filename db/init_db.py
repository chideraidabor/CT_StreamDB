import sqlite3 
from pathlib import Path

DB_PATH = Path("ct_streamdb.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        -- Drop tables safely
        DROP TABLE IF EXISTS Episodes;
        DROP TABLE IF EXISTS Seasons;
        DROP TABLE IF EXISTS Series;
        DROP TABLE IF EXISTS UserSettings;

        CREATE TABLE Series (
            series_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL,
            genre         TEXT,
            description   TEXT,
            start_year    INTEGER,
            end_year      INTEGER,
            imdb_id       TEXT UNIQUE
        );

        CREATE TABLE Seasons (
            season_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id     INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            avg_rating    REAL,
            num_episodes  INTEGER,

            FOREIGN KEY (series_id)
                REFERENCES Series(series_id)
                ON DELETE CASCADE,

            UNIQUE(series_id, season_number)
        );

        CREATE TABLE Episodes (
            episode_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id       INTEGER,
            episode_number  INTEGER NOT NULL,
            title           TEXT NOT NULL,
            air_date        TEXT,
            rating          REAL,

            imdb_id         TEXT,
            series_imdb     TEXT,
            season_tmp      INTEGER,

            FOREIGN KEY (season_id)
                REFERENCES Seasons(season_id)
                ON DELETE CASCADE
        );

        CREATE TABLE UserSettings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            dark_mode INTEGER DEFAULT 0,
            poster_only INTEGER DEFAULT 0,
            fallback_enabled INTEGER DEFAULT 1,
            pagination_size INTEGER DEFAULT 100
        );

        CREATE INDEX idx_series_title
            ON Series(title);

        CREATE INDEX idx_seasons_series
            ON Seasons(series_id);

        CREATE INDEX idx_episodes_season
            ON Episodes(season_id);
        """
    )

    conn.commit()
    conn.close()
    print("Database initialized.")


def init_settings():
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO UserSettings (id) VALUES (1)")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    init_settings()
