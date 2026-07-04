

"""
SEO Metrics Builder

Builds aggregated SEO metrics from query_rank_snapshots:
- avg position
- visibility (coverage)
- top10 / top50 / top100 counts
- total queries per SKU (nm_id)

This is the metrics layer of the SEO system.
"""

from typing import Dict, Any, List
import psycopg2


# -----------------------------
# DB CONFIG (adjust if needed)
# -----------------------------
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": 5432,
}


# -----------------------------
# CORE METRICS BUILDER
# -----------------------------
def fetch_rank_snapshots(conn) -> List[Dict[str, Any]]:
    """
    Pull raw SEO rank snapshots from DB.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                nm_id,
                query,
                position,
                page,
                brand,
                product_name
            FROM query_rank_snapshots
            WHERE position IS NOT NULL
        """)
        rows = cur.fetchall()

    return [
        {
            "nm_id": r[0],
            "query": r[1],
            "position": r[2],
            "page": r[3],
            "brand": r[4],
            "product_name": r[5],
        }
        for r in rows
    ]


def build_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates SEO metrics per nm_id.
    """

    metrics = {}

    for r in rows:
        nm_id = r["nm_id"]
        pos = r["position"]

        if nm_id not in metrics:
            metrics[nm_id] = {
                "nm_id": nm_id,
                "total_queries": 0,
                "avg_position_sum": 0,
                "top10": 0,
                "top50": 0,
                "top100": 0,
            }

        m = metrics[nm_id]

        m["total_queries"] += 1
        m["avg_position_sum"] += pos

        if pos <= 10:
            m["top10"] += 1
        if pos <= 50:
            m["top50"] += 1
        if pos <= 100:
            m["top100"] += 1

    # finalize
    for nm_id, m in metrics.items():
        m["avg_position"] = round(m["avg_position_sum"] / m["total_queries"], 2)
        m["coverage"] = round(m["top100"] / m["total_queries"], 2)

        del m["avg_position_sum"]

    return metrics


def save_metrics(conn, metrics: Dict[str, Any]):
    """
    Saves aggregated metrics into seo_metrics table.
    """

    with conn.cursor() as cur:
        for nm_id, m in metrics.items():
            cur.execute("""
                INSERT INTO seo_metrics (
                    nm_id,
                    total_queries,
                    avg_position,
                    top10,
                    top50,
                    top100,
                    coverage
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (nm_id)
                DO UPDATE SET
                    total_queries = EXCLUDED.total_queries,
                    avg_position = EXCLUDED.avg_position,
                    top10 = EXCLUDED.top10,
                    top50 = EXCLUDED.top50,
                    top100 = EXCLUDED.top100,
                    coverage = EXCLUDED.coverage
            """, (
                m["nm_id"],
                m["total_queries"],
                m["avg_position"],
                m["top10"],
                m["top50"],
                m["top100"],
                m["coverage"],
            ))

    conn.commit()


def run():
    """
    Main pipeline:
    snapshots -> metrics -> seo_metrics table
    """

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        rows = fetch_rank_snapshots(conn)
        metrics = build_metrics(rows)
        save_metrics(conn, metrics)

        print(f"Built metrics for {len(metrics)} SKUs")

    finally:
        conn.close()


if __name__ == "__main__":
    run()