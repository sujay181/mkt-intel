"""
sessionize.py — PySpark sessionization, parity-checked against the dbt model.

Local run:
    pip install pyspark
    python spark/sessionize.py --input raw/segment_events --output spark/output/sessions

Databricks Community Edition:
    1. Upload raw/segment_events/*.jsonl to DBFS: /FileStore/mkt/segment_events/
    2. Create a cluster (Community gives you one free 15GB driver-only node)
    3. Upload this file as a notebook or use %run
    4. Set INPUT = "dbfs:/FileStore/mkt/segment_events/*.jsonl"
       Set OUTPUT = "dbfs:/FileStore/mkt/sessions"

WHY THIS EXISTS
---------------
Not because 7 million rows need Spark — they do not. It exists because the JD
asks for PySpark/Databricks and because running the SAME business logic in two
engines is the honest way to demonstrate you understand that a metric
definition must survive a change of compute. analysis/06_parity_check.py
asserts the two agree within 0.5%; if they diverge, one of them is wrong and
the dashboard is lying.

The window function below is the exact analogue of the lag/sum pattern in
models/intermediate/int_sessions.sql. Keep them in sync or delete one.
"""
import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


def build(spark, input_path: str, timeout_minutes: int, bot_threshold: int):
    raw = spark.read.json(input_path)

    ev = (raw
          .select(
              F.col("messageId").alias("message_id"),
              F.col("type").alias("event_type"),
              F.col("anonymousId").alias("anonymous_id"),
              F.col("userId").alias("user_id"),
              F.to_timestamp("timestamp").alias("event_ts"),
              F.col("context.campaign.source").alias("utm_source_raw"),
              F.col("context.campaign.medium").alias("utm_medium_raw"),
              F.col("context.campaign.name").alias("utm_campaign_name"),
              F.col("context.userAgent").alias("user_agent"),
              F.col("context.device.type").alias("device_type"),
              F.col("properties.campaign_id").alias("campaign_id"),
              F.col("properties.channel_hint").alias("channel_hint"),
          )
          .where(F.col("anonymous_id").isNotNull()))

    # dedupe on messageId — same rule as stg_segment__events
    w_dedupe = Window.partitionBy("message_id").orderBy("event_ts")
    ev = (ev.withColumn("_rn", F.row_number().over(w_dedupe))
            .where(F.col("_rn") == 1).drop("_rn"))

    # UTM normalisation — must match macros/cross_db.sql clean_utm() exactly.
    # Same principled ladder: strip -> reverse leetspeak -> repair ln/in -> map.
    # analysis/06_parity_check.py fails the build if these two drift apart.
    residual_map = F.create_map([F.lit(x) for pair in [
        ("gogle", "google"), ("inkedin", "linkedin"),
    ] for x in pair])

    def clean(col):
        base = F.lower(F.regexp_replace(F.trim(F.col(col)), "_+$", ""))
        base = F.regexp_replace(base, "3", "e")
        base = F.regexp_replace(base, "1", "i")
        base = F.regexp_replace(base, "0", "o")
        base = F.regexp_replace(base, "ln", "in")
        return F.coalesce(residual_map[base], base)

    ev = (ev.withColumn("utm_source", clean("utm_source_raw"))
            .withColumn("utm_medium", clean("utm_medium_raw")))

    # sessionization: new session when the gap exceeds the timeout
    w_user = Window.partitionBy("anonymous_id").orderBy("event_ts")
    ev = (ev
          .withColumn("prev_ts", F.lag("event_ts").over(w_user))
          .withColumn("gap_min",
                      (F.unix_timestamp("event_ts") - F.unix_timestamp("prev_ts")) / 60.0)
          .withColumn("is_new_session",
                      F.when(F.col("prev_ts").isNull() | (F.col("gap_min") > timeout_minutes), 1)
                       .otherwise(0))
          .withColumn("session_seq",
                      F.sum("is_new_session").over(
                          w_user.rowsBetween(Window.unboundedPreceding, Window.currentRow))))

    sessions = (ev.groupBy("anonymous_id", "session_seq").agg(
        F.min("event_ts").alias("session_start_ts"),
        F.max("event_ts").alias("session_end_ts"),
        F.count(F.when(F.col("event_type") == "page", 1)).alias("pageview_count"),
        F.count(F.when(F.col("event_type") == "identify", 1)).alias("identify_count"),
        F.max("user_id").alias("resolved_user_id"),
        F.min("utm_source").alias("utm_source"),
        F.min("utm_medium").alias("utm_medium"),
        F.min("utm_campaign_name").alias("utm_campaign_name"),
        F.min("campaign_id").alias("campaign_id"),
        F.min("channel_hint").alias("channel_hint"),
        F.min("device_type").alias("device_type"),
        F.max(F.when(F.lower(F.col("user_agent")).rlike("crawler|bot"), True)
               .otherwise(False)).alias("has_bot_user_agent"),
    ))

    sessions = (sessions
        .withColumn("session_id",
                    F.sha2(F.concat_ws("||", "anonymous_id",
                                       F.col("session_seq").cast("string")), 256))
        .withColumn("session_duration_sec",
                    F.unix_timestamp("session_end_ts") - F.unix_timestamp("session_start_ts"))
        .withColumn("is_bot_session",
                    F.col("has_bot_user_agent") | (F.col("pageview_count") >= bot_threshold))
        .withColumn("session_date", F.to_date("session_start_ts")))

    return sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="raw/segment_events/*.jsonl")
    ap.add_argument("--output", default="spark/output/sessions")
    ap.add_argument("--timeout-minutes", type=int, default=30)
    ap.add_argument("--bot-threshold", type=int, default=25)
    a = ap.parse_args()

    spark = (SparkSession.builder
             .appName("mkt-intel-sessionize")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.driver.memory", "2g")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    s = build(spark, a.input, a.timeout_minutes, a.bot_threshold)
    s.write.mode("overwrite").parquet(a.output)

    print(f"Wrote {s.count():,} sessions to {a.output}")
    print("Bot sessions:", s.where(F.col("is_bot_session")).count())
    s.groupBy("utm_source").count().orderBy(F.desc("count")).show(20, truncate=False)
    spark.stop()


if __name__ == "__main__":
    main()
