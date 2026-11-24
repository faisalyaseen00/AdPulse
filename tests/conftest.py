import pytest

from adpulse import warehouse


@pytest.fixture(scope="session")
def db():
    if not warehouse.health().ok:
        pytest.skip("ClickHouse not running")
    try:
        n = warehouse.query_df("SELECT count() AS n FROM dim_customers").iloc[0]["n"]
    except Exception:
        pytest.skip("warehouse not loaded - run `adpulse setup`")
    if not n:
        pytest.skip("warehouse empty - run `adpulse setup`")
    warehouse.init_db()
    return True


@pytest.fixture(scope="session", autouse=True)
def _clean_test_rows():
    """Keep the real question log free of rows written by scripted-LLM tests."""
    yield
    if warehouse.health().ok:
        try:
            warehouse.command("ALTER TABLE app_questions DELETE WHERE provider = 'scripted' "
                              "SETTINGS mutations_sync = 1")
        except Exception:
            pass
