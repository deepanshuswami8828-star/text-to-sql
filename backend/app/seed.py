"""Generate the bundled sample database: a small e-commerce store (prices in INR).

The data is random but deterministic (fixed seed), so the same questions give the
same answers on every machine. Run directly to rebuild it:

    python -m app.seed --force
"""

from __future__ import annotations

import argparse
import bisect
import os
import random
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT
);

CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    price          REAL NOT NULL,      -- selling price in INR
    cost           REAL NOT NULL,      -- purchase cost in INR
    stock_quantity INTEGER NOT NULL,
    launched_on    DATE NOT NULL
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    city         TEXT NOT NULL,
    state        TEXT NOT NULL,
    segment      TEXT NOT NULL CHECK (segment IN ('Consumer', 'Corporate', 'Small Business')),
    signup_date  DATE NOT NULL
);

CREATE TABLE employees (
    employee_id  INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    title        TEXT NOT NULL,
    region       TEXT NOT NULL,
    manager_id   INTEGER REFERENCES employees(employee_id),
    hire_date    DATE NOT NULL,
    salary       REAL NOT NULL         -- yearly salary in INR
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    employee_id     INTEGER NOT NULL REFERENCES employees(employee_id),
    order_date      DATE NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('delivered', 'shipped', 'processing', 'cancelled', 'returned')),
    payment_method  TEXT NOT NULL CHECK (payment_method IN ('UPI', 'Credit Card', 'Debit Card', 'Net Banking', 'Cash on Delivery')),
    shipping_city   TEXT NOT NULL
);

CREATE TABLE order_items (
    order_item_id  INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL REFERENCES orders(order_id),
    product_id     INTEGER NOT NULL REFERENCES products(product_id),
    quantity       INTEGER NOT NULL,
    unit_price     REAL NOT NULL,      -- price per unit at time of order, INR
    discount       REAL NOT NULL DEFAULT 0  -- fraction, e.g. 0.10 = 10% off
);

CREATE TABLE reviews (
    review_id    INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(product_id),
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_date  DATE NOT NULL,
    comment      TEXT
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
"""

CATEGORIES = {
    "Electronics": ("Phones, laptops and gadgets", [
        ("Galaxy Smartphone A55", 32999), ("Redmi Note 14 Pro", 24999), ("iPhone 16", 79900),
        ("ThinkPad E14 Laptop", 68990), ("boAt Airdopes 141", 1299), ("Sony WH-1000XM5", 29990),
        ("Mi Power Bank 20000mAh", 1999), ("Fire-Boltt Smartwatch", 2499), ("Logitech MX Master 3S", 9495),
    ]),
    "Home & Kitchen": ("Appliances and cookware", [
        ("Prestige Pressure Cooker 5L", 2199), ("Philips Air Fryer", 8999), ("Milton Steel Bottle 1L", 649),
        ("Pigeon Non-stick Tawa", 799), ("Bajaj Mixer Grinder", 3499), ("Kent RO Water Purifier", 15500),
        ("Havells Ceiling Fan", 2899),
    ]),
    "Fashion": ("Clothing and footwear", [
        ("Levi's 511 Jeans", 2999), ("Allen Solly Formal Shirt", 1599), ("Nike Revolution 7 Shoes", 3695),
        ("Fabindia Cotton Kurta", 1890), ("Ray-Ban Aviator", 8490), ("Woodland Leather Belt", 1295),
        ("Puma Track Jacket", 2799),
    ]),
    "Books": ("Fiction, non-fiction and textbooks", [
        ("Atomic Habits", 499), ("The Psychology of Money", 399), ("Wings of Fire", 299),
        ("Clean Code", 899), ("Ikigai", 350), ("The White Tiger", 425), ("Sapiens", 599),
    ]),
    "Sports & Fitness": ("Sports gear and fitness equipment", [
        ("SG Cricket Bat English Willow", 6999), ("Yonex Badminton Racquet", 2490), ("Nivia Football", 899),
        ("Boldfit Yoga Mat", 699), ("Cosco Dumbbell Set 10kg", 1899), ("Decathlon Cycling Helmet", 1499),
    ]),
    "Beauty & Personal Care": ("Skincare, grooming and wellness", [
        ("Mamaearth Face Wash", 299), ("Philips Trimmer BT3221", 1599), ("Nivea Body Lotion 400ml", 425),
        ("Lakme Sunscreen SPF50", 399), ("Forest Essentials Hair Oil", 1250),
    ]),
    "Grocery": ("Daily essentials and gourmet food", [
        ("Tata Tea Gold 1kg", 560), ("Aashirvaad Atta 10kg", 495), ("Fortune Sunflower Oil 5L", 899),
        ("Haldiram's Bhujia 1kg", 340), ("Nescafe Classic 200g", 690), ("Daawat Basmati Rice 5kg", 799),
    ]),
    "Toys & Games": ("Toys, board games and puzzles", [
        ("LEGO Classic Brick Box", 2999), ("Funskool Monopoly", 1199), ("Hot Wheels 10-Car Pack", 999),
        ("Rubik's Cube 3x3", 499), ("Remote Control Car", 1799),
    ]),
}

CITIES = [
    ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"), ("Nagpur", "Maharashtra"),
    ("Delhi", "Delhi"), ("Bengaluru", "Karnataka"), ("Mysuru", "Karnataka"),
    ("Hyderabad", "Telangana"), ("Chennai", "Tamil Nadu"), ("Coimbatore", "Tamil Nadu"),
    ("Kolkata", "West Bengal"), ("Ahmedabad", "Gujarat"), ("Surat", "Gujarat"),
    ("Jaipur", "Rajasthan"), ("Lucknow", "Uttar Pradesh"), ("Noida", "Uttar Pradesh"),
    ("Chandigarh", "Chandigarh"), ("Kochi", "Kerala"), ("Indore", "Madhya Pradesh"),
    ("Bhopal", "Madhya Pradesh"), ("Gurugram", "Haryana"),
]
# Bigger cities get more customers.
CITY_WEIGHTS = [14, 7, 3, 13, 12, 3, 9, 8, 3, 7, 6, 4, 5, 4, 4, 3, 3, 3, 2, 5]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
    "Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Anika", "Navya", "Myra", "Kavya", "Priya",
    "Rahul", "Neha", "Amit", "Pooja", "Vikram", "Sneha", "Karan", "Meera", "Siddharth", "Riya",
    "Deepak", "Nisha", "Manish", "Tanvi", "Harsh", "Isha", "Yash", "Shreya", "Kabir", "Zoya",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Singh", "Kumar", "Mehta",
    "Joshi", "Chopra", "Rao", "Das", "Banerjee", "Kapoor", "Malhotra", "Agarwal", "Pillai", "Khan",
    "Swami", "Bose", "Menon", "Desai", "Chauhan",
]
SEGMENTS = (["Consumer"] * 7) + (["Corporate"] * 2) + ["Small Business"]
STATUSES = (["delivered"] * 75) + (["shipped"] * 8) + (["processing"] * 5) + (["cancelled"] * 7) + (["returned"] * 5)
PAYMENTS = (["UPI"] * 45) + (["Credit Card"] * 20) + (["Debit Card"] * 12) + (["Net Banking"] * 8) + (["Cash on Delivery"] * 15)
REGIONS = ["North", "South", "East", "West"]

GOOD_COMMENTS = ["Excellent quality!", "Value for money.", "Fast delivery, very happy.", "Works as described.",
                 "Would buy again.", "Great product.", "Exceeded my expectations."]
OK_COMMENTS = ["Decent for the price.", "Average quality.", "Okay, nothing special.", "Packaging could be better."]
BAD_COMMENTS = ["Stopped working in a week.", "Not as described.", "Poor quality.", "Delivery was very late."]

START = date(2024, 1, 1)
END = date(2026, 10, 31)


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build(path: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)

        # Categories & products
        products: list[tuple[int, float]] = []  # (product_id, price)
        pid = 0
        for cid, (cname, (desc, items)) in enumerate(CATEGORIES.items(), start=1):
            conn.execute("INSERT INTO categories VALUES (?, ?, ?)", (cid, cname, desc))
            for pname, price in items:
                pid += 1
                margin = rng.uniform(0.15, 0.45)
                cost = round(price * (1 - margin), 2)
                launched = _rand_date(rng, date(2022, 1, 1), date(2025, 6, 30))
                stock = rng.choice([0, 3, 8]) if rng.random() < 0.08 else rng.randint(10, 400)
                conn.execute(
                    "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (pid, pname, cid, float(price), cost, stock, launched.isoformat()),
                )
                products.append((pid, float(price)))
        # Popular products get ordered more often.
        product_weights = [rng.uniform(0.3, 3.0) for _ in products]
        # A few products are never ordered (useful for "products never ordered" questions).
        for idx in rng.sample(range(len(products)), 3):
            product_weights[idx] = 0.0

        # Employees (sales team with managers)
        emp_rows = []
        eid = 0
        for region in REGIONS:
            eid += 1
            manager = eid
            emp_rows.append((eid, rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES), "Regional Sales Manager",
                             region, None, _rand_date(rng, date(2018, 1, 1), date(2021, 12, 31)),
                             float(rng.randrange(1_800_000, 2_600_000, 50_000))))
            for _ in range(3):
                eid += 1
                emp_rows.append((eid, rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES), "Sales Executive",
                                 region, manager, _rand_date(rng, date(2020, 1, 1), date(2025, 3, 31)),
                                 float(rng.randrange(450_000, 1_100_000, 25_000))))
        conn.executemany(
            "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(e[0], e[1], e[2], e[3], e[4], e[5], e[6].isoformat(), e[7]) for e in emp_rows],
        )
        employee_ids = [e[0] for e in emp_rows if e[5] is not None]

        # Customers
        customers: list[tuple[int, str, date]] = []
        used_emails: set[str] = set()
        for cust_id in range(1, 301):
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            base = f"{first}.{last}".lower()
            email = f"{base}@example.com"
            n = 1
            while email in used_emails:
                n += 1
                email = f"{base}{n}@example.com"
            used_emails.add(email)
            city, state = rng.choices(CITIES, weights=CITY_WEIGHTS)[0]
            signup = _rand_date(rng, date(2023, 6, 1), date(2026, 6, 30))
            conn.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (cust_id, first, last, email, city, state, rng.choice(SEGMENTS), signup.isoformat()),
            )
            customers.append((cust_id, city, signup))
        # Some customers are much more active than others.
        customer_weights = [rng.paretovariate(1.6) for _ in customers]

        # Orders & order items: steady growth over time plus an Oct-Nov festive-season bump.
        by_signup = sorted(zip(customers, customer_weights), key=lambda cw: cw[0][2])
        signup_dates = [c[2] for c, _ in by_signup]
        total_days = (END - START).days
        order_id = 0
        item_id = 0
        bought: list[tuple[int, int, date]] = []  # (customer_id, product_id, order_date)
        while order_id < 2000:
            od = _rand_date(rng, START, END)
            growth = 0.45 + 0.55 * ((od - START).days / total_days)
            season = 1.0 if od.month in (10, 11) else 0.7
            if rng.random() > growth * season:
                continue
            eligible = bisect.bisect_right(signup_dates, od)  # customers signed up by then
            if eligible == 0:
                continue
            pool = by_signup[:eligible]
            (cust_id, city, _signup), _w = rng.choices(pool, weights=[w for _, w in pool])[0]
            order_id += 1
            status = rng.choice(STATUSES)
            if (END - od).days < 7:
                status = rng.choice(["processing", "shipped"])
            conn.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
                (order_id, cust_id, rng.choice(employee_ids), od.isoformat(), status,
                 rng.choice(PAYMENTS), city if rng.random() < 0.9 else rng.choice(CITIES)[0]),
            )
            n_items = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
            chosen = set()
            for _ in range(n_items):
                p_index = rng.choices(range(len(products)), weights=product_weights)[0]
                if p_index in chosen:
                    continue
                chosen.add(p_index)
                prod_id, price = products[p_index]
                item_id += 1
                qty = rng.choices([1, 2, 3, 5], weights=[70, 20, 7, 3])[0]
                discount = rng.choice([0, 0, 0, 0.05, 0.10, 0.15, 0.20]) if od.month in (10, 11) \
                    else rng.choice([0, 0, 0, 0, 0.05, 0.10])
                conn.execute(
                    "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)",
                    (item_id, order_id, prod_id, qty, price, discount),
                )
                if status == "delivered":
                    bought.append((cust_id, prod_id, od))

        # Reviews from customers who received the product
        review_id = 0
        product_quality = {pid: rng.uniform(2.6, 4.8) for pid, _ in products}
        for cust_id, prod_id, od in rng.sample(bought, k=min(700, len(bought))):
            review_id += 1
            rating = max(1, min(5, round(rng.gauss(product_quality[prod_id], 0.9))))
            comments = GOOD_COMMENTS if rating >= 4 else OK_COMMENTS if rating == 3 else BAD_COMMENTS
            comment = rng.choice(comments) if rng.random() < 0.8 else None
            rdate = min(od + timedelta(days=rng.randint(3, 40)), END)
            conn.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?)",
                (review_id, prod_id, cust_id, rating, rdate.isoformat(), comment),
            )

        conn.commit()
    finally:
        conn.close()


def ensure_sample_database(path: Path, force: bool = False) -> Path:
    """Create the sample database at `path` if it doesn't exist (or if force=True)."""
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        tmp_path.unlink()  # sqlite wants to create the file itself
        build(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return path


SAMPLE_QUESTIONS = [
    "Who are the top 5 customers by total amount spent?",
    "Show monthly revenue for 2025",
    "Which product category has the highest average rating?",
    "How many orders were cancelled in each city?",
    "Which sales executives handled the most delivered orders in 2025?",
    "List products that have never been ordered",
    "What is the average order value for each payment method?",
    "Which products are low on stock (fewer than 10 units)?",
]


if __name__ == "__main__":
    from .config import get_settings

    parser = argparse.ArgumentParser(description="Build the sample e-commerce database.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if it already exists")
    args = parser.parse_args()
    target = get_settings().sample_dir / "ecommerce.db"
    ensure_sample_database(target, force=args.force)
    print(f"Sample database ready at {target}")
