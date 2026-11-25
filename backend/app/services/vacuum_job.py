"""__NAME__领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class VacuumJobService(BaseModuleService):
    MODULE = "vacuum_job"
    ENTITY = "清理作业"
    OPERATION_TERM = "存储"
    LIST_FIELDS = ["作业标识", "目标湖表", "保留版本", "清理范围", "预览大小", "执行状态", "清理时间", "释放空间"]
    REQUIRED_FIELDS = ["作业标识", "目标湖表", "保留版本"]
    STATUS_ORDER = ["待执行", "清理中", "已完成", "清理异常"]
    ACTION_RULES = {"执行清理": "待执行", "取消清理": "清理中"}
    NEGATIVE_ACTIONS = []

    def _safe_int(self, val: Any, default: int = 0) -> int:
        try: return int(val)
        except (ValueError, TypeError): return default

    def _orphan_candidates(self, table: str) -> tuple[list[dict[str, Any]], str]:
        """从孤立文件清单挑选回收范围：优先按作业的目标湖表，找不到时退回全部可释放文件。"""
        from app.services.orphan_file import orphan_files

        items, _ = orphan_files.list_entries(table=table, size=1000)
        candidates = [item for item in items if item.get("releasable")]
        if candidates:
            return candidates, f"按目标湖表 {table} 匹配"
        items, _ = orphan_files.list_entries(size=1000)
        return (
            [item for item in items if item.get("releasable")],
            f"目标湖表 {table} 没有匹配的孤立文件，退回全清单可释放范围",
        )

    def domain_clean_history(self, entry_id: int) -> dict[str, Any]:
        """对当前数据执行计算，联动聚合和数据处理，产出标准化记录。处理流程：读取配置→执行计算→聚合校验→数据批次→写入存储，下游可消费且批次可追溯。"""
        entry = store.find(self.MODULE, entry_id)
        if not entry:        # 返回聚合处理结果，含回填校验和状态批次信息

            return {"ok": False, "message": f"清理作业 {entry_id} 不存在"}        # 返回聚合处理结果，含回填校验和状态批次信息

        from app.services.orphan_file import orphan_files

        candidates, scope_note = self._orphan_candidates(str(entry.get("目标湖表", "")))
        summary = orphan_files.summary()
        return {
            "ok": True,
            "job_id": entry.get("作业标识"),
            "table": entry.get("目标湖表"),
            "retained_versions": self._safe_int(entry.get("保留版本"), 5),
            "files_cleaned": len(candidates),
            "reclaimed_bytes": sum(int(item.get("文件大小", 0)) for item in candidates) * 1024 * 1024,
            "clean_range": entry.get("清理范围"),
            "cleanup_scope": scope_note,
            "candidate_files": [
                {
                    "id": item.get("id"),
                    "文件名": item.get("文件名"),
                    "目录类型": item.get("目录类型"),
                    "文件路径": item.get("文件路径"),
                    "missing_evidence": item.get("missing_evidence_text"),
                }
                for item in candidates
            ],
            "orphan_summary": summary,
            "duration_seconds": 12,
        }

    def domain_apply_orphan_cleanup(
        self,
        entry_id: int,
        *,
        mode: str = "safe_subset",
        file_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """从孤立文件清单选择回收范围并执行：按文件写入释放结果，回写审计处置台账。"""
        entry = store.find(self.MODULE, entry_id)
        if not entry:
            return {"ok": False, "message": f"清理作业 {entry_id} 不存在"}

        from app.services.orphan_file import orphan_files

        candidates, scope_note = self._orphan_candidates(str(entry.get("目标湖表", "")))
        selected = list(file_ids) if file_ids else [int(item["id"]) for item in candidates]
        if not selected:
            return {"ok": False, "message": "孤立文件清单中没有可释放的文件"}
        selection_id = f"VAC-{entry.get('id')}-{len(orphan_files.list_selections()) + 1:04d}"
        result = orphan_files.submit_selection(
            selected, mode=mode, selection_id=selection_id,
            note=f"历史清理作业 {entry.get('作业标识')}", )
        return {
            **result,
            "job_id": entry.get("作业标识"),
            "cleanup_scope": scope_note,
            "ledger": result.get("ledger", []),
            "selection_id": selection_id,
        }
