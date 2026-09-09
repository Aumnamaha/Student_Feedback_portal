-- ============================================================
-- Student Feedback Management System — MySQL Schema
-- Matches the "Database Schema (MySQL)" section of PROJECT.md
-- ============================================================

CREATE DATABASE IF NOT EXISTS student_feedback
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE student_feedback;

-- -----------------------------------------------------------
-- users
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100)  NOT NULL,
    email         VARCHAR(100)  NOT NULL UNIQUE,
    roll_number   VARCHAR(50)   NULL  UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    role          ENUM('student', 'admin')
                  NOT NULL DEFAULT 'student',
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------
-- feedback
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    student_id    INT           NOT NULL,
    category      ENUM('Food', 'Faculty', 'Infrastructure',
                       'Events', 'Other')
                  NOT NULL,
    rating        TINYINT       NOT NULL  CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT          NOT NULL,
    is_anonymous  BOOLEAN       NOT NULL DEFAULT FALSE,
    status        ENUM('Pending', 'In Progress', 'Resolved')
                  NOT NULL DEFAULT 'Pending',
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_feedback_student
        FOREIGN KEY (student_id) REFERENCES users (id)
);
