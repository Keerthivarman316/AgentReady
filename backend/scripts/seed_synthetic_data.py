"""Generate synthetic merchants, catalog, and transaction history for AgentReady.

Produces MERCHANTS_PER_CATEGORY merchants per category, cycling through six
trust archetypes (trusted_leader / budget_reliable / flashy_risky /
inconsistent / premium_trusted / new_entrant), each with small per-merchant
jitter so same-archetype merchants aren't score-identical. Every merchant
carries the category's full product catalog, so every product type (e.g.
"earbuds") has one competing listing per merchant — real depth for the
Buyer Agent to rank against, not just one example per category.

Usage:
    python -m scripts.seed_synthetic_data --dry-run     # print summary only
    python -m scripts.seed_synthetic_data                # insert into DATABASE_URL
"""

from __future__ import annotations

import argparse
import json
import os
import random
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from app.llm_client import embed_texts, is_llm_configured

SEED = 42
MERCHANTS_PER_CATEGORY = 50

CATEGORIES = ["Electronics", "Fashion", "Home & Kitchen", "Beauty & Personal Care", "Sports & Outdoors"]

PRODUCT_POOL = {
    "Electronics": [
        ("Wireless Earbuds Pro", "Bluetooth 5.3 earbuds with active noise cancellation and 30hr case battery."),
        ("Smart Fitness Tracker", "Heart-rate and sleep tracking band with 10-day battery life."),
        ("4K Action Camera", "Waterproof action camera with image stabilization, 4K/60fps."),
        ("Portable Bluetooth Speaker", "IPX7 rated speaker with 12-hour playback."),
        ("USB-C Fast Charger 65W", "GaN charger, dual-port, laptop and phone compatible."),
        ("Noise Cancelling Headphones", "Over-ear ANC headphones with 40-hour battery."),
        ("27-inch Full HD Monitor", "IPS panel monitor, 75Hz refresh rate, HDMI + DisplayPort."),
        ("Mechanical Keyboard", "Hot-swappable mechanical keyboard with RGB backlight."),
        ("Wireless Mouse", "2.4GHz wireless mouse with silent clicks and 18-month battery."),
        ("1080p Webcam", "Autofocus USB webcam with built-in noise-cancelling mic."),
        ("20000mAh Power Bank", "Dual USB-C power bank with 65W fast charging passthrough."),
        ("Fitness Smartwatch", "AMOLED smartwatch with SpO2, GPS, and 7-day battery."),
    ],
    "Fashion": [
        ("Cotton Casual Shirt", "100% cotton regular-fit shirt, machine washable."),
        ("Slim Fit Denim Jeans", "Stretch denim, mid-rise, slim fit."),
        ("Running Sneakers", "Lightweight mesh running shoes with cushioned sole."),
        ("Leather Wallet", "Genuine leather bifold wallet with RFID blocking."),
        ("Wool Blend Sweater", "Crew-neck sweater, wool-acrylic blend."),
        ("Canvas Tote Bag", "Durable canvas tote with inner pocket."),
        ("Graphic Print T-Shirt", "100% cotton crew-neck tee with screen-printed graphic."),
        ("Formal Trousers", "Slim-fit formal trousers, wrinkle-resistant fabric."),
        ("Polarized Sunglasses", "UV400 polarized sunglasses with anti-glare lenses."),
        ("Genuine Leather Belt", "Reversible leather belt with metal buckle."),
        ("Ankle Boots", "Faux-leather ankle boots with block heel."),
        ("Sports Cap", "Adjustable cotton-blend cap with breathable mesh back."),
    ],
    "Home & Kitchen": [
        ("Stainless Steel Cookware Set", "5-piece induction-compatible cookware set."),
        ("Electric Kettle 1.5L", "Auto shut-off electric kettle with boil-dry protection."),
        ("Memory Foam Pillow", "Contoured cervical support memory foam pillow."),
        ("Non-Stick Frying Pan", "28cm non-stick frying pan, PFOA-free coating."),
        ("Ceramic Dinner Set", "16-piece ceramic dinnerware set, dishwasher safe."),
        ("LED Desk Lamp", "Dimmable LED desk lamp with USB charging port."),
        ("Digital Air Fryer", "4.5L digital air fryer with 8 preset cooking modes."),
        ("750W Mixer Grinder", "3-jar mixer grinder with overload protection."),
        ("Cotton Bedsheet Set", "King-size cotton bedsheet set with 2 pillow covers."),
        ("Table Fan", "16-inch high-speed table fan with 3-speed control."),
        ("Wall Clock", "Silent-sweep quartz wall clock, 12-inch dial."),
        ("Storage Organizer Set", "Stackable plastic storage bins with lids, set of 6."),
    ],
    "Beauty & Personal Care": [
        ("Vitamin C Face Serum", "Brightening serum with 10% vitamin C and hyaluronic acid."),
        ("Electric Hair Trimmer", "Cordless trimmer with ceramic blades and 90-min runtime."),
        ("Argan Oil Hair Mask", "Deep conditioning hair mask, 250ml, sulfate-free."),
        ("Sonic Facial Cleansing Brush", "Rechargeable silicone facial brush, 3 intensity levels."),
        ("SPF 50 Sunscreen Gel", "Lightweight, non-greasy broad-spectrum sunscreen, 100g."),
        ("Bamboo Bristle Toothbrush Set", "Pack of 4 biodegradable bamboo toothbrushes."),
        ("Daily Moisturizer", "Oil-free daily face moisturizer with ceramides, 100ml."),
        ("Tinted Lip Balm", "Nourishing tinted lip balm with SPF 15, pack of 3."),
        ("Ionic Hair Dryer", "1800W ionic hair dryer with 3 heat settings."),
        ("Eau de Parfum", "Long-lasting unisex eau de parfum, 50ml."),
        ("Manicure Kit", "Stainless steel nail care kit with travel case."),
        ("Gentle Face Wash", "Sulfate-free foaming face wash for daily use, 150ml."),
    ],
    "Sports & Outdoors": [
        ("Yoga Mat Pro", "6mm non-slip TPE yoga mat with carry strap."),
        ("Adjustable Dumbbell Set", "5-25kg adjustable dumbbell pair, space-saving."),
        ("Trekking Backpack 40L", "Water-resistant trekking backpack with rain cover."),
        ("Insulated Water Bottle 1L", "Vacuum-insulated stainless steel bottle, 24hr cold."),
        ("Resistance Band Set", "5-band set with door anchor and carry pouch."),
        ("Camping Tent 2-Person", "Lightweight double-layer tent with waterproof rating 3000mm."),
        ("Cycling Helmet", "Ventilated cycling helmet with adjustable fit dial."),
        ("Badminton Racket Set", "Pair of carbon-fiber rackets with shuttlecocks and cover."),
        ("Skipping Rope", "Ball-bearing speed rope with adjustable steel cable."),
        ("Swim Goggles", "Anti-fog UV-protected swim goggles with silicone strap."),
        ("Foldable Hiking Pole Pair", "Adjustable aluminum trekking poles with cork grips."),
        ("Football", "Size 5 match football, synthetic leather, all-weather."),
    ],
}

PRICE_BAND_PAISE = {
    "Electronics": (80_000, 400_000),
    "Fashion": (30_000, 250_000),
    "Home & Kitchen": (40_000, 300_000),
    "Beauty & Personal Care": (15_000, 150_000),
    "Sports & Outdoors": (50_000, 350_000),
}

MERCHANT_NAME_PREFIXES = [
    "Nova", "Bright", "Urban", "Prime", "Zenith", "Coral", "Swift", "Aster",
    "Northline", "Ember", "Vertex", "Willow", "Cedar", "Halcyon", "Marlow",
    "Sundew", "Ashgrove", "Palisade", "Quill", "Rosewood", "Thistle", "Meridian",
    "Amber", "Fernbrook", "Solace", "Wrenfield", "Bayline", "Copperfield",
    "Larkspur", "Windham", "Ironwood", "Silverlake", "Brightmoor", "Hearthstone",
    "Wildflower", "Stonebridge", "Maplewood", "Riverstone", "Goldenrod",
    "Frostpine", "Sunhaven", "Moonvale", "Clearwater", "Timberline",
    "Brightside", "Wavecrest", "Starling", "Foxglove", "Driftwood", "Everglade",
    "Highmark", "Duskwood", "Silverline", "Northgate", "Eastbrook", "Westfield",
    "Southport", "Glenmoor", "Oakhaven", "Birchwood", "Pinehurst", "Cloverdale",
]

REASON_CODES_DELIVERY = ["item_not_delivered", "item_not_received"]
REASON_CODES_OTHER = ["item_defective", "wrong_item", "buyer_remorse"]
DISPUTE_REASON_CODES = ["item_not_delivered", "item_not_received", "item_defective", "unauthorized_transaction"]

PAYMENT_METHODS = ["card", "upi", "cod"]
PAYMENT_METHOD_WEIGHTS = [0.35, 0.45, 0.20]

TXNS_PER_MERCHANT_DEFAULT = (120, 220)


@dataclass
class Archetype:
    key: str
    payment_success_rate: float
    refund_rate: float
    dispute_rate: float
    sla_violation_rate: float
    avg_rating: float
    review_count_range: tuple[int, int]
    price_multiplier: float
    txn_count_range: tuple[int, int] = TXNS_PER_MERCHANT_DEFAULT


ARCHETYPES = [
    Archetype("trusted_leader", 0.97, 0.03, 0.005, 0.05, 4.6, (150, 400), 1.05),
    Archetype("budget_reliable", 0.93, 0.06, 0.01, 0.10, 4.1, (80, 200), 0.85),
    Archetype("flashy_risky", 0.85, 0.18, 0.06, 0.35, 4.7, (500, 1200), 1.00),
    Archetype("inconsistent", 0.89, 0.10, 0.03, 0.20, 3.6, (40, 120), 0.95),
    Archetype("premium_trusted", 0.99, 0.015, 0.003, 0.03, 4.4, (200, 450), 1.35),
    # Thin history on purpose — a cold-start merchant that hasn't accumulated the
    # transaction volume the other archetypes have.
    Archetype("new_entrant", 0.91, 0.08, 0.02, 0.15, 3.9, (10, 40), 0.90, txn_count_range=(15, 35)),
]

HISTORY_DAYS = 180


@dataclass
class Merchant:
    id: str
    name: str
    category: str
    declared_sla_days: int
    archetype: Archetype
    products: list[dict] = field(default_factory=list)


def _jitter(rng: random.Random, value: float, pct: float, lo: float, hi: float) -> float:
    delta = value * pct
    return max(lo, min(hi, value + rng.uniform(-delta, delta)))


def _jittered_archetype(rng: random.Random, archetype: Archetype) -> Archetype:
    """A per-merchant copy of the archetype with small random variance, so 8+
    merchants sharing the same archetype don't all score identically."""
    return replace(
        archetype,
        payment_success_rate=_jitter(rng, archetype.payment_success_rate, 0.03, lo=0.5, hi=0.995),
        refund_rate=_jitter(rng, archetype.refund_rate, 0.25, lo=0.0, hi=0.5),
        dispute_rate=_jitter(rng, archetype.dispute_rate, 0.25, lo=0.0, hi=0.2),
        sla_violation_rate=_jitter(rng, archetype.sla_violation_rate, 0.25, lo=0.0, hi=0.6),
        avg_rating=_jitter(rng, archetype.avg_rating, 0.06, lo=1.0, hi=5.0),
        price_multiplier=_jitter(rng, archetype.price_multiplier, 0.08, lo=0.5, hi=2.0),
    )


def build_merchants(rng: random.Random, merchants_per_category: int = MERCHANTS_PER_CATEGORY) -> list[Merchant]:
    merchants: list[Merchant] = []
    for category in CATEGORIES:
        names = rng.sample(MERCHANT_NAME_PREFIXES, k=merchants_per_category)
        for i, prefix in enumerate(names):
            archetype = _jittered_archetype(rng, ARCHETYPES[i % len(ARCHETYPES)])
            suffix = category.split(" ")[0]
            merchant = Merchant(
                id=str(uuid.uuid4()),
                name=f"{prefix} {suffix}",
                category=category,
                declared_sla_days=rng.choice([2, 3, 4, 5]),
                archetype=archetype,
            )
            # Every merchant carries the full catalog so every product type
            # (e.g. earbuds) has one competing listing per merchant — real
            # depth to rank against, not a sampled subset.
            for prod_name, prod_desc in PRODUCT_POOL[category]:
                lo, hi = PRICE_BAND_PAISE[category]
                base_price = rng.randint(lo, hi)
                price = int(base_price * archetype.price_multiplier)
                merchant.products.append(
                    {
                        "id": str(uuid.uuid4()),
                        "name": prod_name,
                        "description": prod_desc,
                        "price_paise": price,
                    }
                )
            merchants.append(merchant)
    return merchants


def build_transactions(rng: random.Random, merchant: Merchant, now: datetime):
    transactions = []
    refunds = []
    disputes = []

    n = rng.randint(*merchant.archetype.txn_count_range)
    for _ in range(n):
        product = rng.choice(merchant.products)
        order_created_at = now - timedelta(
            days=rng.uniform(0, HISTORY_DAYS),
            hours=rng.uniform(0, 24),
        )
        method = rng.choices(PAYMENT_METHODS, weights=PAYMENT_METHOD_WEIGHTS, k=1)[0]

        txn_id = str(uuid.uuid4())
        success = rng.random() < merchant.archetype.payment_success_rate
        status = "captured" if success else "failed"

        payment_captured_at = None
        if success and method == "cod":
            violated = rng.random() < merchant.archetype.sla_violation_rate
            delivery_days = merchant.declared_sla_days + (
                rng.uniform(2, 6) if violated else rng.uniform(-0.5, 0.5)
            )
            payment_captured_at = order_created_at + timedelta(days=max(delivery_days, 0.2))
        elif success:
            payment_captured_at = order_created_at + timedelta(minutes=rng.uniform(1, 30))

        transactions.append(
            {
                "id": txn_id,
                "merchant_id": merchant.id,
                "product_id": product["id"],
                "amount_paise": product["price_paise"],
                "payment_method": method,
                "status": status,
                "order_created_at": order_created_at,
                "payment_captured_at": payment_captured_at,
            }
        )

        if success and rng.random() < merchant.archetype.refund_rate:
            delivery_related = rng.random() < merchant.archetype.sla_violation_rate
            reason = rng.choice(REASON_CODES_DELIVERY if delivery_related else REASON_CODES_OTHER)
            refunds.append(
                {
                    "id": str(uuid.uuid4()),
                    "transaction_id": txn_id,
                    "reason_code": reason,
                    "amount_paise": product["price_paise"],
                    "status": rng.choices(["processed", "pending", "rejected"], weights=[0.8, 0.15, 0.05])[0],
                }
            )

        if success and rng.random() < merchant.archetype.dispute_rate:
            disputes.append(
                {
                    "id": str(uuid.uuid4()),
                    "transaction_id": txn_id,
                    "reason_code": rng.choice(DISPUTE_REASON_CODES),
                    "status": rng.choices(["open", "won", "lost"], weights=[0.3, 0.4, 0.3])[0],
                }
            )

    return transactions, refunds, disputes


def generate_dataset(merchants_per_category: int = MERCHANTS_PER_CATEGORY):
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc)

    merchants = build_merchants(rng, merchants_per_category)

    all_transactions = []
    all_refunds = []
    all_disputes = []
    all_reputation = []

    for merchant in merchants:
        transactions, refunds, disputes = build_transactions(rng, merchant, now)
        all_transactions.extend(transactions)
        all_refunds.extend(refunds)
        all_disputes.extend(disputes)
        lo, hi = merchant.archetype.review_count_range
        all_reputation.append(
            {
                "merchant_id": merchant.id,
                "avg_rating": round(max(1.0, min(5.0, merchant.archetype.avg_rating + rng.uniform(-0.15, 0.15))), 1),
                "review_count": rng.randint(lo, hi),
            }
        )

    return merchants, all_transactions, all_refunds, all_disputes, all_reputation


def _compute_product_pool_embeddings() -> dict[str, list[float]]:
    """Maps product name -> 768-dim Gemini embedding, computed once per
    distinct product type in PRODUCT_POOL rather than once per merchant
    listing -- every merchant in a category carries the identical catalog,
    so the same ~60 (name, description) pairs get embedded regardless of
    how many merchants (or how large a future dataset) reuses them. Returns
    {} when GEMINI_API_KEY isn't configured -- seeding still works, products
    just keep a null embedding and semantic search stays unavailable until
    a key is added and this script is re-run with --reset."""
    if not is_llm_configured():
        print("GEMINI_API_KEY not configured -- skipping product embeddings (semantic search unavailable).")
        return {}

    entries = [(name, desc) for products in PRODUCT_POOL.values() for name, desc in products]
    embeddings: dict[str, list[float]] = {}
    chunk_size = 100
    for i in range(0, len(entries), chunk_size):
        chunk = entries[i : i + chunk_size]
        texts = [f"{name}. {desc}" for name, desc in chunk]
        result = embed_texts(texts)
        if result is None:
            print(f"embedding batch {i}-{i + len(chunk)} failed -- those product types will have no embedding.")
            continue
        for (name, _desc), vector in zip(chunk, result):
            embeddings[name] = vector
    print(f"computed embeddings for {len(embeddings)}/{len(entries)} distinct product types.")
    return embeddings


def insert_dataset(merchants, transactions, refunds, disputes, reputation, reset: bool = False):
    import psycopg

    load_dotenv()
    database_url = os.environ["DATABASE_URL"]
    product_embeddings = _compute_product_pool_embeddings()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if reset:
                # Cascades to products, transactions, refunds, disputes, reputation,
                # and trust_score_history via their ON DELETE CASCADE FKs — makes
                # re-running the generator while tuning archetypes/volume safe
                # instead of duplicating merchants on every run.
                cur.execute("TRUNCATE merchants CASCADE")

            category_ids = {}
            for name in CATEGORIES:
                cur.execute(
                    """
                    INSERT INTO categories (name) VALUES (%s)
                    ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (name,),
                )
                category_ids[name] = cur.fetchone()[0]

            for merchant in merchants:
                cur.execute(
                    """
                    INSERT INTO merchants (id, name, category_id, declared_sla_days)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (merchant.id, merchant.name, category_ids[merchant.category], merchant.declared_sla_days),
                )
                for product in merchant.products:
                    embedding = product_embeddings.get(product["name"])
                    cur.execute(
                        """
                        INSERT INTO products (id, merchant_id, category_id, name, description, price_paise, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            product["id"],
                            merchant.id,
                            category_ids[merchant.category],
                            product["name"],
                            product["description"],
                            product["price_paise"],
                            json.dumps(embedding) if embedding is not None else None,
                        ),
                    )

            for txn in transactions:
                cur.execute(
                    """
                    INSERT INTO transactions
                        (id, merchant_id, product_id, amount_paise, payment_method,
                         status, order_created_at, payment_captured_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        txn["id"], txn["merchant_id"], txn["product_id"], txn["amount_paise"],
                        txn["payment_method"], txn["status"], txn["order_created_at"], txn["payment_captured_at"],
                    ),
                )

            for refund in refunds:
                cur.execute(
                    """
                    INSERT INTO refunds (id, transaction_id, reason_code, amount_paise, status)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (refund["id"], refund["transaction_id"], refund["reason_code"], refund["amount_paise"], refund["status"]),
                )

            for dispute in disputes:
                cur.execute(
                    """
                    INSERT INTO disputes (id, transaction_id, reason_code, status)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (dispute["id"], dispute["transaction_id"], dispute["reason_code"], dispute["status"]),
                )

            for rep in reputation:
                cur.execute(
                    """
                    INSERT INTO reputation (merchant_id, avg_rating, review_count)
                    VALUES (%s, %s, %s)
                    """,
                    (rep["merchant_id"], rep["avg_rating"], rep["review_count"]),
                )

        conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="generate and summarize without touching the DB")
    parser.add_argument("--reset", action="store_true", help="truncate existing merchant data before inserting")
    parser.add_argument(
        "--merchants-per-category", type=int, default=MERCHANTS_PER_CATEGORY,
        help=f"merchants to generate per category (default {MERCHANTS_PER_CATEGORY})",
    )
    args = parser.parse_args()

    merchants, transactions, refunds, disputes, reputation = generate_dataset(args.merchants_per_category)

    print(f"Merchants: {len(merchants)} ({args.merchants_per_category} per category x {len(CATEGORIES)} categories)")
    for category in CATEGORIES:
        in_category = [m for m in merchants if m.category == category]
        products_in_category = sum(len(m.products) for m in in_category)
        print(f"  - {category:24s} merchants={len(in_category):3d} products={products_in_category:4d}")
    print(f"Products: {sum(len(m.products) for m in merchants)}")
    print(f"Transactions: {len(transactions)}")
    print(f"Refunds: {len(refunds)}")
    print(f"Disputes: {len(disputes)}")
    print(f"Reputation rows: {len(reputation)}")

    if args.dry_run:
        print("\n--dry-run set: nothing written to the database.")
        return

    insert_dataset(merchants, transactions, refunds, disputes, reputation, reset=args.reset)
    print("\nInserted synthetic dataset into DATABASE_URL.")


if __name__ == "__main__":
    main()
