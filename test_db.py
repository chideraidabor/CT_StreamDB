import sqlite3
import os

DB_PATH = "ct_streamdb.db"   # change to your actual filename


def connect_db():
    print("Testing database connection...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        print("Database connection working!\n")
        return conn
    except Exception as e:
        print("Failed to connect:", e)
        exit()
        


def test_table_exists(conn, table_name):
    print(f"Testing if table '{table_name}' exists...")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?;
    """, (table_name,))
    
    result = cursor.fetchone()
    if result:
        print(f"Table '{table_name}' exists!\n")
    else:
        print(f"Table '{table_name}' does NOT exist.\n")
        exit()


def test_insert_actor(conn):
    print("Testing INSERT into actors...")
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM actors;")  # clean test
    conn.commit()

    cursor.execute("""
        INSERT INTO actors (name, birth_year)
        VALUES (?, ?);
    """, ("Test Actor", 1990))
    conn.commit()

    cursor.execute("SELECT * FROM actors WHERE name=?", ("Test Actor",))
    row = cursor.fetchone()

    if row:
        print("Actor insert & select working:", row, "\n")
    else:
        print("Actor insert/select failed.\n")
        exit()


def test_insert_movie(conn):
    print("Testing INSERT into movies...")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM movies;")  # clean test
    conn.commit()

    cursor.execute("""
        INSERT INTO movies (title, year, rating)
        VALUES (?, ?, ?);
    """, ("Test Movie", 2024, 8.5))
    conn.commit()

    cursor.execute("SELECT * FROM movies WHERE title=?", ("Test Movie",))
    row = cursor.fetchone()

    if row:
        print("Movie insert & select working:", row, "\n")
    else:
        print("Movie insert/select failed.\n")
        exit()


def test_insert_role(conn):
    print("Testing roles (actor-movie relationship)...")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM roles;")
    conn.commit()

    # get existing actor + movie
    cursor.execute("SELECT actor_id FROM actors LIMIT 1;")
    actor_id = cursor.fetchone()[0]

    cursor.execute("SELECT movie_id FROM movies LIMIT 1;")
    movie_id = cursor.fetchone()[0]

    cursor.execute("""
        INSERT INTO roles (actor_id, movie_id, role_name)
        VALUES (?, ?, ?);
    """, (actor_id, movie_id, "Hero"))
    conn.commit()

    cursor.execute("""
        SELECT a.name, m.title, r.role_name
        FROM roles r
        JOIN actors a ON r.actor_id = a.actor_id
        JOIN movies m ON r.movie_id = m.movie_id
        WHERE r.role_name = ?;
    """, ("Hero",))

    row = cursor.fetchone()

    if row:
        print("Role relationship working:", row, "\n")
    else:
        print("Role test failed.\n")
        exit()


def run_all_tests():
    print("\n======== RUNNING ALL DATABASE TESTS ========\n")
    
    conn = connect_db()

    # 1. Tables exist
    for table in ["actors", "movies", "roles"]:
        test_table_exists(conn, table)

    # 2. Insert/select tests
    test_insert_actor(conn)
    test_insert_movie(conn)
    test_insert_role(conn)

    conn.close()
    print("ALL TESTS PASSED SUCCESSFULLY!\n")


if __name__ == "__main__":
    run_all_tests()
