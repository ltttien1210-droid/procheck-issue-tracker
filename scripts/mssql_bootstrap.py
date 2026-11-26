"""Wait for the SQL Server development container and create the app database."""

import os
import sys
import time
from contextlib import closing

import pyodbc

password = os.environ["MSSQL_SA_PASSWORD"]
server = os.getenv("PROCHECK_MSSQL_SERVER", "db,1433")
connection = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={server};UID=sa;PWD={{{password.replace('}', '}}')}}};"
    "Encrypt=yes;TrustServerCertificate=yes;"
)


def main():
    os.environ["MSSQL_ODBC_CONNECTION"] = connection + "DATABASE=ProCheck;"
    for _ in range(60):
        try:
            with closing(pyodbc.connect(connection + "DATABASE=master;", autocommit=True, timeout=2)) as db:
                db.execute("IF DB_ID(N'ProCheck') IS NULL CREATE DATABASE [ProCheck]")
            break
        except pyodbc.Error:
            time.sleep(2)
    else:
        raise SystemExit("SQL Server did not become ready. Check the service logs and password.")

    from procheck import create_app
    from procheck.migration import upgrade_database

    app = create_app()
    engine = app.extensions["procheck_engine"]
    upgrade_database(engine)
    engine.dispose()

    if len(sys.argv) > 1:
        os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
