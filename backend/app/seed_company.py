"""Generate the bundled Company sample database: a fictional IT company's HR data.

Employees, departments, monthly payroll, projects, leaves and performance reviews.
Random but deterministic (fixed seed). All names and figures are fictional.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE departments (
    department_id     INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    location          TEXT NOT NULL,             -- office city
    annual_budget     REAL NOT NULL,             -- INR
    head_employee_id  INTEGER REFERENCES employees(employee_id)
);

CREATE TABLE employees (
    employee_id    INTEGER PRIMARY KEY,
    emp_code       TEXT NOT NULL UNIQUE,         -- e.g. 'NT0042'
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    gender         TEXT NOT NULL CHECK (gender IN ('Male', 'Female')),
    email          TEXT NOT NULL UNIQUE,
    department_id  INTEGER NOT NULL REFERENCES departments(department_id),
    job_title      TEXT NOT NULL,
    level          TEXT NOT NULL CHECK (level IN ('L1', 'L2', 'L3', 'L4', 'L5')),  -- L1 junior .. L5 head
    manager_id     INTEGER REFERENCES employees(employee_id),
    hire_date      DATE NOT NULL,
    exit_date      DATE,                         -- NULL while the employee is still working here
    status         TEXT NOT NULL CHECK (status IN ('Active', 'Resigned', 'Terminated')),
    work_mode      TEXT NOT NULL CHECK (work_mode IN ('Office', 'Hybrid', 'Remote')),
    annual_salary  REAL NOT NULL                 -- current CTC in INR per year
);

CREATE TABLE payroll (
    payroll_id   INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL REFERENCES employees(employee_id),
    month        TEXT NOT NULL,                  -- 'YYYY-MM'
    gross_pay    REAL NOT NULL,                  -- INR, before deductions, excluding bonus
    bonus        REAL NOT NULL DEFAULT 0,        -- INR, paid in March (annual bonus)
    deductions   REAL NOT NULL,                  -- INR: provident fund + income tax
    net_pay      REAL NOT NULL,                  -- gross_pay + bonus - deductions
    UNIQUE (employee_id, month)
);

CREATE TABLE projects (
    project_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    client         TEXT NOT NULL,
    department_id  INTEGER NOT NULL REFERENCES departments(department_id),
    start_date     DATE NOT NULL,
    end_date       DATE,                         -- NULL if not finished
    budget         REAL NOT NULL,                -- INR
    status         TEXT NOT NULL CHECK (status IN ('Planned', 'Active', 'Completed', 'On Hold'))
);

CREATE TABLE project_assignments (
    assignment_id       INTEGER PRIMARY KEY,
    project_id          INTEGER NOT NULL REFERENCES projects(project_id),
    employee_id         INTEGER NOT NULL REFERENCES employees(employee_id),
    role                TEXT NOT NULL,
    allocation_percent  INTEGER NOT NULL,        -- share of the employee's time, 10-100
    UNIQUE (project_id, employee_id)
);

CREATE TABLE leaves (
    leave_id     INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL REFERENCES employees(employee_id),
    leave_type   TEXT NOT NULL CHECK (leave_type IN ('Casual', 'Sick', 'Earned', 'Maternity', 'Paternity', 'Unpaid')),
    start_date   DATE NOT NULL,
    end_date     DATE NOT NULL,
    days         INTEGER NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('Approved', 'Pending', 'Rejected'))
);

CREATE TABLE performance_reviews (
    review_id    INTEGER PRIMARY KEY,
    employee_id  INTEGER NOT NULL REFERENCES employees(employee_id),
    review_year  INTEGER NOT NULL,
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),  -- 5 = outstanding
    reviewer_id  INTEGER REFERENCES employees(employee_id),
    UNIQUE (employee_id, review_year)
);

CREATE INDEX idx_emp_dept ON employees(department_id);
CREATE INDEX idx_payroll_emp ON payroll(employee_id);
CREATE INDEX idx_payroll_month ON payroll(month);
CREATE INDEX idx_leaves_emp ON leaves(employee_id);
"""

# name, office, share of headcount, pay multiplier, titles for L1..L5
DEPARTMENTS = [
    ("Engineering", "Bengaluru", 34, 1.15, ["Software Engineer", "Senior Software Engineer", "Tech Lead",
                                            "Engineering Manager", "VP Engineering"]),
    ("Product", "Bengaluru", 8, 1.20, ["Associate Product Manager", "Product Manager", "Senior Product Manager",
                                       "Group Product Manager", "VP Product"]),
    ("Sales", "Mumbai", 15, 1.00, ["Sales Executive", "Account Executive", "Senior Account Manager",
                                   "Regional Sales Manager", "VP Sales"]),
    ("Marketing", "Mumbai", 8, 0.95, ["Marketing Associate", "Marketing Specialist", "Senior Marketing Manager",
                                      "Marketing Lead", "Head of Marketing"]),
    ("Customer Support", "Hyderabad", 14, 0.80, ["Support Associate", "Support Specialist", "Support Team Lead",
                                                 "Support Manager", "Head of Customer Support"]),
    ("Finance", "Pune", 6, 1.05, ["Accounts Executive", "Financial Analyst", "Senior Financial Analyst",
                                  "Finance Manager", "Chief Financial Officer"]),
    ("Human Resources", "Pune", 5, 0.90, ["HR Associate", "HR Generalist", "HR Business Partner",
                                          "HR Manager", "Head of HR"]),
    ("Operations", "Delhi", 10, 0.90, ["Operations Associate", "Operations Analyst", "Operations Lead",
                                       "Operations Manager", "Head of Operations"]),
]
LEVELS = ["L1", "L2", "L3", "L4", "L5"]
SALARY_BAND = {"L1": (400_000, 700_000), "L2": (700_000, 1_200_000), "L3": (1_200_000, 2_000_000),
               "L4": (2_000_000, 3_500_000), "L5": (3_800_000, 6_500_000)}

BOYS = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Rohan", "Rahul", "Amit", "Vikram", "Karan", "Siddharth",
        "Deepak", "Manish", "Harsh", "Yash", "Kabir", "Nikhil", "Varun", "Gaurav", "Ankit", "Suresh", "Rajesh"]
GIRLS = ["Ananya", "Diya", "Saanvi", "Anika", "Navya", "Kavya", "Priya", "Neha", "Pooja", "Sneha", "Meera",
         "Riya", "Nisha", "Tanvi", "Isha", "Shreya", "Divya", "Swati", "Pallavi", "Aishwarya", "Lakshmi", "Fatima"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Singh", "Kumar", "Mehta", "Joshi",
              "Chopra", "Rao", "Das", "Banerjee", "Kapoor", "Agarwal", "Pillai", "Khan", "Swami", "Menon", "Desai"]
CLIENTS = ["Acme Retail", "BluePeak Bank", "Sunrise Health", "Zenith Motors", "Orbit Telecom", "GreenLeaf Foods",
           "Skyline Realty", "Nova Insurance", "Metro Logistics", "Lotus Pharma", "Indigo Airways", "Everest Energy"]
PROJECT_WORDS = ["Mobile App", "Data Platform", "CRM Migration", "Payments Gateway", "Analytics Dashboard",
                 "Cloud Migration", "Customer Portal", "Chatbot", "Inventory System", "Website Revamp"]

TODAY = date(2026, 10, 31)
COMPANY_START = date(2016, 4, 1)


def _month_range(start: date, end: date) -> list[str]:
    months, d = [], date(start.year, start.month, 1)
    while d <= end:
        months.append(f"{d.year}-{d.month:02d}")
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return months


def build(path: Path, seed: int = 11) -> None:
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        for i, (name, city, *_rest) in enumerate(DEPARTMENTS, start=1):
            conn.execute("INSERT INTO departments (department_id, name, location, annual_budget) VALUES (?, ?, ?, ?)",
                         (i, name, city, float(rng.randrange(20, 120) * 1_000_000)))

        total = 320
        employees = []  # dicts
        used_emails: set[str] = set()
        eid = 0
        for d_index, (_name, _city, share, mult, titles) in enumerate(DEPARTMENTS, start=1):
            count = max(6, round(total * share / 100))
            # level mix: one head (L5), a few L4 managers, pyramid below
            levels = ["L5"] + ["L4"] * max(1, count // 12) + ["L3"] * (count // 5)
            levels += ["L2"] * (count // 3)
            levels += ["L1"] * (count - len(levels))
            for level in levels:
                eid += 1
                gender = "Female" if rng.random() < 0.38 else "Male"
                first = rng.choice(GIRLS if gender == "Female" else BOYS)
                last = rng.choice(LAST_NAMES)
                base = f"{first}.{last}".lower()
                email, n = base, 1
                while email in used_emails:
                    n += 1
                    email = f"{base}{n}"
                used_emails.add(email)
                seniority_years = {"L1": (0, 3), "L2": (1, 5), "L3": (2, 8), "L4": (4, 10), "L5": (5, 10)}[level]
                hire = TODAY - timedelta(days=int(rng.uniform(*seniority_years) * 365) + rng.randint(0, 200))
                hire = max(hire, COMPANY_START)
                lo, hi = SALARY_BAND[level]
                salary = round(rng.uniform(lo, hi) * mult / 1000) * 1000
                status, exit_date = "Active", None
                if level not in ("L5",) and rng.random() < 0.16:
                    status = "Resigned" if rng.random() < 0.8 else "Terminated"
                    exit_date = hire + timedelta(days=rng.randint(120, max(121, (TODAY - hire).days)))
                    exit_date = min(exit_date, TODAY - timedelta(days=5))
                    if exit_date <= hire:
                        status, exit_date = "Active", None
                work_mode = rng.choices(["Office", "Hybrid", "Remote"], weights=[35, 50, 15])[0]
                employees.append(dict(id=eid, dept=d_index, level=level, title=titles[LEVELS.index(level)],
                                      first=first, last=last, gender=gender, email=email, hire=hire,
                                      exit=exit_date, status=status, mode=work_mode, salary=float(salary)))

        # Managers: L5 heads the department; L4 report to L5; others report to an L4 (or L5) in their department.
        by_dept: dict[int, dict[str, list[dict]]] = {}
        for e in employees:
            by_dept.setdefault(e["dept"], {}).setdefault(e["level"], []).append(e)
        for e in employees:
            levels = by_dept[e["dept"]]
            if e["level"] == "L5":
                e["manager"] = None
            elif e["level"] == "L4":
                e["manager"] = levels["L5"][0]["id"]
            else:
                e["manager"] = rng.choice(levels.get("L4") or levels["L5"])["id"]

        for e in employees:
            conn.execute(
                "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e["id"], f"NT{e['id']:04d}", e["first"], e["last"], e["gender"], f"{e['email']}@nimbustech.example",
                 e["dept"], e["title"], e["level"], e["manager"], e["hire"].isoformat(),
                 e["exit"].isoformat() if e["exit"] else None, e["status"], e["mode"], e["salary"]),
            )
        for d_index, levels in by_dept.items():
            conn.execute("UPDATE departments SET head_employee_id = ? WHERE department_id = ?",
                         (levels["L5"][0]["id"], d_index))

        # Payroll: Jan 2025 - Oct 2026 for everyone employed that month.
        pid = 0
        for month in _month_range(date(2025, 1, 1), TODAY):
            y, m = map(int, month.split("-"))
            month_start = date(y, m, 1)
            for e in employees:
                if e["hire"] > month_start + timedelta(days=27):
                    continue
                if e["exit"] and e["exit"] < month_start:
                    continue
                pid += 1
                gross = round(e["salary"] / 12, 2)
                bonus = 0.0
                if m == 3 and e["hire"] < month_start - timedelta(days=180):
                    bonus = round(e["salary"] * rng.choice([0.05, 0.08, 0.10, 0.12, 0.15]), 2)
                pf = round(gross * 0.5 * 0.12, 2)
                tax_rate = 0.0 if e["salary"] <= 700_000 else 0.08 if e["salary"] <= 1_500_000 else 0.18
                deductions = round(pf + (gross + bonus) * tax_rate, 2)
                conn.execute("INSERT INTO payroll VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (pid, e["id"], month, gross, bonus, deductions, round(gross + bonus - deductions, 2)))

        # Projects and assignments
        active_staff = [e for e in employees if e["status"] == "Active"]
        assign_id = 0
        for proj_id in range(1, 29):
            dept = rng.choices([1, 2, 3, 8], weights=[60, 20, 10, 10])[0]
            start = TODAY - timedelta(days=rng.randint(30, 1400))
            status = rng.choices(["Completed", "Active", "On Hold", "Planned"], weights=[45, 35, 10, 10])[0]
            if status == "Planned":
                start = TODAY + timedelta(days=rng.randint(10, 90))
            end = start + timedelta(days=rng.randint(90, 420)) if status == "Completed" else None
            if end and end > TODAY:
                end = TODAY - timedelta(days=rng.randint(1, 30))
            conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (proj_id, f"{rng.choice(PROJECT_WORDS)} {proj_id}", rng.choice(CLIENTS), dept,
                          start.isoformat(), end.isoformat() if end else None,
                          float(rng.randrange(20, 500) * 100_000), status))
            pool = [e for e in active_staff if e["dept"] in (dept, 1, 2)] or active_staff
            for e in rng.sample(pool, k=min(len(pool), rng.randint(3, 9))):
                assign_id += 1
                role = {"L1": "Developer", "L2": "Developer", "L3": "Lead", "L4": "Project Manager",
                        "L5": "Sponsor"}[e["level"]] if e["dept"] == 1 else "Contributor"
                conn.execute("INSERT INTO project_assignments VALUES (?, ?, ?, ?, ?)",
                             (assign_id, proj_id, e["id"], role, rng.choice([20, 30, 50, 50, 70, 100])))

        # Leaves (2024 - 2026)
        leave_id = 0
        for e in employees:
            for _ in range(rng.randint(2, 9)):
                start = date(2024, 1, 1) + timedelta(days=rng.randint(0, (TODAY - date(2024, 1, 1)).days))
                if start < e["hire"] or (e["exit"] and start > e["exit"]):
                    continue
                leave_type = rng.choices(["Casual", "Sick", "Earned", "Unpaid"], weights=[40, 30, 25, 5])[0]
                days = {"Casual": rng.randint(1, 2), "Sick": rng.randint(1, 4), "Earned": rng.randint(2, 10),
                        "Unpaid": rng.randint(1, 5)}[leave_type]
                if rng.random() < 0.015:
                    leave_type = "Maternity" if e["gender"] == "Female" else "Paternity"
                    days = 182 if leave_type == "Maternity" else 10
                status = "Pending" if start > TODAY - timedelta(days=10) else rng.choices(
                    ["Approved", "Rejected"], weights=[92, 8])[0]
                leave_id += 1
                conn.execute("INSERT INTO leaves VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (leave_id, e["id"], leave_type, start.isoformat(),
                              (start + timedelta(days=days - 1)).isoformat(), days, status))

        # Performance reviews for 2023-2025 (employees who were there in December of that year)
        review_id = 0
        for year in (2023, 2024, 2025):
            for e in employees:
                if e["hire"] > date(year, 9, 30) or (e["exit"] and e["exit"] < date(year, 12, 31)):
                    continue
                review_id += 1
                rating = rng.choices([1, 2, 3, 4, 5], weights=[3, 10, 45, 32, 10])[0]
                conn.execute("INSERT INTO performance_reviews VALUES (?, ?, ?, ?, ?)",
                             (review_id, e["id"], year, rating, e["manager"]))
        conn.commit()
    finally:
        conn.close()


SAMPLE_QUESTIONS = [
    "How many active employees are in each department?",
    "What is the average salary by department and level?",
    "Who are the 10 highest paid employees?",
    "Show the total monthly payroll cost for 2026",
    "Which employees took the most sick leave in 2025?",
    "What is the attrition rate (resigned or terminated) per department?",
    "List active projects with their client and number of team members",
    "Which managers have the most direct reports?",
]
