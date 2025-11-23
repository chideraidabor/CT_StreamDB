# CT_StreamDB-
CT StreamDB is a TV Series Explorer, a small web application that uses an SQL database and a Streamlit front-end. 

**Download IMDb Datasets**

This project requires IMDb's bulk data files.
Due to GitHub’s 100MB file limit, these datasets cannot be pushed to GitHub and must be downloaded manually.

**That’s where you downloaded:**
https://datasets.imdbws.com

**Download the following**
title.basics.tsv.gz
title.ratings.tsv.gz
title.episode.tsv.gz

**Extract them (macOS Terminal):**
gunzip title.basics.tsv.gz
gunzip title.ratings.tsv.gz
gunzip title.episode.tsv.gz

Create a folder called imdb_data/ and add the files in the folder

run the init_db.py to create the database called ct_streamdb.db

run the file load_imbd.py to load the imbd data into the ct_streamdb.db located in the /db folder

