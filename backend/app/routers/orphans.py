"""孤立数据文件清单接口：筛选查询、引用证据回查、清理选择和处置台账。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import PageResult
from app.services.orphan_file import orphan_files

router = APIRouter(prefix="/api/orphan-files", tags=["孤立文件清单"])


class RestoreReferencePayload(BaseModel):
    source: str = "目录补发"
    evidence: str = ""
    note: str = ""


class SelectionPayload(BaseModel):
    file_ids: list[int] = Field(default_factory=list)
    mode: str = "safe_subset"
    note: str = ""
    selection_id: str | None = None
    # false 只登记回收范围，供“提交清理前恢复引用”的并发场景演示。
    execute: bool = True


class ActionPayload(BaseModel):
    note: str = ""


class InterruptPayload(BaseModel):
    after: int = 1


@router.get("", response_model=PageResult[dict])
def list_orphan_files(
    directory_type: str | None = Query(default=None),
    table: str | None = Query(default=None),
    object_version: str | None = Query(default=None),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    items, total = orphan_files.list_entries(
        directory_type=directory_type,
        table=table,
        object_version=object_version,
        status=status,
        keyword=keyword,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/options")
def list_options() -> dict[str, Any]:
    return orphan_files.options()


@router.get("/summary")
def get_summary(report_id: str | None = Query(default=None)) -> dict[str, Any]:
    return orphan_files.summary(report_id)


@router.get("/ledger")
def get_ledger(
    report_id: str | None = Query(default=None),
    selection_id: str | None = Query(default=None),
) -> dict[str, Any]:
    items = orphan_files.ledger(report_id=report_id, selection_id=selection_id)
    return {"items": items, "total": len(items)}


@router.get("/selections")
def list_selections(report_id: str | None = Query(default=None)) -> dict[str, Any]:
    items = orphan_files.list_selections(report_id=report_id)
    return {"items": items, "total": len(items)}


@router.post("/selections")
def submit_selection(payload: SelectionPayload) -> dict[str, Any]:
    return orphan_files.submit_selection(
        payload.file_ids, mode=payload.mode, note=payload.note,
        selection_id=payload.selection_id, execute=payload.execute,
    )


@router.get("/selections/{selection_id}")
def get_selection(selection_id: str) -> dict[str, Any]:
    detail = orphan_files.selection_detail(selection_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"清理选择 {selection_id} 不存在")
    return detail


@router.post("/selections/{selection_id}/execute")
def execute_selection(selection_id: str) -> dict[str, Any]:
    return orphan_files.execute_selection(selection_id)


@router.post("/selections/{selection_id}/resume")
def resume_selection(selection_id: str) -> dict[str, Any]:
    return orphan_files.resume_selection(selection_id)


@router.post("/selections/{selection_id}/reconfirm")
def reconfirm_selection(selection_id: str, payload: ActionPayload | None = None) -> dict[str, Any]:
    return orphan_files.reconfirm_selection(
        selection_id, note=(payload.note if payload else ""))


@router.post("/selections/{selection_id}/interrupt")
def interrupt_selection(selection_id: str, payload: InterruptPayload | None = None) -> dict[str, Any]:
    return orphan_files.interrupt_selection(
        selection_id, after=(payload.after if payload else 1))


class VacuumCleanupPayload(BaseModel):
    mode: str = "safe_subset"
    file_ids: list[int] = Field(default_factory=list)


@router.post("/reset-demo")
def reset_demo() -> dict[str, Any]:
    """把孤立文件清单与处置台账恢复到演示初始状态，方便重复验证两种口径。"""
    return orphan_files.reset_demo()


@router.get("/vacuum-jobs")
def list_vacuum_jobs() -> dict[str, Any]:
    """历史清理作业列表：回收范围从这里选，再进入孤立文件清单执行。"""
    from app.store import store

    items = [
        {
            "id": row.get("id"),
            "作业标识": row.get("作业标识"),
            "目标湖表": row.get("目标湖表"),
            "保留版本": row.get("保留版本"),
            "清理范围": row.get("清理范围"),
            "status": row.get("status"),
        }
        for row in store.rows("vacuum_job")
    ]
    return {"items": items, "total": len(items)}


@router.get("/vacuum-jobs/{job_id}/preview")
def preview_vacuum_scope(job_id: int) -> dict[str, Any]:
    from app.services import service_for

    service = service_for("vacuum_job")
    if service is None:
        raise HTTPException(status_code=404, detail="历史清理服务未注册")
    return service.domain_clean_history(job_id)


@router.post("/vacuum-jobs/{job_id}/cleanup")
def apply_vacuum_cleanup(job_id: int, payload: VacuumCleanupPayload) -> dict[str, Any]:
    """历史清理按文件写入释放结果，并回写湖仓审计处置台账。"""
    from app.services import service_for

    service = service_for("vacuum_job")
    if service is None:
        raise HTTPException(status_code=404, detail="历史清理服务未注册")
    return service.domain_apply_orphan_cleanup(
        job_id, mode=payload.mode, file_ids=payload.file_ids)


@router.get("/{file_id}", response_model=dict)
def get_orphan_file(file_id: int) -> dict[str, Any]:
    detail = orphan_files.get_detail(file_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"孤立文件 {file_id} 不存在")
    return detail


@router.post("/{file_id}/restore-reference", response_model=dict)
def restore_reference(file_id: int, payload: RestoreReferencePayload) -> dict[str, Any]:
    entry, message = orphan_files.restore_reference(
        file_id, source=payload.source, evidence=payload.evidence, note=payload.note)
    return {"ok": entry is not None, "message": message, "entry": entry}


@router.get("/{file_id}/release-count")
def get_release_count(file_id: int, selection_id: str | None = Query(default=None)) -> dict[str, Any]:
    entry = orphan_files.get_entry(file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"孤立文件 {file_id} 不存在")
    return orphan_files.release_count(selection_id, file_id)


