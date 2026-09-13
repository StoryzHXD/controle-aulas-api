BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS
        email_verified BOOLEAN,
    ADD COLUMN IF NOT EXISTS
        verification_code_hash VARCHAR(255),
    ADD COLUMN IF NOT EXISTS
        verification_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS
        verification_attempts INTEGER,
    ADD COLUMN IF NOT EXISTS
        verification_last_sent_at TIMESTAMPTZ;

-- Mantém as contas antigas funcionando.
UPDATE users
SET email_verified = TRUE
WHERE email_verified IS NULL;

UPDATE users
SET verification_attempts = 0
WHERE verification_attempts IS NULL;

ALTER TABLE users
    ALTER COLUMN email_verified
        SET DEFAULT FALSE;

ALTER TABLE users
    ALTER COLUMN email_verified
        SET NOT NULL;

ALTER TABLE users
    ALTER COLUMN verification_attempts
        SET DEFAULT 0;

ALTER TABLE users
    ALTER COLUMN verification_attempts
        SET NOT NULL;

COMMIT;