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
import time
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


def _merchant_prefixes(rng: random.Random, merchants_per_category: int) -> list[str]:
    """`rng.sample` (no repeats) below `len(MERCHANT_NAME_PREFIXES)` (64) --
    identical output to before this function existed, at any scale this
    project ran at until now. Above that, sampling without replacement is
    impossible (ValueError), so a 100x-scale dataset (thousands per
    category) instead samples with replacement; `build_merchants` appends a
    disambiguating index in that case, since plain reuse would collide."""
    if merchants_per_category <= len(MERCHANT_NAME_PREFIXES):
        return rng.sample(MERCHANT_NAME_PREFIXES, k=merchants_per_category)
    return [rng.choice(MERCHANT_NAME_PREFIXES) for _ in range(merchants_per_category)]


def build_merchants(rng: random.Random, merchants_per_category: int = MERCHANTS_PER_CATEGORY) -> list[Merchant]:
    large_scale = merchants_per_category > len(MERCHANT_NAME_PREFIXES)
    merchants: list[Merchant] = []
    for category in CATEGORIES:
        names = _merchant_prefixes(rng, merchants_per_category)
        for i, prefix in enumerate(names):
            archetype = _jittered_archetype(rng, ARCHETYPES[i % len(ARCHETYPES)])
            suffix = category.split(" ")[0]
            name = f"{prefix} {suffix} #{i + 1}" if large_scale else f"{prefix} {suffix}"
            merchant = Merchant(
                id=str(uuid.uuid4()),
                name=name,
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


def generate_batch_transactions(rng: random.Random, merchants_batch: list[Merchant], now: datetime):
    """Transactions/refunds/disputes/reputation for one bounded batch of
    merchants, not the whole dataset — insert_dataset calls this per batch
    and discards the result after copying it to Postgres, so peak memory
    stays proportional to `batch_size`, not to total dataset size. At a
    100x-scale dataset (millions of transactions), holding it all in one
    Python list at once would compete for RAM with Postgres itself on a
    single dev machine."""
    all_transactions, all_refunds, all_disputes, all_reputation = [], [], [], []
    for merchant in merchants_batch:
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
    return all_transactions, all_refunds, all_disputes, all_reputation


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
    max_attempts = 3
    for i in range(0, len(entries), chunk_size):
        chunk = entries[i : i + chunk_size]
        texts = [f"{name}. {desc}" for name, desc in chunk]
        result = None
        for attempt in range(1, max_attempts + 1):
            result = embed_texts(texts)
            if result is not None:
                break
            # embed_texts swallows the actual error (network hiccup, transient
            # rate limit, etc. all just return None) -- a short retry is
            # cheap insurance for a step this small (one batch, 60 items) but
            # important not to silently drop, since the whole product catalog
            # loses semantic search for a run if it's skipped.
            print(f"embedding batch {i}-{i + len(chunk)} attempt {attempt}/{max_attempts} failed, retrying...")
            time.sleep(2 * attempt)
        if result is None:
            print(f"embedding batch {i}-{i + len(chunk)} failed after {max_attempts} attempts -- "
                  f"those product types will have no embedding.")
            continue
        for (name, _desc), vector in zip(chunk, result):
            embeddings[name] = vector
    print(f"computed embeddings for {len(embeddings)}/{len(entries)} distinct product types.")
    return embeddings


def _copy_rows(cur, table: str, columns: list[str], rows: list[tuple]) -> None:
    """Bulk-loads `rows` via COPY FROM STDIN rather than one INSERT per row
    -- at a 100x-scale dataset (millions of transaction rows), row-by-row
    execute() round trips would take on the order of an hour; COPY does the
    same load in seconds. Columns not listed here get their schema default
    (or NULL) applied automatically, same as with INSERT."""
    if not rows:
        return
    col_list = ", ".join(columns)
    with cur.copy(f"COPY {table} ({col_list}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def insert_dataset(rng: random.Random, merchants: list[Merchant], reset: bool = False,
                    batch_size: int = 200, progress: bool = True) -> None:
    """`rng` must be the same generator `build_merchants` already advanced --
    transaction generation continues that one seeded stream rather than
    starting a fresh one, so the whole run stays deterministic end to end
    for a given SEED, exactly as it was before this function was split into
    batches.

    Processes merchants in batches of `batch_size`: generates that batch's
    transactions/refunds/disputes/reputation, COPYs them, and discards them
    before moving to the next batch, so peak memory is bounded by
    `batch_size` regardless of total dataset size (see
    generate_batch_transactions's docstring)."""
    import psycopg

    load_dotenv()
    database_url = os.environ["DATABASE_URL"]
    product_embeddings = _compute_product_pool_embeddings()
    now = datetime.now(timezone.utc)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if reset:
                # Cascades to products, transactions, refunds, disputes, reputation,
                # and trust_score_history via their ON DELETE CASCADE FKs — makes
                # re-running the generator while tuning archetypes/volume safe
                # instead of duplicating merchants on every run. product_embeddings
                # has no FK to merchants (keyed by product name, not id), so it
                # isn't touched by the cascade -- and is only truncated here if the
                # recompute above actually got something back. Wiping it
                # unconditionally would mean a transient embedding-API failure (rate
                # limit, network blip) permanently destroys previously-good
                # embeddings for no reason -- upsert-by-name (below) refreshes
                # existing rows in place when the recompute does succeed.
                cur.execute("TRUNCATE merchants CASCADE")
                if not product_embeddings:
                    print("  no embeddings computed this run -- leaving product_embeddings untouched.")

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
        conn.commit()

        with conn.cursor() as cur:
            _copy_rows(
                cur, "merchants", ["id", "name", "category_id", "declared_sla_days"],
                [(m.id, m.name, category_ids[m.category], m.declared_sla_days) for m in merchants],
            )
        conn.commit()
        if progress:
            print(f"  merchants: {len(merchants)} rows copied.", flush=True)

        with conn.cursor() as cur:
            product_rows = [
                (p["id"], m.id, category_ids[m.category], p["name"], p["description"], p["price_paise"])
                for m in merchants for p in m.products
            ]
            _copy_rows(cur, "products", ["id", "merchant_id", "category_id", "name", "description", "price_paise"],
                       product_rows)
        conn.commit()
        if progress:
            print(f"  products: {len(product_rows)} rows copied.", flush=True)

        with conn.cursor() as cur:
            for prod_name, vector in product_embeddings.items():
                cur.execute(
                    """
                    INSERT INTO product_embeddings (name, embedding) VALUES (%s, %s)
                    ON CONFLICT (name) DO UPDATE SET embedding = EXCLUDED.embedding
                    """,
                    (prod_name, json.dumps(vector)),
                )
        conn.commit()
        if progress:
            print(f"  product_embeddings: {len(product_embeddings)} rows upserted.", flush=True)

        total_txns = total_refunds = total_disputes = total_reputation = 0
        for batch_start in range(0, len(merchants), batch_size):
            batch = merchants[batch_start : batch_start + batch_size]
            transactions, refunds, disputes, reputation = generate_batch_transactions(rng, batch, now)

            with conn.cursor() as cur:
                _copy_rows(
                    cur, "transactions",
                    ["id", "merchant_id", "product_id", "amount_paise", "payment_method",
                     "status", "order_created_at", "payment_captured_at"],
                    [
                        (t["id"], t["merchant_id"], t["product_id"], t["amount_paise"], t["payment_method"],
                         t["status"], t["order_created_at"], t["payment_captured_at"])
                        for t in transactions
                    ],
                )
                _copy_rows(
                    cur, "refunds", ["id", "transaction_id", "reason_code", "amount_paise", "status"],
                    [(r["id"], r["transaction_id"], r["reason_code"], r["amount_paise"], r["status"]) for r in refunds],
                )
                _copy_rows(
                    cur, "disputes", ["id", "transaction_id", "reason_code", "status"],
                    [(d["id"], d["transaction_id"], d["reason_code"], d["status"]) for d in disputes],
                )
                _copy_rows(
                    cur, "reputation", ["merchant_id", "avg_rating", "review_count"],
                    [(r["merchant_id"], r["avg_rating"], r["review_count"]) for r in reputation],
                )
            conn.commit()

            total_txns += len(transactions)
            total_refunds += len(refunds)
            total_disputes += len(disputes)
            total_reputation += len(reputation)
            if progress:
                done = batch_start + len(batch)
                print(f"  seeded {done}/{len(merchants)} merchants "
                      f"({total_txns} txns, {total_refunds} refunds, {total_disputes} disputes so far)...", flush=True)

        if progress:
            print(f"  totals: {total_txns} transactions, {total_refunds} refunds, "
                  f"{total_disputes} disputes, {total_reputation} reputation rows.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="generate and summarize without touching the DB")
    parser.add_argument("--reset", action="store_true", help="truncate existing merchant data before inserting")
    parser.add_argument(
        "--merchants-per-category", type=int, default=MERCHANTS_PER_CATEGORY,
        help=f"merchants to generate per category (default {MERCHANTS_PER_CATEGORY})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=200,
        help="merchants per transaction-generation/COPY batch (default 200) -- bounds peak memory at large scale",
    )
    args = parser.parse_args()

    rng = random.Random(SEED)
    merchants = build_merchants(rng, args.merchants_per_category)

    print(f"Merchants: {len(merchants)} ({args.merchants_per_category} per category x {len(CATEGORIES)} categories)")
    for category in CATEGORIES:
        in_category = [m for m in merchants if m.category == category]
        products_in_category = sum(len(m.products) for m in in_category)
        print(f"  - {category:24s} merchants={len(in_category):6d} products={products_in_category:7d}")
    print(f"Products: {sum(len(m.products) for m in merchants)}")

    if args.dry_run:
        # Estimated, not exact: doesn't materialize every transaction/refund/
        # dispute dict just to count them (at 100x scale that's millions of
        # dicts for a summary line) -- expected value from each merchant's
        # archetype rates instead. insert_dataset's actual per-transaction
        # RNG draws (and its printed totals) are the real numbers.
        est_txns = sum(sum(m.archetype.txn_count_range) / 2 for m in merchants)
        est_captured = sum(sum(m.archetype.txn_count_range) / 2 * m.archetype.payment_success_rate for m in merchants)
        est_refunds = sum(
            sum(m.archetype.txn_count_range) / 2 * m.archetype.payment_success_rate * m.archetype.refund_rate
            for m in merchants
        )
        est_disputes = sum(
            sum(m.archetype.txn_count_range) / 2 * m.archetype.payment_success_rate * m.archetype.dispute_rate
            for m in merchants
        )
        print(f"Transactions: ~{est_txns:,.0f} (estimated from archetype rates, {est_captured:,.0f} captured)")
        print(f"Refunds: ~{est_refunds:,.0f} (estimated)")
        print(f"Disputes: ~{est_disputes:,.0f} (estimated)")
        print(f"Reputation rows: {len(merchants)}")
        print("\n--dry-run set: nothing written to the database.")
        return

    insert_dataset(rng, merchants, reset=args.reset, batch_size=args.batch_size)
    print("\nInserted synthetic dataset into DATABASE_URL.")


if __name__ == "__main__":
    main()
