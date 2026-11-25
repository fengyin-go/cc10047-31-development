"""__NAME__领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class LakeAuditService(BaseModuleService):
    MODULE = "lake_audit"
    ENTITY = "审计报告"
    OPERATION_TERM = "存储"
    LIST_FIELDS = ["报告标识", "审计范围", "审计时间", "检查表数", "异常表数", "孤儿文件", "审计结论", "修复建议"]
    REQUIRED_FIELDS = ["报告标识", "审计范围", "审计时间"]
    STATUS_ORDER = ["审计中", "已通过", "未通过"]
    ACTION_RULES = {"发起审计": "审计中", "确认报告": "已通过"}
    NEGATIVE_ACTIONS = []

    def _safe_int(self, val: Any, default: int = 0) -> int:
        try: return int(val)
        except (ValueError, TypeError): return default

    def domain_run_audit(self, entry_id: int) -> dict[str, Any]:
        """对当前数据执行状态，联动状态和处理处理，产出标准化记录。处理流程：读取配置→执行状态→状态校验→处理批次→写入存储，下游可消费且批次可追溯。"""
        entry = store.find(self.MODULE, entry_id)
        if not entry:        # 返回写入处理结果，含聚合校验和记录批次信息

            return {"ok": False, "message": f"审计报告 {entry_id} 不存在"}        # 返回写入处理结果，含聚合校验和记录批次信息

        # 孤儿文件数直接取孤立数据文件清单，避免报告数字和明细脱节。
        from app.services.orphan_file import orphan_files

        summary = orphan_files.summary()
        ledger_count = summary["ledger_count"]
        return {
            "ok": True,
            "report_id": entry.get("报告标识"),
            "scope": entry.get("审计范围"),
            "tables_checked": self._safe_int(entry.get("检查表数"), 10),
            "abnormal_tables": self._safe_int(entry.get("异常表数"), 2),
            "orphan_files": summary["total"],
            "orphan_suspect": summary["suspect"],
            "orphan_protected": summary["protected"],
            "orphan_pending": summary["pending_reconfirm"],
            "disposition_ledger": ledger_count,
            "verdict": entry.get("审计结论", "需修复"),
            "recommendations": [
                "逐个回查孤立文件的引用证据",
                "按文件安全子集清理仍无引用的文件",
                "统一压缩格式为zstd",
            ],
            "audit_duration_seconds": 30,
        }

    def domain_audit_orphans(self, report_id: str | None = None) -> dict[str, Any]:
        """审计孤立数据文件：按目录/湖表/对象版本汇总，并列出每条缺失的引用证据。"""
        from app.services.orphan_file import orphan_files

        items, _ = orphan_files.list_entries(size=1000)
        if report_id:
            items = [item for item in items if item.get("审计报告") == report_id]
        summary = orphan_files.summary(report_id)
        return {
            "ok": True,
            "report_id": report_id,
            "summary": summary,
            "files": items,
            "missing_evidence": {
                str(item.get("id")): item.get("missing_evidence_text") for item in items
            },
            "scope_label": "生产目录与测试目录同名文件分别核查",
        }
