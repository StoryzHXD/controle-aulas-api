BEGIN;


-- =========================================================
-- 1. VERIFICAR E-MAILS DUPLICADOS
-- =========================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM users
        GROUP BY LOWER(email)
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Existem e-mails duplicados. Resolva-os antes da migração.';
    END IF;
END
$$;


-- =========================================================
-- 2. VERIFICAR MAIS DE UM ADMINISTRADOR POR ESCOLA
-- =========================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM users
        WHERE role = 'ADMIN'
        GROUP BY school_id
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Existe uma escola com mais de um administrador.';
    END IF;
END
$$;


-- =========================================================
-- 3. VERIFICAR ESCOLAS SEM ADMINISTRADOR
-- =========================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM schools AS school
        WHERE (
            EXISTS (
                SELECT 1
                FROM users
                WHERE users.school_id = school.id
            )
            OR EXISTS (
                SELECT 1
                FROM rooms
                WHERE rooms.school_id = school.id
            )
            OR EXISTS (
                SELECT 1
                FROM schedules
                WHERE schedules.school_id = school.id
            )
            OR EXISTS (
                SELECT 1
                FROM notifications
                WHERE notifications.school_id = school.id
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM users
            WHERE users.school_id = school.id
              AND users.role = 'ADMIN'
        )
    ) THEN
        RAISE EXCEPTION
            'Existe uma escola com dados, mas sem administrador.';
    END IF;
END
$$;


-- =========================================================
-- 4. ADICIONAR FATHER_ID
-- =========================================================

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS father_id INTEGER;

ALTER TABLE rooms
    ADD COLUMN IF NOT EXISTS father_id INTEGER;

ALTER TABLE schedules
    ADD COLUMN IF NOT EXISTS father_id INTEGER;

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS father_id INTEGER;


-- =========================================================
-- 5. ASSOCIAR PROFESSORES AOS ADMINISTRADORES
-- =========================================================

UPDATE users AS child
SET father_id = administrator.id
FROM users AS administrator
WHERE child.school_id = administrator.school_id
  AND administrator.role = 'ADMIN'
  AND child.role <> 'ADMIN'
  AND child.father_id IS NULL;


-- Administradores principais não possuem pai.
UPDATE users
SET father_id = NULL
WHERE role = 'ADMIN';


-- =========================================================
-- 6. ASSOCIAR SALAS AOS ADMINISTRADORES
-- =========================================================

UPDATE rooms AS room
SET father_id = administrator.id
FROM users AS administrator
WHERE room.school_id = administrator.school_id
  AND administrator.role = 'ADMIN'
  AND room.father_id IS NULL;


-- =========================================================
-- 7. ASSOCIAR AGENDAMENTOS AOS ADMINISTRADORES
-- =========================================================

UPDATE schedules AS schedule
SET father_id = room.father_id
FROM rooms AS room
WHERE schedule.room_id = room.id
  AND schedule.father_id IS NULL;


-- =========================================================
-- 8. ASSOCIAR NOTIFICAÇÕES AOS ADMINISTRADORES
-- =========================================================

UPDATE notifications AS notification
SET father_id = CASE
    WHEN recipient.role = 'ADMIN'
        THEN recipient.id
    ELSE recipient.father_id
END
FROM users AS recipient
WHERE notification.user_id = recipient.id
  AND notification.father_id IS NULL;


-- =========================================================
-- 9. VALIDAR A MIGRAÇÃO DOS DADOS
-- =========================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM users
        WHERE role <> 'ADMIN'
          AND father_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Existe um usuário secundário sem father_id.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM rooms
        WHERE father_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Existe uma sala sem father_id.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM schedules
        WHERE father_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Existe um agendamento sem father_id.';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM notifications
        WHERE father_id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Existe uma notificação sem father_id.';
    END IF;
END
$$;


-- =========================================================
-- 10. CRIAR CHAVES ESTRANGEIRAS DE FATHER_ID
-- =========================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_users_father_id'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_father_id
            FOREIGN KEY (father_id)
            REFERENCES users(id)
            ON DELETE CASCADE;
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_rooms_father_id'
    ) THEN
        ALTER TABLE rooms
            ADD CONSTRAINT fk_rooms_father_id
            FOREIGN KEY (father_id)
            REFERENCES users(id)
            ON DELETE CASCADE;
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_schedules_father_id'
    ) THEN
        ALTER TABLE schedules
            ADD CONSTRAINT fk_schedules_father_id
            FOREIGN KEY (father_id)
            REFERENCES users(id)
            ON DELETE CASCADE;
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_notifications_father_id'
    ) THEN
        ALTER TABLE notifications
            ADD CONSTRAINT fk_notifications_father_id
            FOREIGN KEY (father_id)
            REFERENCES users(id)
            ON DELETE CASCADE;
    END IF;
END
$$;


-- =========================================================
-- 11. TORNAR FATHER_ID OBRIGATÓRIO NOS RECURSOS
-- =========================================================

-- Em users permanece NULL para o administrador principal.
ALTER TABLE rooms
    ALTER COLUMN father_id SET NOT NULL;

ALTER TABLE schedules
    ALTER COLUMN father_id SET NOT NULL;

ALTER TABLE notifications
    ALTER COLUMN father_id SET NOT NULL;


-- =========================================================
-- 12. REMOVER RESTRIÇÕES DA ARQUITETURA SCHOOL_ID
-- =========================================================

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS uq_users_school_email;

ALTER TABLE rooms
    DROP CONSTRAINT IF EXISTS uq_rooms_school_name;

ALTER TABLE schedules
    DROP CONSTRAINT IF EXISTS
        uq_schedules_school_room_date_lesson;


-- Remove possíveis nomes de chaves estrangeiras.
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_school_id_fkey;

ALTER TABLE users
    DROP CONSTRAINT IF EXISTS fk_users_school_id;

ALTER TABLE rooms
    DROP CONSTRAINT IF EXISTS rooms_school_id_fkey;

ALTER TABLE rooms
    DROP CONSTRAINT IF EXISTS fk_rooms_school_id;

ALTER TABLE schedules
    DROP CONSTRAINT IF EXISTS schedules_school_id_fkey;

ALTER TABLE schedules
    DROP CONSTRAINT IF EXISTS fk_schedules_school_id;

ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_school_id_fkey;

ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS fk_notifications_school_id;


-- =========================================================
-- 13. REMOVER SCHOOL_ID
-- =========================================================

ALTER TABLE notifications
    DROP COLUMN IF EXISTS school_id;

ALTER TABLE schedules
    DROP COLUMN IF EXISTS school_id;

ALTER TABLE rooms
    DROP COLUMN IF EXISTS school_id;

ALTER TABLE users
    DROP COLUMN IF EXISTS school_id;


-- =========================================================
-- 14. REMOVER TABELA SCHOOLS
-- =========================================================

DROP TABLE IF EXISTS schools;


-- =========================================================
-- 15. E-MAIL GLOBALMENTE ÚNICO
-- =========================================================

-- Normaliza os e-mails existentes.
UPDATE users
SET email = LOWER(TRIM(email));


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_email_key'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_email_key
            UNIQUE (email);
    END IF;
END
$$;


-- Também impede duplicação mudando apenas letras maiúsculas.
CREATE UNIQUE INDEX IF NOT EXISTS
    uq_users_email_lower
ON users (LOWER(email));


-- =========================================================
-- 16. RESTRIÇÕES POR ADMINISTRADOR
-- =========================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_rooms_father_name'
    ) THEN
        ALTER TABLE rooms
            ADD CONSTRAINT uq_rooms_father_name
            UNIQUE (
                father_id,
                name
            );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'uq_schedules_father_room_date_lesson'
    ) THEN
        ALTER TABLE schedules
            ADD CONSTRAINT
                uq_schedules_father_room_date_lesson
            UNIQUE (
                father_id,
                room_id,
                class_date,
                lesson_number
            );
    END IF;
END
$$;


-- =========================================================
-- 17. CRIAR ÍNDICES
-- =========================================================

CREATE INDEX IF NOT EXISTS ix_users_father_id
    ON users (father_id);

CREATE INDEX IF NOT EXISTS ix_rooms_father_id
    ON rooms (father_id);

CREATE INDEX IF NOT EXISTS ix_schedules_father_id
    ON schedules (father_id);

CREATE INDEX IF NOT EXISTS ix_notifications_father_id
    ON notifications (father_id);


COMMIT;