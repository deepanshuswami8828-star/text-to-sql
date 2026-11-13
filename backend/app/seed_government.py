"""Generate the bundled Government sample database: public-sector data for Indian states.

States and districts use real names. State population, literacy and sex ratio are approximate
Census-2011-style figures; everything else (district figures, scheme budgets, hospitals,
grievances) is synthetic. This is practice data, NOT official statistics.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
-- Practice data: approximate or synthetic figures, not official statistics.

CREATE TABLE states (
    state_id       INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    type           TEXT NOT NULL CHECK (type IN ('State', 'Union Territory')),
    region         TEXT NOT NULL,               -- North, South, East, West, Central, North-East
    capital        TEXT NOT NULL,
    area_sq_km     INTEGER NOT NULL,
    population     INTEGER NOT NULL,            -- approximate, Census 2011 scale
    literacy_rate  REAL NOT NULL,               -- percent
    sex_ratio      INTEGER NOT NULL             -- females per 1000 males
);

CREATE TABLE districts (
    district_id    INTEGER PRIMARY KEY,
    state_id       INTEGER NOT NULL REFERENCES states(state_id),
    name           TEXT NOT NULL,
    population     INTEGER NOT NULL,            -- synthetic
    area_sq_km     INTEGER NOT NULL,            -- synthetic
    is_aspirational INTEGER NOT NULL DEFAULT 0  -- 1 = flagged for development focus
);

CREATE TABLE schemes (
    scheme_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    ministry     TEXT NOT NULL,
    category     TEXT NOT NULL,                 -- Health, Education, Agriculture, Housing, Employment, ...
    launch_year  INTEGER NOT NULL
);

CREATE TABLE scheme_allocations (
    allocation_id    INTEGER PRIMARY KEY,
    scheme_id        INTEGER NOT NULL REFERENCES schemes(scheme_id),
    state_id         INTEGER NOT NULL REFERENCES states(state_id),
    financial_year   TEXT NOT NULL,             -- '2023-24', '2024-25', '2025-26'
    allocated_crore  REAL NOT NULL,             -- INR crore (1 crore = 10 million)
    spent_crore      REAL NOT NULL,             -- INR crore
    beneficiaries    INTEGER NOT NULL,
    UNIQUE (scheme_id, state_id, financial_year)
);

CREATE TABLE hospitals (
    hospital_id      INTEGER PRIMARY KEY,
    district_id      INTEGER NOT NULL REFERENCES districts(district_id),
    name             TEXT NOT NULL,
    type             TEXT NOT NULL CHECK (type IN ('Primary Health Centre', 'Community Health Centre',
                                                   'District Hospital', 'Medical College')),
    beds             INTEGER NOT NULL,
    doctors          INTEGER NOT NULL,
    established_year INTEGER NOT NULL
);

CREATE TABLE grievances (
    grievance_id   INTEGER PRIMARY KEY,
    district_id    INTEGER NOT NULL REFERENCES districts(district_id),
    department     TEXT NOT NULL,               -- Water Supply, Electricity, Roads, Health, ...
    channel        TEXT NOT NULL CHECK (channel IN ('Online Portal', 'Helpline', 'Mobile App', 'In Person')),
    filed_date     DATE NOT NULL,
    resolved_date  DATE,                        -- NULL until resolved
    status         TEXT NOT NULL CHECK (status IN ('Resolved', 'In Progress', 'Pending', 'Rejected'))
);

CREATE INDEX idx_districts_state ON districts(state_id);
CREATE INDEX idx_alloc_state ON scheme_allocations(state_id);
CREATE INDEX idx_hospitals_district ON hospitals(district_id);
CREATE INDEX idx_grievances_district ON grievances(district_id);
CREATE INDEX idx_grievances_filed ON grievances(filed_date);
"""

# name, type, region, capital, area km2, population, literacy %, sex ratio, sample districts
STATES = [
    ("Uttar Pradesh", "State", "North", "Lucknow", 240928, 199812341, 67.7, 912,
     ["Lucknow", "Kanpur Nagar", "Varanasi", "Agra", "Prayagraj", "Gorakhpur"]),
    ("Maharashtra", "State", "West", "Mumbai", 307713, 112374333, 82.3, 929,
     ["Mumbai Suburban", "Pune", "Nagpur", "Nashik", "Thane"]),
    ("Bihar", "State", "East", "Patna", 94163, 104099452, 61.8, 918,
     ["Patna", "Gaya", "Muzaffarpur", "Bhagalpur", "Darbhanga"]),
    ("West Bengal", "State", "East", "Kolkata", 88752, 91276115, 76.3, 950,
     ["Kolkata", "Howrah", "Darjeeling", "Nadia", "Purba Medinipur"]),
    ("Madhya Pradesh", "State", "Central", "Bhopal", 308252, 72626809, 69.3, 931,
     ["Bhopal", "Indore", "Jabalpur", "Gwalior", "Ujjain"]),
    ("Tamil Nadu", "State", "South", "Chennai", 130060, 72147030, 80.1, 996,
     ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem"]),
    ("Rajasthan", "State", "North", "Jaipur", 342239, 68548437, 66.1, 928,
     ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Bikaner"]),
    ("Karnataka", "State", "South", "Bengaluru", 191791, 61095297, 75.4, 973,
     ["Bengaluru Urban", "Mysuru", "Belagavi", "Dharwad", "Dakshina Kannada"]),
    ("Gujarat", "State", "West", "Gandhinagar", 196024, 60439692, 78.0, 919,
     ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Kutch"]),
    ("Andhra Pradesh", "State", "South", "Amaravati", 162968, 49577103, 67.0, 993,
     ["Visakhapatnam", "Guntur", "Krishna", "Chittoor", "Kurnool"]),
    ("Odisha", "State", "East", "Bhubaneswar", 155707, 41974218, 72.9, 979,
     ["Khordha", "Cuttack", "Ganjam", "Sambalpur", "Mayurbhanj"]),
    ("Telangana", "State", "South", "Hyderabad", 112077, 35003674, 66.5, 988,
     ["Hyderabad", "Rangareddy", "Warangal", "Karimnagar", "Nizamabad"]),
    ("Kerala", "State", "South", "Thiruvananthapuram", 38863, 33406061, 94.0, 1084,
     ["Thiruvananthapuram", "Ernakulam", "Kozhikode", "Thrissur", "Kollam"]),
    ("Assam", "State", "North-East", "Dispur", 78438, 31205576, 72.2, 958,
     ["Kamrup Metropolitan", "Dibrugarh", "Cachar", "Nagaon", "Jorhat"]),
    ("Punjab", "State", "North", "Chandigarh", 50362, 27743338, 75.8, 895,
     ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda"]),
    ("Delhi", "Union Territory", "North", "New Delhi", 1484, 16787941, 86.2, 868,
     ["New Delhi", "South Delhi", "North West Delhi", "East Delhi", "Central Delhi"]),
]

SCHEMES = [
    ("Rural Housing Mission", "Ministry of Rural Development", "Housing", 2016),
    ("Farmer Income Support", "Ministry of Agriculture and Farmers Welfare", "Agriculture", 2019),
    ("Universal Health Insurance", "Ministry of Health and Family Welfare", "Health", 2018),
    ("Rural Employment Guarantee", "Ministry of Rural Development", "Employment", 2006),
    ("Clean Drinking Water Mission", "Ministry of Jal Shakti", "Water and Sanitation", 2019),
    ("School Meal Programme", "Ministry of Education", "Education", 1995),
    ("Girl Child Scholarship", "Ministry of Women and Child Development", "Education", 2015),
    ("Clean Cooking Gas Connections", "Ministry of Petroleum and Natural Gas", "Social Welfare", 2016),
    ("Old Age Pension", "Ministry of Rural Development", "Social Welfare", 1995),
    ("Youth Skill Development", "Ministry of Skill Development and Entrepreneurship", "Employment", 2015),
    ("Rural Roads Programme", "Ministry of Rural Development", "Infrastructure", 2000),
    ("Maternal Health Support", "Ministry of Health and Family Welfare", "Health", 2005),
]
FINANCIAL_YEARS = ["2023-24", "2024-25", "2025-26"]

DEPARTMENTS = ["Water Supply", "Electricity", "Roads", "Health", "Education", "Police", "Revenue",
               "Sanitation", "Public Transport", "Pension"]
DEPT_WEIGHTS = [16, 15, 14, 9, 8, 9, 10, 10, 5, 4]
CHANNELS = ["Online Portal", "Helpline", "Mobile App", "In Person"]
HOSPITAL_TYPES = [("Primary Health Centre", (6, 30), (1, 4)), ("Community Health Centre", (30, 60), (4, 10)),
                  ("District Hospital", (150, 500), (20, 80)), ("Medical College", (500, 1800), (80, 350))]

TODAY = date(2026, 10, 31)


def build(path: Path, seed: int = 23) -> None:
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)

        district_rows = []  # (district_id, state_literacy, aspirational)
        did = 0
        for sid, (name, kind, region, capital, area, pop, lit, ratio, districts) in enumerate(STATES, start=1):
            conn.execute("INSERT INTO states VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (sid, name, kind, region, capital, area, pop, lit, ratio))
            for dname in districts:
                did += 1
                d_pop = int(pop * rng.uniform(0.025, 0.08))
                d_area = int(area * rng.uniform(0.015, 0.06))
                aspirational = 1 if lit < 72 and rng.random() < 0.35 else 0
                conn.execute("INSERT INTO districts VALUES (?, ?, ?, ?, ?, ?)",
                             (did, sid, dname, d_pop, max(d_area, 120), aspirational))
                district_rows.append((did, sid, lit, aspirational, d_pop))

        for i, (name, ministry, category, year) in enumerate(SCHEMES, start=1):
            conn.execute("INSERT INTO schemes VALUES (?, ?, ?, ?, ?)", (i, name, ministry, category, year))

        alloc_id = 0
        for scheme_id, (_name, _ministry, category, _year) in enumerate(SCHEMES, start=1):
            per_crore_people = rng.uniform(4, 40)  # crore allocated per crore population
            for sid, state in enumerate(STATES, start=1):
                pop = state[5]
                rural_need = 1.25 if state[6] < 72 else 0.9  # lower literacy -> larger welfare budgets
                growth = 1.0
                for fy in FINANCIAL_YEARS:
                    alloc_id += 1
                    allocated = round(pop / 1e7 * per_crore_people * rural_need * growth * rng.uniform(0.85, 1.15), 2)
                    utilisation = rng.uniform(0.55, 0.98) if fy != "2025-26" else rng.uniform(0.35, 0.75)
                    spent = round(allocated * utilisation, 2)
                    beneficiaries = int(pop * rng.uniform(0.002, 0.03) * (1.2 if category == "Social Welfare" else 1))
                    conn.execute("INSERT INTO scheme_allocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (alloc_id, scheme_id, sid, fy, allocated, spent, beneficiaries))
                    growth *= rng.uniform(1.03, 1.12)

        hid = 0
        for did, _sid, lit, _asp, d_pop in district_rows:
            dname = conn.execute("SELECT name FROM districts WHERE district_id = ?", (did,)).fetchone()[0]
            counts = {"Primary Health Centre": rng.randint(3, 7), "Community Health Centre": rng.randint(1, 3),
                      "District Hospital": 1, "Medical College": 1 if (lit > 75 or d_pop > 3_000_000) else 0}
            for htype, beds_range, doctors_range in HOSPITAL_TYPES:
                for n in range(1, counts[htype] + 1):
                    hid += 1
                    label = f"{htype}, {dname}" + (f" {n}" if counts[htype] > 1 else "")
                    conn.execute("INSERT INTO hospitals VALUES (?, ?, ?, ?, ?, ?, ?)",
                                 (hid, did, label, htype, rng.randint(*beds_range), rng.randint(*doctors_range),
                                  rng.randint(1955, 2022)))

        # Grievances Jan 2024 - Oct 2026; better-run districts resolve faster.
        gid = 0
        start = date(2024, 1, 1)
        span = (TODAY - start).days
        weights = [row[4] for row in district_rows]
        for _ in range(4500):
            did, _sid, lit, asp, _pop = rng.choices(district_rows, weights=weights)[0]
            filed = start + timedelta(days=rng.randint(0, span))
            dept = rng.choices(DEPARTMENTS, weights=DEPT_WEIGHTS)[0]
            channel = rng.choices(CHANNELS, weights=[40, 25, 25, 10])[0]
            speed = 1.0 + (0.6 if asp else 0) + (0.3 if lit < 70 else 0)
            days_to_resolve = int(rng.expovariate(1 / (14 * speed))) + 1
            resolved = filed + timedelta(days=days_to_resolve)
            if rng.random() < 0.06:
                status, resolved_date = "Rejected", filed + timedelta(days=rng.randint(2, 20))
            elif resolved <= TODAY:
                status, resolved_date = "Resolved", resolved
            else:
                status, resolved_date = rng.choice(["Pending", "In Progress"]), None
            if resolved_date and resolved_date > TODAY:
                resolved_date = TODAY
            gid += 1
            conn.execute("INSERT INTO grievances VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (gid, did, dept, channel, filed.isoformat(),
                          resolved_date.isoformat() if resolved_date else None, status))
        conn.commit()
    finally:
        conn.close()


SAMPLE_QUESTIONS = [
    "Which 5 states have the highest literacy rate?",
    "Show population density (people per sq km) for each state",
    "How much was allocated and spent on each scheme in 2024-25?",
    "Which states used the smallest share of their health scheme budgets in 2024-25?",
    "How many hospital beds are there per state?",
    "Which departments get the most citizen grievances?",
    "What is the average time to resolve a grievance in each state?",
    "List the aspirational districts with their state",
]
