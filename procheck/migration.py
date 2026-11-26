from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def upgrade_database(engine):
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parent / "migrations").replace("%", "%%")
    )
    with engine.begin() as connection:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" not in tables:
            baseline = {"accounts", "issues", "issue_events"}
            if baseline <= tables:
                revision = "0002" if "issue_verifications" in tables else "0001"
                command.stamp(config, revision)
            elif baseline & tables or "issue_verifications" in tables:
                raise RuntimeError("Cơ sở dữ liệu cũ thiếu bảng. Hãy khôi phục bản sao lưu.")
        command.upgrade(config, "head")
