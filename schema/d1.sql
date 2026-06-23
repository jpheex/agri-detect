CREATE TABLE IF NOT EXISTS identifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    crop TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    treatment TEXT NOT NULL,
    prevention TEXT NOT NULL,
    verified INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS training_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_path TEXT NOT NULL,
    crop TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    notes TEXT,
    treatment TEXT,
    prevention TEXT,
    image_vector TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    treatment TEXT NOT NULL,
    prevention TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'site',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(crop, issue_type, issue_name)
);

CREATE TABLE IF NOT EXISTS knowledge_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    image_vector TEXT NOT NULL,
    crop TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    issue_name TEXT NOT NULL,
    treatment TEXT NOT NULL,
    prevention TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS farm_monitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL DEFAULT '',
    crop_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    push_enabled INTEGER NOT NULL DEFAULT 1,
    last_alert_at TEXT,
    last_high_disease TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
