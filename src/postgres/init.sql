CREATE TABLE IF NOT EXISTS licenses (
    user_id TEXT NOT NULL,
    feature TEXT NOT NULL,
    PRIMARY KEY (user_id, feature)
);

CREATE TABLE IF NOT EXISTS features (
    name TEXT PRIMARY KEY,
    description TEXT
);

INSERT INTO features (name, description) VALUES
    ('dashboard', 'Advanced dashboard access'),
    ('export', 'Data export tools')
ON CONFLICT DO NOTHING;