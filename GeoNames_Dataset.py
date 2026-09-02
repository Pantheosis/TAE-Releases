import os
import sqlite3
import urllib.request
import zipfile

URL = "http://download.geonames.org/export/dump/cities500.zip"
ZIP_PATH = "cities500.zip"
TXT_PATH = "cities500.txt"
DB_PATH = "atlas.db"

def build_offline_atlas():
    if not os.path.exists(ZIP_PATH):
        print("Downloading cities500.zip from GeoNames...")
        urllib.request.urlretrieve(URL, ZIP_PATH)
    
    if not os.path.exists(TXT_PATH):
        print("Extracting archive...")
        with zipfile.ZipFile(ZIP_PATH, 'r') as z:
            z.extract(TXT_PATH)
            
    print("Building SQLite database (this takes a few seconds)...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS cities")
    cursor.execute("""
        CREATE TABLE cities (
            id INTEGER PRIMARY KEY,
            name TEXT,
            ascii_name TEXT,
            admin1 TEXT,
            country TEXT,
            lat REAL,
            lon REAL,
            population INTEGER
        )
    """)
    
    with open(TXT_PATH, 'r', encoding='utf-8') as f:
        rows = []
        for line in f:
            cols = line.split('\t')
            rows.append((
                int(cols[0]),       # geonameid
                cols[1],            # name
                cols[2],            # ascii_name 
                cols[10],           # admin1 code (state/province code)
                cols[8],            # country code
                float(cols[4]),     # latitude
                float(cols[5]),     # longitude
                int(cols[14]) if cols[14] else 0  # population
            ))
            
    cursor.executemany("""
        INSERT INTO cities (id, name, ascii_name, admin1, country, lat, lon, population)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    
    # Create indexes for blazing fast text lookups
    cursor.execute("CREATE INDEX idx_name ON cities(name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_ascii ON cities(ascii_name COLLATE NOCASE)")
    
    conn.commit()
    conn.close()
    
    os.remove(ZIP_PATH)
    os.remove(TXT_PATH)
    print(f"Success! {DB_PATH} is ready.")

if __name__ == "__main__":
    build_offline_atlas()
