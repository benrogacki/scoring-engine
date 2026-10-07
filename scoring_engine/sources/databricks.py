"""Read ledger data from, and write scoring results to, Databricks.

Two ways in:

* From anywhere (laptop, CI, a VM): the Databricks SQL connector against a SQL
  warehouse. Install with ``pip install "scoring-engine[databricks]"`` and set

      DATABRICKS_SERVER_HOSTNAME   e.g. adb-1234567890123456.7.azuredatabricks.net
      DATABRICKS_HTTP_PATH         e.g. /sql/1.0/warehouses/abc123def456
      DATABRICKS_TOKEN             personal access token or service principal token

* Inside Databricks (notebook or job): pass the ``spark`` session instead; see
  databricks/credit_scoring_job.py. No connector or token needed.

Queries are templates with ``{invoices_table}``, ``{customers_table}`` and
``{lookback_months}`` placeholders; the defaults read curated views whose
columns match the engine's canonical names (see docs/integrations.md).
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .netsuite import QUERY_DIR

ENV_VARS = ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN")
# Text columns in the scorecard/worklist; everything else is numeric. Fixed so the
# table schema doesn't drift when a column happens to be empty in a given run.
TEXT_COLUMNS = {
    "customer_name", "industry", "grade", "grade_label", "limit_action", "collection_tier",
    "risk_drivers", "tier", "action",
    # run log
    "run_at", "source", "fingerprint", "data_health", "backtest_verdict", "previous_as_of",
}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){0,2}$")


class DatabricksError(RuntimeError):
    pass


def check_table_name(name: str) -> str:
    """Allow only catalog.schema.table identifiers so names can't inject SQL."""
    if not _IDENT.match(name or ""):
        raise DatabricksError(f"Invalid table name: {name!r} (expected catalog.schema.table)")
    return name


def connect(environ: Optional[Dict[str, str]] = None):
    env = os.environ if environ is None else environ
    missing = [v for v in ENV_VARS if not env.get(v)]
    if missing:
        raise DatabricksError("Missing Databricks settings: set " + ", ".join(missing))
    try:
        from databricks import sql  # type: ignore
    except ImportError:
        raise DatabricksError('Databricks SQL connector not installed: pip install "scoring-engine[databricks]"') from None
    return sql.connect(
        server_hostname=env["DATABRICKS_SERVER_HOSTNAME"],
        http_path=env["DATABRICKS_HTTP_PATH"],
        access_token=env["DATABRICKS_TOKEN"],
    )


def render_query(path: Optional[str], default: str, **params: Any) -> str:
    sql = (Path(path) if path else QUERY_DIR / default).read_text(encoding="utf-8")
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", str(value))
    return sql.strip().rstrip(";")


def query_rows(conn, sql: str) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def fetch(
    conn,
    invoices_table: Optional[str] = None,
    customers_table: Optional[str] = None,
    lookback_months: int = 15,
    invoices_query: Optional[str] = None,
    customers_query: Optional[str] = None,
    spark=None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return invoice and customer rows, via a SQL connection or a Spark session."""
    if not invoices_query and not invoices_table:
        raise DatabricksError("Provide an invoices table (--invoices-table) or query file (--invoices-query)")
    params = {"lookback_months": int(lookback_months)}
    if invoices_table:
        params["invoices_table"] = check_table_name(invoices_table)
    if customers_table:
        params["customers_table"] = check_table_name(customers_table)
    inv_sql = render_query(invoices_query, "databricks_invoices.sql", **params)
    cust_sql = None
    if customers_query or customers_table:
        cust_sql = render_query(customers_query, "databricks_customers.sql", **params)

    def run(sql: str) -> List[Dict[str, Any]]:
        if spark is not None:
            return [r.asDict() for r in spark.sql(sql).collect()]
        return query_rows(conn, sql)

    return {"invoices": run(inv_sql), "customers": run(cust_sql) if cust_sql else []}


# ---------------------------------------------------------------- write-back

def column_types(rows: Sequence[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """STRING for IDs and known text columns; DOUBLE where every value is numeric."""
    if not rows:
        return []
    types = []
    for col in rows[0].keys():
        if col.endswith("_id") or col in TEXT_COLUMNS:
            types.append((col, "STRING"))
            continue
        values = [r[col] for r in rows if r[col] not in ("", None)]
        numeric = True
        for v in values:
            try:
                float(v)
            except (TypeError, ValueError):
                numeric = False
                break
        types.append((col, "DOUBLE" if numeric else "STRING"))
    return types


def typed_rows(rows: Sequence[Dict[str, Any]], types: List[Tuple[str, str]], as_of: date) -> List[tuple]:
    out = []
    for r in rows:
        values = [as_of]
        for col, kind in types:
            v = r[col]
            if v in ("", None):
                values.append(None)
            else:
                values.append(float(v) if kind == "DOUBLE" else str(v))
        out.append(tuple(values))
    return out


def write_table(conn, table: str, rows: Sequence[Dict[str, Any]], as_of: date) -> int:
    """Upsert one scoring run into a Delta table, keyed on as_of.

    The table keeps every run, so month-on-month trends can be charted in
    Databricks SQL or Power BI. Re-running a date replaces that date's rows.
    """
    table = check_table_name(table)
    types = column_types(rows)
    if not types:
        return 0
    ddl = ", ".join(["as_of DATE"] + [f"`{c}` {t}" for c, t in types])
    cols = ", ".join(["as_of"] + [f"`{c}`" for c, _ in types])
    marks = ", ".join(["?"] * (len(types) + 1))
    with conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({ddl}) USING DELTA")
        cur.execute(f"DELETE FROM {table} WHERE as_of = ?", [as_of])
        cur.executemany(f"INSERT INTO {table} ({cols}) VALUES ({marks})", typed_rows(rows, types, as_of))
    return len(rows)


def spark_write_table(spark, table: str, rows: Sequence[Dict[str, Any]], as_of: date) -> int:
    """Same as ``write_table`` but through Spark, for notebooks and jobs."""
    table = check_table_name(table)
    types = column_types(rows)
    if not types:
        return 0
    schema = ", ".join(["as_of DATE"] + [f"`{c}` {t}" for c, t in types])
    df = spark.createDataFrame(typed_rows(rows, types, as_of), schema=schema)
    if spark.catalog.tableExists(table):
        spark.sql(f"DELETE FROM {table} WHERE as_of = DATE'{as_of.isoformat()}'")
        df.write.mode("append").option("mergeSchema", "true").saveAsTable(table)
    else:
        df.write.saveAsTable(table)
    return len(rows)


def spark_previous_scorecard(spark, table: str, as_of: date):
    """(as_of, scorecard rows by customer) of the latest earlier run in ``table``, or (None, None)."""
    table = check_table_name(table)
    if not spark.catalog.tableExists(table):
        return None, None
    row = spark.sql(f"SELECT max(as_of) AS d FROM {table} WHERE as_of < DATE'{as_of.isoformat()}'").collect()[0]
    prev = row["d"]
    if prev is None:
        return None, None
    prev = prev if isinstance(prev, date) else date.fromisoformat(str(prev))
    rows = spark.sql(f"SELECT * FROM {table} WHERE as_of = DATE'{prev.isoformat()}'").collect()
    card = {}
    for r in rows:
        d = {k: ("" if v is None else _text(v)) for k, v in r.asDict().items() if k != "as_of"}
        card[d["customer_id"]] = d
    return prev.isoformat(), card


def _text(v: Any) -> str:
    # Whole numbers stored as DOUBLE come back as 12.0; keep them readable.
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
