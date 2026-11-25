"""孤立文件清单与清理处置测试：覆盖筛选、引用证据、两种清理口径和并发恢复。"""
from __future__ import annotations

import sys

sys.path.insert(0, '.')

import pytest

from app.services.orphan_file import (
    MODE_BATCH,
    MODE_SAFE,
    STATUS_PENDING,
    STATUS_PROTECTED,
    STATUS_RELEASED,
    STATUS_SUSPECT,
    orphan_files,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    orphan_files.reset_demo()


def _file(file_id: int) -> dict:
    detail = orphan_files.get_detail(file_id)
    assert detail is not None
    return detail


def _status(file_id: int) -> str:
    return str(_file(file_id)["status"])


def test_seed_lists_production_and_test_same_name_files() -> None:
    items, total = orphan_files.list_entries()
    assert total == 4
    pairs = {(item["目录类型"], item["文件名"]) for item in items}
    assert ("生产目录", "f7.parquet") in pairs
    assert ("生产目录", "f8.parquet") in pairs
    assert ("测试目录", "f7.parquet") in pairs
    # 测试目录的 f7 已单独补发引用，不能沿用生产目录结论。
    test_f7 = next(
        item for item in items
        if item["目录类型"] == "测试目录" and item["文件名"] == "f7.parquet"
    )
    assert test_f7["status"] == STATUS_PROTECTED


def test_filter_by_directory_table_and_version() -> None:
    prod, total = orphan_files.list_entries(directory_type="生产目录")
    assert total == 2
    assert all(item["目录类型"] == "生产目录" for item in prod)

    by_table, table_total = orphan_files.list_entries(table="orders", object_version="v12")
    assert table_total == 4

    missing, missing_total = orphan_files.list_entries(object_version="v99")
    assert missing_total == 0 and missing == []


def test_missing_evidence_is_reported_per_file() -> None:
    row = _file(1)
    assert row["releasable"] is True
    labels = {item["key"] for item in row["missing_evidence"]}
    assert labels == {"commit_log", "snapshot_manifest", "catalog_entry"}
    assert "Delta 提交日志" in row["missing_evidence_text"]


def test_restore_reference_fills_catalog_evidence_only() -> None:
    entry, message = orphan_files.restore_reference(
        1, source="生产目录清单同步", evidence="prod/orders 目录清单包含 f7.parquet@v12")
    assert entry is not None and "已恢复引用" in message
    row = _file(1)
    assert row["status"] == STATUS_PROTECTED
    checks = {item["key"]: item["present"] for item in row["checks"]}
    assert checks["catalog_entry"] is True
    assert checks["commit_log"] is False
    assert row["reference_source"] == "生产目录清单同步"
    assert row["reference_history"][-1]["action"] == "生产目录清单同步"


def test_safe_subset_releases_only_unreferenced_file() -> None:
    orphan_files.restore_reference(
        1, source="生产目录清单同步", evidence="prod/orders 目录清单包含 f7.parquet@v12")
    result = orphan_files.submit_selection([1, 2], mode=MODE_SAFE, selection_id="SEL-T1")
    assert result["ok"] is True
    selection = result["selection"]
    assert selection["scope"] == "按文件安全子集"
    assert selection["status"] == "部分释放"
    assert selection["released_file_ids"] == [2]
    assert _status(1) == STATUS_PROTECTED
    assert _status(2) == STATUS_RELEASED
    # 处置台账按文件写入，并带上本次采用的范围。
    assert {(item["file_id"], item["result"], item["scope"]) for item in result["ledger"]} == {
        (1, STATUS_PROTECTED, "按文件安全子集"),
        (2, STATUS_RELEASED, "按文件安全子集"),
    }


def test_whole_batch_freezes_then_reconfirm_releases() -> None:
    orphan_files.submit_selection(
        [1, 2], mode=MODE_BATCH, selection_id="SEL-T2", execute=False)
    orphan_files.restore_reference(
        1, source="生产目录清单同步", evidence="prod/orders 目录清单包含 f7.parquet@v12")

    result = orphan_files.execute_selection("SEL-T2")
    selection = result["selection"]
    assert selection["status"] == "已冻结"
    assert selection["scope"] == "整批重新确认"
    assert "生产目录/f7.parquet" in selection["frozen_reason"]
    assert selection["released_count"] == 0
    assert _status(1) == STATUS_PROTECTED
    assert _status(2) == STATUS_PENDING

    result = orphan_files.reconfirm_selection("SEL-T2")
    selection = result["selection"]
    assert selection["scope"] == "整批重新确认"
    assert selection["status"] == "部分释放"
    assert selection["released_count"] == 1
    assert _status(1) == STATUS_PROTECTED
    assert _status(2) == STATUS_RELEASED
    assert selection["pending_file_ids"] == []

    again = orphan_files.reconfirm_selection("SEL-T2")
    assert again["released_count"] == 1


def test_duplicate_submission_of_same_selection_is_idempotent() -> None:
    first = orphan_files.submit_selection([2], mode=MODE_SAFE, selection_id="SEL-T3")
    assert first["released_count"] == 1
    second = orphan_files.submit_selection([2], mode=MODE_SAFE, selection_id="SEL-T3")
    assert second["released_count"] == 1
    assert "不重复计数" in second["message"]
    assert orphan_files.release_count("SEL-T3")["release_count"] == 1


def test_resume_after_reference_change_only_touches_unreferenced() -> None:
    orphan_files.submit_selection(
        [1, 2], mode=MODE_SAFE, selection_id="SEL-T4", execute=False)
    orphan_files.restore_reference(1, source="目录补发", evidence="prod 目录新增引用")
    result = orphan_files.resume_selection("SEL-T4")
    assert result["selection"]["released_file_ids"] == [2]
    assert _status(1) == STATUS_PROTECTED
    assert _status(2) == STATUS_RELEASED


def test_interrupt_keeps_unprocessed_files_readable() -> None:
    orphan_files.submit_selection(
        [1, 2], mode=MODE_SAFE, selection_id="SEL-T5", execute=False)
    result = orphan_files.interrupt_selection("SEL-T5", after=1)
    assert result["selection"]["status"] == "已中断"
    # 未处理的文件仍可读，等待继续，而不是被当作已释放。
    assert _file(1)["status"] == STATUS_RELEASED
    assert _file(2)["status"] == STATUS_PENDING
    assert orphan_files.get_entry(2)["released_at"] is None
    resumed = orphan_files.resume_selection("SEL-T5")
    assert resumed["released_count"] == 2


def test_completed_selection_cannot_be_interrupted() -> None:
    orphan_files.submit_selection([2], mode=MODE_SAFE, selection_id="SEL-T6")
    result = orphan_files.interrupt_selection("SEL-T6")
    assert result["ok"] is False
    assert _status(2) == STATUS_RELEASED


def test_summary_tracks_statuses_and_selections() -> None:
    summary = orphan_files.summary()
    assert summary["total"] == 4
    assert summary["suspect"] == 2
    assert summary["protected"] == 1
    assert summary["released"] == 1
    orphan_files.submit_selection([2], mode=MODE_SAFE, selection_id="SEL-T7")
    summary = orphan_files.summary()
    assert summary["released"] == 2
    assert summary["selection_count"] == 1
    assert summary["ledger_count"] == 1


def test_unknown_selection_and_unknown_file() -> None:
    assert orphan_files.execute_selection("SEL-NONE")["ok"] is False
    assert orphan_files.reconfirm_selection("SEL-NONE")["ok"] is False
    assert orphan_files.resume_selection("SEL-NONE")["ok"] is False
    assert orphan_files.get_detail(999) is None
    result = orphan_files.submit_selection([999], mode=MODE_SAFE)
    assert result["ok"] is False


def test_orphan_rows_stay_out_of_business_modules() -> None:
    from app.store import store

    assert "orphan_file" not in store.module_names()
    assert "orphan_file" in store.aux_names()


def test_history_cleanup_uses_orphan_list_and_writes_ledger() -> None:
    from app.services import service_for

    vacuum = service_for("vacuum_job")
    assert vacuum is not None
    preview = vacuum.domain_clean_history(1)
    assert preview["ok"] is True
    assert preview["table"] == "orders"
    assert preview["files_cleaned"] == 2
    assert {item["文件名"] for item in preview["candidate_files"]} == {"f7.parquet", "f8.parquet"}
    assert preview["reclaimed_bytes"] == 123 * 1024 * 1024

    result = vacuum.domain_apply_orphan_cleanup(1, mode=MODE_SAFE)
    assert result["ok"] is True
    assert result["selection_id"].startswith("VAC-1-")
    assert result["released_count"] == 2
    assert len(result["ledger"]) == 2
    assert orphan_files.summary()["ledger_count"] == 2


def test_history_cleanup_safe_subset_protects_restored_reference() -> None:
    from app.services import service_for

    vacuum = service_for("vacuum_job")
    orphan_files.restore_reference(
        1, source="生产目录清单同步", evidence="prod/orders 目录清单包含 f7.parquet@v12")
    result = vacuum.domain_apply_orphan_cleanup(1, mode=MODE_SAFE)
    assert result["released_count"] == 1
    assert _status(1) == STATUS_PROTECTED
    assert _status(2) == STATUS_RELEASED


def test_audit_snapshot_uses_orphan_list() -> None:
    from app.services import service_for

    audit = service_for("lake_audit")
    assert audit is not None
    report = audit.domain_run_audit(1)
    assert report["ok"] is True
    assert report["orphan_files"] == 4
    assert report["orphan_suspect"] == 2
    snapshot = audit.domain_audit_orphans()
    assert snapshot["ok"] is True
    assert snapshot["summary"]["total"] == 4
    assert len(snapshot["files"]) == 4
