"""Generate the bundled School sample database: students, classes, subjects, exam marks and attendance.

Random but deterministic (fixed seed), for the 2025-26 academic year (April 2025 - March 2026).
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE subjects (
    subject_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE teachers (
    teacher_id  INTEGER PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    subject_id  INTEGER NOT NULL REFERENCES subjects(subject_id),  -- subject the teacher teaches
    hire_date   DATE NOT NULL,
    salary      REAL NOT NULL                                     -- monthly salary in INR
);

CREATE TABLE classes (
    class_id          INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,   -- e.g. '10-A'
    grade             INTEGER NOT NULL,       -- 9 to 12
    section           TEXT NOT NULL,          -- 'A' or 'B'
    stream            TEXT,                   -- 'Science' or 'Commerce' for grades 11-12, NULL otherwise
    class_teacher_id  INTEGER NOT NULL REFERENCES teachers(teacher_id)
);

CREATE TABLE students (
    student_id      INTEGER PRIMARY KEY,
    roll_number     TEXT NOT NULL UNIQUE,     -- e.g. '10A-07'
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    gender          TEXT NOT NULL CHECK (gender IN ('Male', 'Female')),
    date_of_birth   DATE NOT NULL,
    class_id        INTEGER NOT NULL REFERENCES classes(class_id),
    city            TEXT NOT NULL,
    admission_date  DATE NOT NULL
);

CREATE TABLE exams (
    exam_id        INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,             -- 'Unit Test 1', 'Half Yearly', 'Unit Test 2', 'Final'
    academic_year  TEXT NOT NULL,             -- '2025-26'
    exam_date      DATE NOT NULL,
    max_marks      INTEGER NOT NULL           -- maximum marks per subject
);

CREATE TABLE marks (
    mark_id         INTEGER PRIMARY KEY,
    student_id      INTEGER NOT NULL REFERENCES students(student_id),
    exam_id         INTEGER NOT NULL REFERENCES exams(exam_id),
    subject_id      INTEGER NOT NULL REFERENCES subjects(subject_id),
    marks_obtained  INTEGER,                  -- out of exams.max_marks; NULL means the student was absent
    UNIQUE (student_id, exam_id, subject_id)
);

CREATE TABLE attendance (
    attendance_id  INTEGER PRIMARY KEY,
    student_id     INTEGER NOT NULL REFERENCES students(student_id),
    month          TEXT NOT NULL,             -- 'YYYY-MM'
    working_days   INTEGER NOT NULL,
    days_present   INTEGER NOT NULL,
    UNIQUE (student_id, month)
);

CREATE INDEX idx_marks_student ON marks(student_id);
CREATE INDEX idx_marks_exam_subject ON marks(exam_id, subject_id);
CREATE INDEX idx_students_class ON students(class_id);
CREATE INDEX idx_attendance_student ON attendance(student_id);
"""

SUBJECTS = ["Mathematics", "Science", "English", "Hindi", "Social Science", "Computer Science",
            "Physics", "Chemistry", "Biology", "Accountancy", "Business Studies", "Economics"]
SUBJECTS_BY_TRACK = {
    "junior": ["Mathematics", "Science", "English", "Hindi", "Social Science", "Computer Science"],
    "Science": ["Mathematics", "Physics", "Chemistry", "Biology", "English", "Computer Science"],
    "Commerce": ["Accountancy", "Business Studies", "Economics", "Mathematics", "English", "Computer Science"],
}
# How hard each subject is: added to a student's ability (negative = harder).
DIFFICULTY = {"Mathematics": -7, "Physics": -6, "Chemistry": -4, "Accountancy": -3, "Science": -2,
              "Economics": -1, "Biology": 0, "Business Studies": 2, "Social Science": 1,
              "Computer Science": 4, "Hindi": 3, "English": 2}

CLASSES = [(9, "A", None), (9, "B", None), (10, "A", None), (10, "B", None),
           (11, "A", "Science"), (11, "B", "Commerce"), (12, "A", "Science"), (12, "B", "Commerce")]

EXAMS = [("Unit Test 1", date(2025, 7, 14)), ("Half Yearly", date(2025, 9, 22)),
         ("Unit Test 2", date(2025, 12, 8)), ("Final", date(2026, 3, 2))]

BOYS = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
        "Rahul", "Amit", "Vikram", "Karan", "Siddharth", "Deepak", "Manish", "Harsh", "Yash", "Kabir",
        "Dev", "Ayaan", "Atharv", "Shaurya", "Pranav"]
GIRLS = ["Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Anika", "Navya", "Myra", "Kavya", "Priya",
         "Neha", "Pooja", "Sneha", "Meera", "Riya", "Nisha", "Tanvi", "Isha", "Shreya", "Zoya",
         "Aarohi", "Kiara", "Avni", "Ira", "Sara"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Singh", "Kumar", "Mehta",
              "Joshi", "Chopra", "Rao", "Das", "Banerjee", "Kapoor", "Malhotra", "Agarwal", "Pillai", "Khan",
              "Swami", "Bose", "Menon", "Desai", "Chauhan"]
CITIES = ["Jaipur"] * 6 + ["Ajmer", "Kota", "Udaipur", "Jodhpur", "Alwar", "Sikar", "Bhilwara"]

STUDENTS_PER_CLASS = 30
YEAR_START = date(2025, 4, 1)


def _months() -> list[str]:
    months, d = [], YEAR_START
    for _ in range(12):
        months.append(f"{d.year}-{d.month:02d}")
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return months


# Working days per month (summer break in May-June, Diwali break in October).
WORKING_DAYS = dict(zip(_months(), [22, 6, 12, 25, 24, 23, 18, 22, 21, 23, 22, 20]))


def build(path: Path, seed: int = 7) -> None:
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        subject_ids = {}
        for i, name in enumerate(SUBJECTS, start=1):
            conn.execute("INSERT INTO subjects VALUES (?, ?)", (i, name))
            subject_ids[name] = i

        # Teachers: one or two per subject.
        teachers_by_subject: dict[str, list[int]] = {}
        tid = 0
        used_emails: set[str] = set()
        for name in SUBJECTS:
            for _ in range(2 if name in ("Mathematics", "English", "Computer Science") else 1):
                tid += 1
                gender_names = rng.choice([BOYS, GIRLS])
                first, last = rng.choice(gender_names), rng.choice(LAST_NAMES)
                email = f"{first}.{last}".lower()
                n = 1
                while email in used_emails:
                    n += 1
                    email = f"{first}.{last}{n}".lower()
                used_emails.add(email)
                hire = YEAR_START - timedelta(days=rng.randint(200, 5000))
                conn.execute("INSERT INTO teachers VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (tid, first, last, f"{email}@school.example", subject_ids[name],
                              hire.isoformat(), float(rng.randrange(38_000, 95_000, 500))))
                teachers_by_subject.setdefault(name, []).append(tid)
        all_teachers = list(range(1, tid + 1))

        # Classes
        class_rows = []
        class_teachers = rng.sample(all_teachers, len(CLASSES))
        for cid, ((grade, section, stream), teacher) in enumerate(zip(CLASSES, class_teachers), start=1):
            conn.execute("INSERT INTO classes VALUES (?, ?, ?, ?, ?, ?)",
                         (cid, f"{grade}-{section}", grade, section, stream, teacher))
            class_rows.append((cid, grade, section, stream))

        # Exams
        for eid, (name, day) in enumerate(EXAMS, start=1):
            conn.execute("INSERT INTO exams VALUES (?, ?, ?, ?, ?)", (eid, name, "2025-26", day.isoformat(), 100))

        # Students, marks, attendance
        sid = mark_id = att_id = 0
        months = _months()
        for cid, grade, section, stream in class_rows:
            track = stream or "junior"
            # Section A classes do a little better on average.
            class_shift = 2.5 if section == "A" else -1.5
            for roll in range(1, STUDENTS_PER_CLASS + 1):
                sid += 1
                gender = "Female" if rng.random() < 0.48 else "Male"
                first = rng.choice(GIRLS if gender == "Female" else BOYS)
                last = rng.choice(LAST_NAMES)
                dob = date(2025 - grade - 6, 1, 1) + timedelta(days=rng.randint(-120, 300))
                admitted = date(rng.randint(2014, 2025), 4, 1) if grade <= 10 else date(2024 + (grade == 11), 4, 1)
                conn.execute("INSERT INTO students VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (sid, f"{grade}{section}-{roll:02d}", first, last, gender, dob.isoformat(),
                              cid, rng.choice(CITIES), admitted.isoformat()))

                ability = rng.gauss(66, 13) + class_shift
                # Drives attendance (and attendance nudges marks); about 1 in 10 students attend poorly.
                diligence = rng.uniform(0.60, 0.78) if rng.random() < 0.1 else rng.uniform(0.80, 0.99)
                trend = rng.gauss(0, 2.5)            # some students improve over the year, some slip
                for e_index, _exam in enumerate(EXAMS):
                    exam_id = e_index + 1
                    for subject in SUBJECTS_BY_TRACK[track]:
                        mark_id += 1
                        if rng.random() < 0.012:
                            score = None  # absent
                        else:
                            raw = (ability + DIFFICULTY[subject] + trend * e_index
                                   + (diligence - 0.9) * 40 + rng.gauss(0, 7))
                            score = int(max(4, min(100, round(raw))))
                        conn.execute("INSERT INTO marks VALUES (?, ?, ?, ?, ?)",
                                     (mark_id, sid, exam_id, subject_ids[subject], score))

                for month in months:
                    att_id += 1
                    working = WORKING_DAYS[month]
                    present = sum(1 for _ in range(working) if rng.random() < diligence)
                    conn.execute("INSERT INTO attendance VALUES (?, ?, ?, ?, ?)",
                                 (att_id, sid, month, working, present))
        conn.commit()
    finally:
        conn.close()


SAMPLE_QUESTIONS = [
    "Find the average marks of students in each subject",
    "Who are the top 10 students by overall percentage in the Final exam?",
    "Which class has the highest average in Mathematics?",
    "List students who scored below 33 in any subject in the Final exam",
    "Which students have attendance below 75% for the year?",
    "Compare the average marks of boys and girls in each subject",
    "How did the average marks change from Unit Test 1 to the Final exam?",
    "Who is the class teacher of each class?",
]
