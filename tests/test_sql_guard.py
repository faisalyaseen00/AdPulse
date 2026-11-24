import pytest

from adpulse.agent.prompts import semantic
from adpulse.agent.sql_guard import SQLRejected, check_sql

ALLOWED = {"dim_ads", "fct_ad_daily", "dim_customers", "fct_orders", "mart_ad_monthly"}


def test_example_sql_passes():
    sql = semantic()["examples"][0]["sql"]
    res = check_sql(sql, ALLOWED)
    assert res.tables == {"dim_customers", "fct_ad_daily", "dim_ads"}


@pytest.mark.parametrize("sql", [
    "DROP TABLE dim_ads",
    "SELECT 1; DROP TABLE dim_ads",
    "INSERT INTO dim_ads SELECT * FROM dim_ads",
    "SELECT * FROM system.users",
    "SELECT * FROM app_recommendations",
    "SELECT * FROM url('http://evil.example/x.csv', CSV)",
    "SELECT * FROM numbers(1000000000)",
    "SELECT * FROM other_db.dim_ads",
    "SELECT 1",
    "ALTER TABLE dim_ads DELETE WHERE 1",
    "SELECT * FROM dim_ads INTO OUTFILE '/tmp/x'",
])
def test_rejects_unsafe(sql):
    with pytest.raises(SQLRejected):
        check_sql(sql, ALLOWED)


def test_keywords_inside_strings_are_fine():
    check_sql("SELECT ad_name FROM dim_ads WHERE ad_name = 'drop table; insert'", ALLOWED)


def test_cte_names_not_treated_as_tables():
    check_sql("WITH x AS (SELECT ad_id FROM dim_ads) SELECT * FROM x", ALLOWED)
