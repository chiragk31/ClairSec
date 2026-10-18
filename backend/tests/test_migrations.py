"""
Unit tests for schema migrations and index assertions (DATA_MODEL §1, §6).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.database.indexes import ensure_indexes
from app.database.migrations import v001_initial
from app.database.migrations.runner import run_migrations
from app.database.models import ProjectRecord, IsolationStatus


class TestDatabaseIndexes:
    @pytest.mark.asyncio
    async def test_ensure_indexes_creates_and_asserts(self):
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_col.create_indexes = AsyncMock(return_value=["idx_projects_id_unique", "idx_projects_isolation_status"])
        mock_col.index_information = AsyncMock(return_value={
            "_id_": {"key": [("_id", 1)]},
            "idx_projects_id_unique": {"key": [("id", 1)], "unique": True},
            "idx_projects_isolation_status": {"key": [("isolation_status", 1)]},
            "idx_jobs_id_unique": {"key": [("id", 1)], "unique": True},
            "idx_jobs_status": {"key": [("status", 1)]},
        })
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        await ensure_indexes(mock_db)
        assert mock_col.create_indexes.await_count == 2
        assert mock_col.index_information.await_count == 2

    @pytest.mark.asyncio
    async def test_ensure_indexes_raises_if_index_missing(self):
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_col.create_indexes = AsyncMock(return_value=["idx_projects_id_unique"])
        # Missing idx_projects_isolation_status
        mock_col.index_information = AsyncMock(return_value={
            "_id_": {"key": [("_id", 1)]},
            "idx_projects_id_unique": {"key": [("id", 1)], "unique": True},
        })
        mock_db.__getitem__ = MagicMock(return_value=mock_col)

        with pytest.raises(AssertionError, match="idx_projects_isolation_status"):
            await ensure_indexes(mock_db)


class TestSchemaMigrations:
    @pytest.mark.asyncio
    async def test_run_migrations_applies_v001_when_unapplied(self):
        mock_db = MagicMock()
        mock_migrations_col = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_migrations_col.find = MagicMock(return_value=mock_cursor)
        mock_migrations_col.insert_one = AsyncMock()

        mock_projects_col = MagicMock()
        mock_update_res = MagicMock()
        mock_update_res.modified_count = 2
        mock_projects_col.update_many = AsyncMock(return_value=mock_update_res)

        def get_col(name):
            if name == "schema_migrations":
                return mock_migrations_col
            elif name == "projects":
                return mock_projects_col
            mock_col = MagicMock()
            mock_col.create_index = AsyncMock()
            mock_col.update_many = AsyncMock()
            return mock_col

        mock_db.__getitem__ = MagicMock(side_effect=get_col)

        await run_migrations(mock_db)

        # Assert v001 upgrade ran and updated records
        import unittest.mock
        assert unittest.mock.call(
            {"schema_version": {"$exists": False}},
            {"$set": {"schema_version": 1}},
        ) in mock_projects_col.update_many.call_args_list
        # Assert recorded in schema_migrations
        assert mock_migrations_col.insert_one.await_count >= 1
        recorded_names = [call[0][0]["name"] for call in mock_migrations_col.insert_one.call_args_list]
        assert v001_initial.MIGRATION_ID in recorded_names

    @pytest.mark.asyncio
    async def test_run_migrations_skips_already_applied(self):
        from app.database.migrations import runner
        mock_db = MagicMock()
        mock_migrations_col = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[{"name": m[0]} for m in runner.MIGRATIONS])
        mock_migrations_col.find = MagicMock(return_value=mock_cursor)
        mock_migrations_col.insert_one = AsyncMock()

        mock_projects_col = MagicMock()
        mock_projects_col.update_many = AsyncMock()

        def get_col(name):
            if name == "schema_migrations":
                return mock_migrations_col
            elif name == "projects":
                return mock_projects_col
            mock_col = MagicMock()
            mock_col.create_index = AsyncMock()
            mock_col.update_many = AsyncMock()
            return mock_col

        mock_db.__getitem__ = MagicMock(side_effect=get_col)

        await run_migrations(mock_db)

        # Assert all upgrades were skipped
        mock_projects_col.update_many.assert_not_awaited()
        mock_migrations_col.insert_one.assert_not_awaited()


class TestProjectModelSchemaVersion:
    def test_project_record_default_schema_version(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        record = ProjectRecord(
            id="f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
            name="test",
            source_path="/tmp/source",
            scan_workspace_path="/tmp/workspace",
            created_at=now,
            isolation_status=IsolationStatus.PENDING,
        )
        assert record.schema_version == 1
