from db import get_connection


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS afc_homes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT,
    name TEXT,
    address TEXT NOT NULL,
    city TEXT,
    county TEXT,
    state TEXT DEFAULT 'MI',
    zip TEXT,
    latitude REAL,
    longitude REAL,
    address_key TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ranch_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mls TEXT,
    stat TEXT,
    property_type TEXT,
    area TEXT,
    address TEXT NOT NULL,
    city TEXT,
    county TEXT,
    price REAL,
    dom INTEGER,
    beds_total REAL,
    baths REAL,
    sqft REAL,
    latitude REAL,
    longitude REAL,
    address_key TEXT NOT NULL UNIQUE,
    first_seen TEXT DEFAULT CURRENT_DATE,
    last_seen TEXT DEFAULT CURRENT_DATE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranch_address_key TEXT NOT NULL UNIQUE,
    ranch_listing_id INTEGER NOT NULL,
    nearest_afc_id INTEGER,
    nearest_afc_address TEXT,
    distance_feet REAL,
    distance_miles REAL,
    tier TEXT,
    status TEXT DEFAULT 'Active',
    disposition TEXT DEFAULT 'New',
    notes TEXT DEFAULT '',
    first_seen TEXT DEFAULT CURRENT_DATE,
    last_seen TEXT DEFAULT CURRENT_DATE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ranch_listing_id) REFERENCES ranch_listings(id),
    FOREIGN KEY (nearest_afc_id) REFERENCES afc_homes(id)
);

CREATE TABLE IF NOT EXISTS discarded_ranches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ranch_address_key TEXT NOT NULL UNIQUE,
    ranch_listing_id INTEGER NOT NULL,
    nearest_afc_id INTEGER,
    nearest_afc_address TEXT,
    distance_feet REAL,
    distance_miles REAL,
    reason TEXT,
    first_seen TEXT DEFAULT CURRENT_DATE,
    last_seen TEXT DEFAULT CURRENT_DATE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (ranch_listing_id) REFERENCES ranch_listings(id),
    FOREIGN KEY (nearest_afc_id) REFERENCES afc_homes(id)
);

CREATE TABLE IF NOT EXISTS geocode_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mls TEXT,
    address TEXT NOT NULL,
    city TEXT,
    county TEXT,
    state TEXT DEFAULT 'MI',
    address_key TEXT NOT NULL UNIQUE,
    reason TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def main():
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print("Database initialized successfully.")


if __name__ == "__main__":
    main()
