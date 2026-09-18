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
-- faculty
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS faculty (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100)  NOT NULL,
    email          VARCHAR(100)  NOT NULL UNIQUE,
    faculty_id     VARCHAR(50)   NOT NULL UNIQUE,
    department     VARCHAR(100)  NOT NULL,
    subject_taught VARCHAR(200)  NOT NULL,
    password_hash  VARCHAR(255)  NOT NULL,
    role           ENUM('faculty')
                  NOT NULL DEFAULT 'faculty',
    created_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------
-- feedback
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    student_id            INT           NOT NULL,
    category              ENUM('Food', 'Faculty', 'Infrastructure',
                               'Events', 'Other')
                          NOT NULL,
    rating                TINYINT       NOT NULL  CHECK (rating BETWEEN 1 AND 5),
    comment               TEXT          NOT NULL,
    is_anonymous          BOOLEAN       NOT NULL DEFAULT FALSE,
    status                ENUM('Pending', 'In Progress', 'Resolved',
                               'Pinned', 'Verified/Closed', 'Verification Failed')
                          NOT NULL DEFAULT 'Pending',
    department            VARCHAR(100)  NULL,
    subject               VARCHAR(200)  NULL,
    semester_year         VARCHAR(20)   NULL,
    resolved_by_faculty_id INT          NULL,
    review_deadline       TIMESTAMP     NULL,
    escalation_deadline   TIMESTAMP     NULL,
    failed_verification_count TINYINT  NOT NULL DEFAULT 0,
    created_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_feedback_student
        FOREIGN KEY (student_id) REFERENCES users (id),

    CONSTRAINT fk_feedback_faculty
        FOREIGN KEY (resolved_by_faculty_id) REFERENCES faculty (id)
);

-- -----------------------------------------------------------
-- comment (threaded comments on feedback items)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS comment (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    feedback_id   INT           NOT NULL,
    parent_id     INT           NULL,
    author_type   ENUM('faculty', 'student')
                  NOT NULL,
    author_id     INT           NOT NULL,
    text          TEXT          NOT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_comment_feedback
        FOREIGN KEY (feedback_id) REFERENCES feedback (id),

    CONSTRAINT fk_comment_parent
        FOREIGN KEY (parent_id) REFERENCES comment (id)
);

