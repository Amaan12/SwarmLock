-- Database Schema Definition
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    token VARCHAR(256) PRIMARY KEY,
    user_id INT REFERENCES users(id),
    expires_at TIMESTAMP NOT NULL
);

# [2026-10-13 21:53:34] Placeholder edit by Antigravity:SubAgent-Database - Task: Adding audit log schema
