-- Database initialization script
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Grant schema privileges
GRANT ALL PRIVILEGES ON DATABASE attendance_db TO postgres;

