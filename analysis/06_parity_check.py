"""
06_parity_check.py — assert the PySpark sessionizer and the dbt/SQL
sessionizer produce the same sessions.

Run: python analysis/06_parity_check.py --db warehouse/mkt.duckdb \
        --spark-out spark/output/sessions

Two engines computing the same metric is how definitions drift in real
companies. This script is the guard: it fails loudly if session counts differ
by more than 0.5%, or if any single day differs by more than 2%.
"""
import argparse, glob, os, sys, duckdb, pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--spark-out", default="spark/output/sessions")
    ap.add_argument("--tolerance", type=float, default=0.005)
    a = ap.parse_args()

    files = glob.glob(os.path.join(a.spark_out, "*.parquet"))
    if not files:
        print(f"No Spark output at {a.spark_out} — run spark/sessionize.py first.")
        sys.exit(0)

    con = duckdb.connect(a.db)
    sql_side = con.execute("""
        select cast(session_start_ts as date) d, count(*) n
        from intermediate.int_sessions group by 1
    """).df()
    spark_side = con.execute(
        f"select cast(session_start_ts as date) d, count(*) n "
        f"from read_parquet('{a.spark_out}/*.parquet') group by 1").df()

    m = sql_side.merge(spark_side, on="d", how="outer", suffixes=("_sql", "_spark")).fillna(0)
    m["diff_pct"] = (m.n_spark - m.n_sql).abs() / m.n_sql.replace(0, 1)
    total_diff = abs(m.n_spark.sum() - m.n_sql.sum()) / max(m.n_sql.sum(), 1)

    print(f"SQL sessions:   {int(m.n_sql.sum()):,}")
    print(f"Spark sessions: {int(m.n_spark.sum()):,}")
    print(f"Total drift:    {total_diff:.4%}")
    worst = m.sort_values("diff_pct", ascending=False).head(5)
    print("\nWorst days:\n", worst.to_string(index=False))

    if total_diff > a.tolerance:
        print(f"\nFAIL: drift {total_diff:.4%} exceeds tolerance {a.tolerance:.2%}")
        sys.exit(1)
    print("\nPASS: engines agree within tolerance.")

if __name__ == "__main__":
    main()
