-- Create database if not exists
SELECT 'CREATE DATABASE magic_frame_bot'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'magic_frame_bot')\gexec

-- Create user if not exists and grant privileges
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles
        WHERE rolname = 'magic_frame') THEN
        
        CREATE ROLE magic_frame LOGIN PASSWORD 'RagnarLothbrok2021!';
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE magic_frame_bot TO magic_frame;

-- Switch to the magic_frame_bot database
\c magic_frame_bot

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO magic_frame;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO magic_frame;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO magic_frame;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO magic_frame;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO magic_frame;
