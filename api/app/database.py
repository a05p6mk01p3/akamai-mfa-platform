from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Any

from .config import Settings


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    """Small synchronous PostgreSQL adapter.

    Connections are intentionally short-lived in change-set 02. Pooling may be added
    later without changing repository contracts.
    """

    def __init__(self, settings: Settings) -> None:
        self.dsn = settings.require_database_url()

    @staticmethod
    def _driver():
        # Lazy import keeps pure unit tests independent from the PostgreSQL driver.
        import psycopg
        from psycopg.rows import dict_row
        return psycopg, dict_row

    @contextmanager
    def connection(self) -> Iterator[Any]:
        psycopg, dict_row = self._driver()
        try:
            conn = psycopg.connect(self.dsn, row_factory=dict_row)
        except psycopg.Error as exc:
            raise DatabaseUnavailable("PostgreSQL indisponível") from exc
        try:
            yield conn
        finally:
            conn.close()

    def ping(self) -> bool:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
                return bool(row and row["ok"] == 1)
