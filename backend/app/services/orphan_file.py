"""孤立数据文件清单与回收处置领域服务。

围绕“疑似孤立文件 → 引用核查 → 清理选择 → 按文件释放 → 审计处置台账”的闭环：

- 清单按目录类型、湖表、对象版本筛选；生产目录和测试目录的同名文件是两条独立记录。
- 每条记录都保留三类引用证据的核查结果，缺哪条证据直接展示，便于回查。
- 清理选择支持两种口径：按文件安全子集只释放仍无引用的文件；整批提交时若有文件
  新增了引用，则整批冻结等待重新确认，避免误删仍可读的数据。
- 释放结果按文件写入湖仓审计处置台账；同一选择并发恢复只计一次释放。
"""
from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.store import store

# 中国标准时间：示例数据的时间戳统一按 +08:00 展示。
CST = timezone(timedelta(hours=8))

FILE_TABLE = "orphan_file"
SELECTION_TABLE = "cleanup_selection"
LEDGER_TABLE = "audit_ledger"

STATUS_SUSPECT = "疑似孤立"
STATUS_PROTECTED = "受保护"
STATUS_PENDING = "待重新确认"
STATUS_RELEASED = "已释放"

MODE_SAFE = "safe_subset"
MODE_BATCH = "whole_batch"

SCOPE_SAFE = "按文件安全子集"
SCOPE_BATCH = "整批重新确认"


def _now() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def _next_id(rows: list[dict[str, Any]], prefix: str) -> str:
    seq = 0
    for row in rows:
        raw = str(row.get("id", ""))
        if raw.startswith(prefix):
            tail = raw.rsplit("-", 1)[-1]
            if tail.isdigit():
                seq = max(seq, int(tail))
    return f"{prefix}-{seq + 1:04d}"


class OrphanFileService:
    """孤立文件清单服务：路由只做参数透传，状态流转全部留在这里。"""

    # 内存仓库在多线程（uvicorn 线程池）下共享，选择和台账的写入需要串行化。
    _lock = threading.RLock()

    # ------------------------------------------------------------------
    # 清单查询
    # ------------------------------------------------------------------

    def _files(self) -> list[dict[str, Any]]:
        return store.aux(FILE_TABLE)

    def _selections(self) -> list[dict[str, Any]]:
        return store.aux(SELECTION_TABLE)

    def _ledger(self) -> list[dict[str, Any]]:
        return store.aux(LEDGER_TABLE)

    def _releasable(self, row: dict[str, Any]) -> bool:
        # 冻结等待重新确认的文件不直接算可释放，必须先走重新确认。
        return (
            not row.get("referenced")
            and row.get("status") not in (STATUS_RELEASED, STATUS_PROTECTED, STATUS_PENDING)
        )

    def _missing_evidence(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        return [check for check in row.get("checks", []) if not check.get("present")]

    def present(self, row: dict[str, Any]) -> dict[str, Any]:
        """把存储行转成清单行：补上缺失证据摘要和是否能释放的判断。"""
        missing = self._missing_evidence(row)
        history = row.get("disposition_history") or []
        last = history[-1] if history else None
        payload = dict(row)
        payload["status"] = row.get("status", STATUS_SUSPECT)
        payload["missing_evidence"] = missing
        payload["missing_evidence_text"] = (
            "、".join(item.get("label", "") for item in missing) if missing else "无（引用齐全）"
        )
        payload["evidence_complete"] = not missing
        payload["releasable"] = self._releasable(row)
        payload["last_disposition"] = last
        payload["上次处置"] = last.get("处置", "—") if last else "—"
        payload["上次处置说明"] = last.get("说明", "—") if last else "—"
        return payload

    def list_entries(
        self,
        *,
        directory_type: str | None = None,
        table: str | None = None,
        object_version: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(self._files())
        if directory_type:
            rows = [row for row in rows if row.get("目录类型") == directory_type]
        if table:
            rows = [row for row in rows if table.casefold() in str(row.get("湖表", "")).casefold()]
        if object_version:
            rows = [row for row in rows if str(row.get("对象版本", "")) == object_version]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if keyword:
            needle = keyword.casefold()
            rows = [
                row for row in rows
                if needle in str(row.get("文件名", "")).casefold()
                or needle in str(row.get("文件路径", "")).casefold()
            ]
        total = len(rows)
        start = (page - 1) * size
        return [self.present(row) for row in rows[start:start + size]], total

    def get_entry(self, file_id: int) -> dict[str, Any] | None:
        for row in self._files():
            if int(row.get("id", 0)) == file_id:
                return row
        return None

    def get_detail(self, file_id: int) -> dict[str, Any] | None:
        row = self.get_entry(file_id)
        return self.present(row) if row else None

    def summary(self, report_id: str | None = None) -> dict[str, Any]:
        rows = [
            row for row in self._files()
            if not report_id or row.get("审计报告") == report_id
        ]
        by_status = {
            status: sum(1 for row in rows if row.get("status") == status)
            for status in (STATUS_SUSPECT, STATUS_PROTECTED, STATUS_PENDING, STATUS_RELEASED)
        }
        selections = [
            item for item in self._selections()
            if not report_id or item.get("report_id") == report_id
        ]
        ledger = [
            item for item in self._ledger()
            if not report_id or item.get("report_id") == report_id
        ]
        return {
            "report_id": report_id,
            "total": len(rows),
            "by_status": by_status,
            "suspect": by_status[STATUS_SUSPECT],
            "protected": by_status[STATUS_PROTECTED],
            "pending_reconfirm": by_status[STATUS_PENDING],
            "released": by_status[STATUS_RELEASED],
            "releasable": sum(1 for row in rows if self._releasable(row)),
            "released_bytes": sum(int(row.get("released_bytes", 0)) for row in rows),
            "selection_count": len(selections),
            "ledger_count": len(ledger),
            "production": sum(1 for row in rows if row.get("目录类型") == "生产目录"),
            "test": sum(1 for row in rows if row.get("目录类型") == "测试目录"),
        }

    def options(self) -> dict[str, list[str]]:
        """筛选下拉项：目录类型、湖表、对象版本都从现有清单里取。"""
        def distinct(field: str) -> list[str]:
            return sorted({str(row.get(field)) for row in self._files() if row.get(field)})
        return {
            "directory_types": distinct("目录类型") or ["生产目录", "测试目录"],
            "tables": distinct("湖表"),
            "object_versions": distinct("对象版本"),
            "statuses": [STATUS_SUSPECT, STATUS_PROTECTED, STATUS_PENDING, STATUS_RELEASED],
        }

    # ------------------------------------------------------------------
    # 引用证据：目录补发引用
    # ------------------------------------------------------------------

    def restore_reference(
        self,
        file_id: int,
        *,
        source: str = "目录补发",
        evidence: str = "",
        note: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        with self._lock:
            row = self.get_entry(file_id)
            if row is None:
                return None, f"孤立文件 {file_id} 不存在"
            if row.get("status") == STATUS_RELEASED:
                return None, "文件已释放，不能再补发引用"

            at = _now()
            detail = evidence or f"{row.get('目录路径')} 目录清单包含 {row.get('文件名')}@{row.get('对象版本')}"
            row["referenced"] = True
            row["reference_restored_at"] = at
            row["reference_source"] = source
            # 只补目录清单这一条证据，其余证据维持原核查结论，方便回查缺哪一条。
            catalog_check = next(
                (item for item in row.get("checks", []) if item.get("key") == "catalog_entry"),
                None,
            )
            if catalog_check is not None:
                catalog_check["present"] = True
                catalog_check["detail"] = detail
            else:
                row.setdefault("checks", []).append({
                    "key": "catalog_entry",
                    "label": "Catalog 目录清单条目",
                    "present": True,
                    "detail": detail,
                })
            row.setdefault("reference_history", []).append({
                "at": at,
                "action": source,
                "source": source,
                "evidence": detail,
                "note": note or "目录新增引用，原清理选择需要重新核查",
            })
            row["status"] = STATUS_PROTECTED
            row["frozen_reason"] = None
            self._dispose(
                row,
                disposition=STATUS_PROTECTED,
                detail=note or f"{source}补发引用，文件转为受保护",
                selection_id=row.get("last_selection_id"),
                report_id=row.get("审计报告"),
                scope="目录补发引用",
            )
            return self.present(row), f"{row.get('文件名')} 已恢复引用并转为受保护"

    # ------------------------------------------------------------------
    # 清理选择
    # ------------------------------------------------------------------

    def _resolve_files(self, file_ids: list[int]) -> tuple[list[dict[str, Any]], list[int]]:
        resolved: list[dict[str, Any]] = []
        missing: list[int] = []
        seen: set[int] = set()
        for raw in file_ids:
            try:
                file_id = int(raw)
            except (TypeError, ValueError):
                missing.append(raw)  # type: ignore[arg-type]
                continue
            if file_id in seen:
                continue
            seen.add(file_id)
            row = self.get_entry(file_id)
            if row is None:
                missing.append(file_id)
            else:
                resolved.append(row)
        return resolved, missing

    def _remaining(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            row for row in files
            if row.get("status") not in (STATUS_RELEASED, STATUS_PROTECTED)
        ]

    def _dispose(
        self,
        row: dict[str, Any],
        *,
        disposition: str,
        detail: str,
        selection_id: str | None,
        report_id: str | None,
        scope: str | None = None,
        released_bytes: int = 0,
    ) -> dict[str, Any] | None:
        """写一条处置台账；同一选择 + 同一文件 + 同一口径只记一次释放。"""
        if selection_id:
            for item in self._ledger():
                if (
                    item.get("selection_id") == selection_id
                    and int(item.get("file_id", 0)) == int(row.get("id", 0))
                    and item.get("result") == disposition
                    and item.get("scope") == scope
                ):
                    return item
        entry = {
            "id": _next_id(self._ledger(), "LEDG"),
            "selection_id": selection_id,
            "file_id": row.get("id"),
            "file_key": f"{row.get('目录路径')}/{row.get('文件名')}",
            "文件名": row.get("文件名"),
            "目录类型": row.get("目录类型"),
            "目录路径": row.get("目录路径"),
            "湖表": row.get("湖表"),
            "对象版本": row.get("对象版本"),
            "report_id": report_id or row.get("审计报告"),
            "scope": scope,
            "result": disposition,
            "released": disposition == STATUS_RELEASED,
            "released_bytes": released_bytes,
            "detail": detail,
            "missing_evidence": [item.get("label") for item in self._missing_evidence(row)],
            "at": _now(),
        }
        self._ledger().append(entry)
        row.setdefault("disposition_history", []).append({
            "at": entry["at"],
            "处置": disposition,
            "说明": detail,
            "selection_id": selection_id,
            "ledger_id": entry["id"],
        })
        return entry

    def _release(self, row: dict[str, Any], *, selection_id: str, scope: str,
                 detail: str) -> dict[str, Any]:
        """按文件写入释放结果；已释放过的文件不再重复计数。"""
        for item in self._ledger():
            if (
                item.get("selection_id") == selection_id
                and int(item.get("file_id", 0)) == int(row.get("id", 0))
                and item.get("result") == STATUS_RELEASED
            ):
                return item
        size_mb = int(row.get("文件大小", 0) or 0)
        released_bytes = size_mb * 1024 * 1024
        row["status"] = STATUS_RELEASED
        row["released_at"] = _now()
        row["released_bytes"] = released_bytes
        row["release_selection_id"] = selection_id
        row["frozen_reason"] = None
        entry = self._dispose(
            row,
            disposition=STATUS_RELEASED,
            detail=detail,
            selection_id=selection_id,
            report_id=row.get("审计报告"),
            scope=scope,
            released_bytes=released_bytes,
        )
        assert entry is not None
        return entry

    def _protect(self, row: dict[str, Any], *, selection_id: str, scope: str,
                 detail: str) -> dict[str, Any] | None:
        row["status"] = STATUS_PROTECTED
        row["frozen_reason"] = None
        return self._dispose(
            row,
            disposition=STATUS_PROTECTED,
            detail=detail,
            selection_id=selection_id,
            report_id=row.get("审计报告"),
            scope=scope,
        )

    def _pending(self, row: dict[str, Any], *, selection_id: str, scope: str,
                 detail: str) -> dict[str, Any] | None:
        row["status"] = STATUS_PENDING
        row["last_selection_id"] = selection_id
        return self._dispose(
            row,
            disposition=STATUS_PENDING,
            detail=detail,
            selection_id=selection_id,
            report_id=row.get("审计报告"),
            scope=scope,
        )

    def _build_selection(
        self,
        *,
        selection_id: str,
        mode: str,
        files: list[dict[str, Any]],
        scope: str,
        note: str = "",
    ) -> dict[str, Any]:
        selection = {
            "id": selection_id,
            "selection_id": selection_id,
            "created_at": _now(),
            "mode": mode,
            "mode_label": SCOPE_SAFE if mode == MODE_SAFE else SCOPE_BATCH,
            "scope": scope,
            "note": note,
            "report_id": files[0].get("审计报告") if files else None,
            "file_ids": [row.get("id") for row in files],
            "file_keys": [f"{row.get('目录路径')}/{row.get('文件名')}" for row in files],
            "files": [
                {
                    "id": row.get("id"),
                    "文件名": row.get("文件名"),
                    "目录类型": row.get("目录类型"),
                    "目录路径": row.get("目录路径"),
                    "湖表": row.get("湖表"),
                    "对象版本": row.get("对象版本"),
                }
                for row in files
            ],
            "status": "进行中",
            "released_file_ids": [],
            "protected_file_ids": [],
            "pending_file_ids": [],
            "released_count": 0,
            "released_bytes": 0,
            "ledger_ids": [],
            "events": [],
            "frozen_reason": None,
            "reconfirmed_at": None,
            "interrupted": False,
        }
        self._selections().append(selection)
        return selection

    def _log(self, selection: dict[str, Any], action: str, detail: str) -> None:
        selection.setdefault("events", []).append({
            "at": _now(), "action": action, "detail": detail,
        })

    def _refresh_totals(self, selection: dict[str, Any]) -> None:
        released = [
            item for item in self._ledger()
            if item.get("selection_id") == selection["id"] and item.get("result") == STATUS_RELEASED
        ]
        # 去重：同一文件只计一次释放，抵御并发重复写入。
        unique: dict[int, dict[str, Any]] = {}
        for item in released:
            unique.setdefault(int(item.get("file_id", 0)), item)
        selection["released_file_ids"] = sorted(unique)
        selection["released_count"] = len(unique)
        selection["released_bytes"] = sum(int(item.get("released_bytes", 0)) for item in unique.values())
        # 受保护/待确认按文件“当前状态”统计，避免重新确认后仍显示历史待核记录。
        protected_ids: list[int] = []
        pending_ids: list[int] = []
        for file_id in selection.get("file_ids", []):
            row = self.get_entry(int(file_id))
            if row is None:
                continue
            if row.get("status") == STATUS_PROTECTED:
                protected_ids.append(int(file_id))
            elif row.get("status") == STATUS_PENDING:
                pending_ids.append(int(file_id))
        selection["protected_file_ids"] = sorted(protected_ids)
        selection["pending_file_ids"] = sorted(pending_ids)

    def submit_selection(
        self,
        file_ids: list[int],
        *,
        mode: str = MODE_SAFE,
        note: str = "",
        selection_id: str | None = None,
        execute: bool = True,
    ) -> dict[str, Any]:
        if mode not in (MODE_SAFE, MODE_BATCH):
            return {"ok": False, "message": f"未知清理口径：{mode}"}
        with self._lock:
            files, missing = self._resolve_files(file_ids)
            if missing:
                return {"ok": False, "message": f"以下孤立文件不存在：{missing}"}
            if not files:
                return {"ok": False, "message": "请先选择需要清理的孤立文件"}
            sid = selection_id or _next_id(self._selections(), "SEL")
            existing = next((s for s in self._selections() if s.get("id") == sid), None)
            if existing is not None:
                return self._selection_result(existing, reused=True)

            scope = SCOPE_SAFE if mode == MODE_SAFE else SCOPE_BATCH
            selection = self._build_selection(
                selection_id=sid, mode=mode, files=files, scope=scope, note=note)

            if not execute:
                # 只登记回收范围，等人工执行；此时不动任何文件状态。
                selection["status"] = "待执行"
                self._log(selection, "登记清理范围", f"{scope}：等待执行清理")
                return self._selection_result(selection)

            self._run_selection(selection, files, action="提交清理")
            return self._selection_result(selection)

    def _run_selection(self, selection: dict[str, Any], files: list[dict[str, Any]], *,
                       action: str) -> None:
        """执行前再核一次引用：整批口径遇到新增引用就整批冻结，其余按文件处理。"""
        sid = selection["id"]
        conflicted = [
            row for row in files
            if row.get("referenced") and row.get("status") != STATUS_RELEASED
        ]
        if selection.get("mode") == MODE_BATCH and conflicted:
            reason = f"{action}前目录新增引用：" + "、".join(
                f"{row.get('目录类型')}/{row.get('文件名')}" for row in conflicted)
            selection["status"] = "已冻结"
            selection["scope"] = SCOPE_BATCH
            selection["frozen_reason"] = reason
            self._log(selection, "整批冻结", reason)
            for row in files:
                if row.get("status") == STATUS_RELEASED:
                    # 已释放的文件不因冻结回退状态，也不重复计数。
                    continue
                if row.get("referenced"):
                    self._protect(
                        row, selection_id=sid, scope=SCOPE_BATCH,
                        detail=f"{reason}；该文件有新增引用，保持可读",
                    )
                else:
                    self._pending(
                        row,
                        selection_id=sid,
                        scope=SCOPE_BATCH,
                        detail=f"整批等待重新确认：{reason}",
                    )
            self._refresh_totals(selection)
            return

        self._execute(selection, files, scope=selection.get("scope") or SCOPE_SAFE, action=action)

    def execute_selection(self, selection_id: str) -> dict[str, Any]:
        """执行已登记的回收范围；整批口径有新增引用时冻结等待重新确认。"""
        with self._lock:
            selection = self.get_selection(selection_id)
            if selection is None:
                return {"ok": False, "message": f"清理选择 {selection_id} 不存在"}
            if selection.get("status") != "待执行":
                return self._selection_result(selection)
            files, _ = self._resolve_files([int(i) for i in selection.get("file_ids", [])])
            self._run_selection(selection, files, action="执行清理")
            return self._selection_result(selection)

    def _execute(self, selection: dict[str, Any], files: list[dict[str, Any]], *,
                 scope: str, action: str) -> None:
        """按文件执行释放：释放前再核一次引用，仍可读的文件一律保护。"""
        released = 0
        protected = 0
        for row in files:
            if row.get("status") == STATUS_RELEASED:
                # 同一选择并发恢复：已释放的文件只计一次。
                continue
            if row.get("status") == STATUS_PENDING and action == "提交清理":
                # 属于冻结批次、尚未重新确认的文件，不能被一个新的安全子集悄悄释放。
                self._protect(
                    row, selection_id=selection["id"], scope=scope,
                    detail="该文件在冻结批次中，等待整批重新确认",
                )
                protected += 1
                continue
            if row.get("referenced"):
                self._protect(
                    row, selection_id=selection["id"], scope=scope,
                    detail=f"{action}复核发现目录已新增引用，文件保持可读",
                )
                protected += 1
                continue
            self._release(
                row, selection_id=selection["id"], scope=scope,
                detail=f"{action}：{scope}，释放前复核无任何引用证据",
            )
            released += 1
        selection["status"] = "已完成" if protected == 0 else "部分释放"
        selection["interrupted"] = False
        self._log(
            selection, action,
            f"{scope}：释放 {released} 个文件，保护 {protected} 个仍有引用的文件",
        )
        self._refresh_totals(selection)

    def _selection_result(self, selection: dict[str, Any], *, reused: bool = False) -> dict[str, Any]:
        ledger = [item for item in self._ledger() if item.get("selection_id") == selection["id"]]
        message = {
            "已完成": (
                f"本次采用{selection.get('scope') or '按文件安全子集'}："
                f"{selection.get('released_count', 0)} 个文件已释放"
            ),
            "部分释放": (
                "本次采用整批重新确认：仍无引用的文件已释放，有引用的文件受保护"
                if selection.get("scope") == SCOPE_BATCH
                else "本次采用按文件安全子集：仍无引用的文件已释放，其余文件受保护"
            ),
            "已冻结": "整批清理已冻结，等待重新确认",
            "已中断": "清理已中断，未处理文件保持可读，可继续恢复",
            "待执行": "清理范围已登记，等待执行清理",
        }.get(selection.get("status"), "清理选择已登记")
        if reused:
            message = "该清理选择已存在，返回原处置结果，不重复计数"
        return {
            "ok": True,
            "message": message,
            "selection": selection,
            "ledger": ledger,
            "released_count": selection.get("released_count", 0),
        }

    def list_selections(self, report_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._selections())
        if report_id:
            rows = [row for row in rows if row.get("report_id") == report_id]
        return list(reversed(rows))

    def get_selection(self, selection_id: str) -> dict[str, Any] | None:
        for row in self._selections():
            if row.get("id") == selection_id:
                return row
        return None

    def selection_detail(self, selection_id: str) -> dict[str, Any] | None:
        selection = self.get_selection(selection_id)
        if selection is None:
            return None
        self._refresh_totals(selection)
        ledger = [item for item in self._ledger() if item.get("selection_id") == selection_id]
        files = []
        for file_id in selection.get("file_ids", []):
            row = self.get_entry(int(file_id))
            files.append(self.present(row) if row else {"id": file_id, "status": "已删除"})
        payload = dict(selection)
        payload["ledger"] = ledger
        payload["file_details"] = files
        payload["execution_detail"] = {
            "scope": selection.get("scope"),
            "status": selection.get("status"),
            "released_count": selection.get("released_count", 0),
            "released_bytes": selection.get("released_bytes", 0),
            "protected_count": len(selection.get("protected_file_ids", [])),
            "pending_count": len(selection.get("pending_file_ids", [])),
            "frozen_reason": selection.get("frozen_reason"),
            "reconfirm_required": selection.get("status") in ("已冻结", "已中断"),
        }
        return payload

    def resume_selection(self, selection_id: str) -> dict[str, Any]:
        """目录引用变化后，只处理仍无引用的文件；有引用的文件保持受保护。"""
        with self._lock:
            selection = self.get_selection(selection_id)
            if selection is None:
                return {"ok": False, "message": f"清理选择 {selection_id} 不存在"}
            if selection.get("status") in ("已完成", "部分释放") and not self._remaining(files):
                return {
                    "ok": True,
                    "message": "该选择已处理完毕，重复恢复不重复释放",
                    "selection": selection,
                    "ledger": [i for i in self._ledger() if i.get("selection_id") == selection_id],
                    "released_count": selection.get("released_count", 0),
                }
            files, _ = self._resolve_files([int(i) for i in selection.get("file_ids", [])])
            # 目录引用变化后只用安全子集口径：只处理仍无引用的文件，有引用的一律保护。
            scope = SCOPE_SAFE
            selection["scope"] = scope
            self._execute(selection, files, scope=scope, action="继续处理仍无引用文件")
            return self._selection_result(selection)

    def reconfirm_selection(self, selection_id: str, *, note: str = "") -> dict[str, Any]:
        """整批重新确认：逐个复核引用证据，仍无引用的释放，已有引用的保护。"""
        with self._lock:
            selection = self.get_selection(selection_id)
            if selection is None:
                return {"ok": False, "message": f"清理选择 {selection_id} 不存在"}
            files, _ = self._resolve_files([int(i) for i in selection.get("file_ids", [])])
            if (
                selection.get("status") in ("已完成", "部分释放")
                and selection.get("scope") == SCOPE_BATCH
                and not self._remaining(files)
            ):
                return {
                    "ok": True,
                    "message": "该选择已重新确认过，释放结果不重复计数",
                    "selection": selection,
                    "ledger": [i for i in self._ledger() if i.get("selection_id") == selection_id],
                    "released_count": selection.get("released_count", 0),
                }
            scope = SCOPE_BATCH
            selection["scope"] = scope
            selection["mode"] = MODE_BATCH
            selection["mode_label"] = SCOPE_BATCH
            selection["reconfirmed_at"] = _now()
            selection["frozen_reason"] = None
            if note:
                selection["note"] = note
            self._execute(selection, files, scope=scope, action="整批重新确认")
            return self._selection_result(selection)

    def interrupt_selection(self, selection_id: str, *, after: int = 1) -> dict[str, Any]:
        """模拟清理中断：只处理前 after 个无引用文件，其余保持可读并记为受保护。"""
        with self._lock:
            selection = self.get_selection(selection_id)
            if selection is None:
                return {"ok": False, "message": f"清理选择 {selection_id} 不存在"}
            if selection.get("status") == "已完成":
                return {"ok": False, "message": "该选择已完成，无法再模拟中断"}
            files, _ = self._resolve_files([int(i) for i in selection.get("file_ids", [])])
            done = 0
            for row in files:
                if row.get("status") == STATUS_RELEASED:
                    continue
                if done >= max(0, after) or row.get("referenced"):
                    # 中断后未处理的文件保持可读：有引用的转受保护，无引用的留在待确认，
                    # 后续可继续清理，但绝不在这里当作已释放。
                    if row.get("referenced"):
                        self._protect(
                            row, selection_id=selection_id,
                            scope=selection.get("scope") or SCOPE_SAFE,
                            detail="清理中断，文件有新增引用，保持可读",
                        )
                    else:
                        self._pending(
                            row, selection_id=selection_id,
                            scope=selection.get("scope") or SCOPE_SAFE,
                            detail="清理中断，未处理文件保持可读，可继续清理",
                        )
                    continue
                self._release(
                    row, selection_id=selection_id, scope=selection.get("scope") or SCOPE_SAFE,
                    detail="清理中断前已完成的释放",
                )
                done += 1
            selection["status"] = "已中断"
            selection["interrupted"] = True
            self._log(selection, "清理中断", f"中断前释放 {done} 个文件，其余文件受保护")
            self._refresh_totals(selection)
            return self._selection_result(selection)

    # ------------------------------------------------------------------
    # 处置台账
    # ------------------------------------------------------------------

    def ledger(self, *, report_id: str | None = None,
               selection_id: str | None = None) -> list[dict[str, Any]]:
        rows = [
            row for row in self._ledger()
            if (not report_id or row.get("report_id") == report_id)
            and (not selection_id or row.get("selection_id") == selection_id)
        ]
        return list(reversed(rows))

    def release_count(self, selection_id: str | None = None,
                      file_id: int | None = None) -> dict[str, Any]:
        """释放次数：同一选择 + 同一文件只计一次，抵御并发恢复的重复写入。"""
        rows = [
            item for item in self._ledger()
            if item.get("result") == STATUS_RELEASED
            and (not selection_id or item.get("selection_id") == selection_id)
            and (file_id is None or int(item.get("file_id", 0)) == file_id)
        ]
        unique = {(item.get("selection_id"), int(item.get("file_id", 0))) for item in rows}
        return {
            "selection_id": selection_id,
            "file_id": file_id,
            "release_count": len(unique),
            "raw_entries": len(rows),
            "files": sorted({file for _, file in unique}),
            "selections": sorted({str(sel) for sel, _ in unique if sel}),
        }

    def reset_demo(self) -> dict[str, Any]:
        """把辅助数据集恢复到初始演示状态，便于分别走两条清理口径。"""
        from app.orphan_seed import AUX_SEED_ROWS

        with self._lock:
            for name, rows in AUX_SEED_ROWS.items():
                table = store.aux(name)
                table.clear()
                # 深拷贝：checks / history 都是嵌套结构，浅拷贝会让恢复后的修改串回种子。
                table.extend(copy.deepcopy(row) for row in rows)
            return {"ok": True, "message": "孤立文件清单已恢复到演示初始状态"}


orphan_files = OrphanFileService()
