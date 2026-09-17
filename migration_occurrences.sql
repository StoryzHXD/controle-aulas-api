BEGIN;

CREATE TABLE IF NOT EXISTS occurrences (
    id SERIAL PRIMARY KEY,

    father_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,

    student_name VARCHAR(150) NOT NULL,
    student_ra VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,

    created_at TIMESTAMPTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_occurrences_father_id
        FOREIGN KEY (father_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_occurrences_teacher_id
        FOREIGN KEY (teacher_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS
    ix_occurrences_father_id
ON occurrences (father_id);

CREATE INDEX IF NOT EXISTS
    ix_occurrences_teacher_id
ON occurrences (teacher_id);

CREATE INDEX IF NOT EXISTS
    ix_occurrences_student_ra
ON occurrences (student_ra);

CREATE INDEX IF NOT EXISTS
    ix_occurrences_created_at
ON occurrences (created_at DESC);

COMMIT;