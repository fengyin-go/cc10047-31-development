"""孤立数据文件清单的演示数据。

这里单独维护辅助数据集，不进入 18 个业务模块的概览统计：
- orphan_file: 疑似孤立文件清单（生产目录与测试目录分别一条，同名文件靠目录隔离）
- cleanup_selection: 历史清理回收范围（运行时生成）
- audit_ledger: 湖仓审计处置台账（运行时生成）
"""
from __future__ import annotations

from typing import Any

_REPORT = "AUD-2026-1120-01"


def _checks(*, catalog_present: bool = False, catalog_detail: str = "") -> list[dict[str, Any]]:
    return [
        {
            "key": "commit_log",
            "label": "Delta 提交日志 AddFile 引用",
            "present": False,
            "detail": "提交版本 v12 的 delta_log 中没有该文件路径",
        },
        {
            "key": "snapshot_manifest",
            "label": "表快照清单引用",
            "present": False,
            "detail": "当前快照 s-20261120-0900 的 manifest 未包含该文件",
        },
        {
            "key": "catalog_entry",
            "label": "Catalog 目录清单条目",
            "present": catalog_present,
            "detail": catalog_detail or "orders 目录中没有该对象版本条目",
        },
    ]


ORPHAN_FILE_SEED: list[dict[str, Any]] = [
    {
        "id": 1,
        "status": "疑似孤立",
        "文件名": "f7.parquet",
        "目录类型": "生产目录",
        "目录路径": "s3://lakehouse/prod/orders",
        "湖表": "orders",
        "对象版本": "v12",
        "文件路径": "s3://lakehouse/prod/orders/date=2026-11-20/f7.parquet",
        "文件大小": 52,
        "审计报告": _REPORT,
        "referenced": False,
        "checks": _checks(),
        "reference_history": [],
        "disposition_history": [],
        "created_at": "2026-11-20T09:40:00+08:00",
        "reference_restored_at": None,
        "reference_source": None,
        "released_at": None,
        "released_bytes": 0,
        "release_selection_id": None,
        "last_selection_id": None,
        "frozen_reason": None,
    },
    {
        "id": 2,
        "status": "疑似孤立",
        "文件名": "f8.parquet",
        "目录类型": "生产目录",
        "目录路径": "s3://lakehouse/prod/orders",
        "湖表": "orders",
        "对象版本": "v12",
        "文件路径": "s3://lakehouse/prod/orders/date=2026-11-20/f8.parquet",
        "文件大小": 71,
        "审计报告": _REPORT,
        "referenced": False,
        "checks": _checks(),
        "reference_history": [],
        "disposition_history": [],
        "created_at": "2026-11-20T09:41:00+08:00",
        "reference_restored_at": None,
        "reference_source": None,
        "released_at": None,
        "released_bytes": 0,
        "release_selection_id": None,
        "last_selection_id": None,
        "frozen_reason": None,
    },
    {
        "id": 3,
        "status": "受保护",
        "文件名": "f7.parquet",
        "目录类型": "测试目录",
        "目录路径": "s3://lakehouse/test/orders",
        "湖表": "orders",
        "对象版本": "v12",
        "文件路径": "s3://lakehouse/test/orders/date=2026-11-20/f7.parquet",
        "文件大小": 18,
        "审计报告": _REPORT,
        "referenced": True,
        "checks": _checks(
            catalog_present=True,
            catalog_detail="test/orders 目录清单包含 f7.parquet@v12（测试目录同步）",
        ),
        "reference_history": [
            {
                "at": "2026-11-20T09:55:00+08:00",
                "action": "目录补发",
                "source": "测试目录清单同步",
                "evidence": "test/orders 目录清单包含 f7.parquet@v12",
                "note": "测试目录同名文件独立核查，不沿用生产目录结论",
            }
        ],
        "disposition_history": [
            {
                "at": "2026-11-20T09:55:00+08:00",
                "处置": "受保护",
                "说明": "测试目录已补发引用，同名文件不参与生产目录清理",
            }
        ],
        "created_at": "2026-11-20T09:42:00+08:00",
        "reference_restored_at": "2026-11-20T09:55:00+08:00",
        "reference_source": "测试目录清单同步",
        "released_at": None,
        "released_bytes": 0,
        "release_selection_id": None,
        "last_selection_id": None,
        "frozen_reason": None,
    },
    {
        "id": 4,
        "status": "已释放",
        "文件名": "f8.parquet",
        "目录类型": "测试目录",
        "目录路径": "s3://lakehouse/test/orders",
        "湖表": "orders",
        "对象版本": "v12",
        "文件路径": "s3://lakehouse/test/orders/date=2026-11-20/f8.parquet",
        "文件大小": 18,
        "审计报告": _REPORT,
        "referenced": False,
        "checks": [
            {
                "key": "commit_log",
                "label": "Delta 提交日志 AddFile 引用",
                "present": False,
                "detail": "文件已于测试目录清理前完成引用核查",
            },
            {
                "key": "snapshot_manifest",
                "label": "表快照清单引用",
                "present": False,
                "detail": "文件已于测试目录清理前完成引用核查",
            },
            {
                "key": "catalog_entry",
                "label": "Catalog 目录清单条目",
                "present": False,
                "detail": "测试目录确认无引用后释放",
            },
        ],
        "reference_history": [],
        "disposition_history": [
            {
                "at": "2026-11-19T16:20:00+08:00",
                "处置": "已释放",
                "说明": "测试目录同名文件独立回收，释放 18 MB",
                "selection_id": "SEL-DEMO-TEST-01",
            }
        ],
        "created_at": "2026-11-19T15:00:00+08:00",
        "reference_restored_at": None,
        "reference_source": None,
        "released_at": "2026-11-19T16:20:00+08:00",
        "released_bytes": 18 * 1024 * 1024,
        "release_selection_id": "SEL-DEMO-TEST-01",
        "last_selection_id": "SEL-DEMO-TEST-01",
        "frozen_reason": None,
    },
]

AUX_SEED_ROWS: dict[str, list[dict[str, Any]]] = {
    "orphan_file": ORPHAN_FILE_SEED,
    "cleanup_selection": [],
    "audit_ledger": [],
}
