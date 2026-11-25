/** 孤立数据文件清单接口：筛选、引用证据、清理选择、执行详情和处置台账。 */
import { fetchJson, request } from './client'

export type EvidenceCheck = {
  key: string
  label: string
  present: boolean
  detail: string
}

export type HistoryItem = {
  at: string
  action?: string
  source?: string
  evidence?: string
  note?: string
  处置?: string
  说明?: string
  selection_id?: string | null
  ledger_id?: string
}

export type OrphanFile = {
  id: number
  status: string
  文件名: string
  目录类型: string
  目录路径: string
  湖表: string
  对象版本: string
  文件路径: string
  文件大小: number
  审计报告: string
  referenced: boolean
  checks: EvidenceCheck[]
  missing_evidence: EvidenceCheck[]
  missing_evidence_text: string
  evidence_complete: boolean
  releasable: boolean
  reference_history: HistoryItem[]
  disposition_history: HistoryItem[]
  reference_restored_at: string | null
  reference_source: string | null
  released_at: string | null
  released_bytes: number
  release_selection_id: string | null
  last_selection_id: string | null
  frozen_reason: string | null
  上次处置: string
  上次处置说明: string
  last_disposition: HistoryItem | null
}

export type SelectionFile = {
  id: number
  文件名: string
  目录类型: string
  目录路径: string
  湖表: string
  对象版本: string
}

export type SelectionEvent = {
  at: string
  action: string
  detail: string
}

export type Selection = {
  id: string
  selection_id: string
  created_at: string
  mode: string
  mode_label: string
  scope: string
  note: string
  report_id: string | null
  file_ids: number[]
  files: SelectionFile[]
  status: string
  released_file_ids: number[]
  protected_file_ids: number[]
  pending_file_ids: number[]
  released_count: number
  released_bytes: number
  events: SelectionEvent[]
  frozen_reason: string | null
  reconfirmed_at: string | null
  interrupted: boolean
}

export type LedgerEntry = {
  id: string
  selection_id: string | null
  file_id: number
  file_key: string
  文件名: string
  目录类型: string
  目录路径: string
  湖表: string
  对象版本: string
  report_id: string | null
  scope: string | null
  result: string
  released: boolean
  released_bytes: number
  detail: string
  missing_evidence: string[]
  at: string
}

export type SelectionDetail = Selection & {
  ledger: LedgerEntry[]
  file_details: OrphanFile[]
  execution_detail: {
    scope: string
    status: string
    released_count: number
    released_bytes: number
    protected_count: number
    pending_count: number
    frozen_reason: string | null
    reconfirm_required: boolean
  }
}

export type OrphanSummary = {
  report_id: string | null
  total: number
  by_status: Record<string, number>
  suspect: number
  protected: number
  pending_reconfirm: number
  released: number
  releasable: number
  released_bytes: number
  selection_count: number
  ledger_count: number
  production: number
  test: number
}

export type OrphanOptions = {
  directory_types: string[]
  tables: string[]
  object_versions: string[]
  statuses: string[]
}

export type PageResult<T> = {
  items: T[]
  total: number
  page: number
  size: number
}

export type ReleaseCount = {
  selection_id: string | null
  file_id: number | null
  release_count: number
  raw_entries: number
  files: number[]
  selections: string[]
}

export type SelectionResult = {
  ok: boolean
  message: string
  selection?: Selection
  ledger?: LedgerEntry[]
  released_count?: number
}

export type OrphanFilters = {
  directory_type?: string
  table?: string
  object_version?: string
  status?: string
  keyword?: string
}

function queryString(filters: Record<string, string | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value)
  }
  return params.toString()
}

export function listOrphanFiles(filters: OrphanFilters): Promise<PageResult<OrphanFile>> {
  return fetchJson<PageResult<OrphanFile>>(`/api/orphan-files?${queryString(filters)}`)
}

export function getOrphanOptions(): Promise<OrphanOptions> {
  return fetchJson<OrphanOptions>('/api/orphan-files/options')
}

export function getOrphanSummary(reportId?: string): Promise<OrphanSummary> {
  const suffix = reportId ? `?report_id=${encodeURIComponent(reportId)}` : ''
  return fetchJson<OrphanSummary>(`/api/orphan-files/summary${suffix}`)
}

export async function restoreReference(
  fileId: number,
  payload: { source: string; evidence: string; note: string },
): Promise<{ ok: boolean; message: string; entry?: OrphanFile }> {
  const response = await request(`/api/orphan-files/${fileId}/restore-reference`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('补发引用失败')
  return await response.json()
}

export async function submitSelection(payload: {
  file_ids: number[]
  mode: string
  note?: string
  selection_id?: string
  execute?: boolean
}): Promise<SelectionResult> {
  const response = await request('/api/orphan-files/selections', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('提交清理失败')
  return await response.json()
}

export async function listSelections(reportId?: string): Promise<{ items: Selection[]; total: number }> {
  const suffix = reportId ? `?report_id=${encodeURIComponent(reportId)}` : ''
  return fetchJson(`/api/orphan-files/selections${suffix}`)
}

export function getSelectionDetail(selectionId: string): Promise<SelectionDetail> {
  return fetchJson<SelectionDetail>(`/api/orphan-files/selections/${encodeURIComponent(selectionId)}`)
}

export async function executeSelection(selectionId: string): Promise<SelectionResult> {
  const response = await request(
    `/api/orphan-files/selections/${encodeURIComponent(selectionId)}/execute`,
    { method: 'POST' },
  )
  if (!response.ok) throw new Error('执行清理失败')
  return await response.json()
}

export async function resumeSelection(selectionId: string): Promise<SelectionResult> {
  const response = await request(
    `/api/orphan-files/selections/${encodeURIComponent(selectionId)}/resume`,
    { method: 'POST' },
  )
  if (!response.ok) throw new Error('继续处理失败')
  return await response.json()
}

export async function reconfirmSelection(
  selectionId: string,
  note = '',
): Promise<SelectionResult> {
  const response = await request(
    `/api/orphan-files/selections/${encodeURIComponent(selectionId)}/reconfirm`,
    { method: 'POST', body: JSON.stringify({ note }) },
  )
  if (!response.ok) throw new Error('重新确认失败')
  return await response.json()
}

export async function interruptSelection(
  selectionId: string,
  after = 1,
): Promise<SelectionResult> {
  const response = await request(
    `/api/orphan-files/selections/${encodeURIComponent(selectionId)}/interrupt`,
    { method: 'POST', body: JSON.stringify({ after }) },
  )
  if (!response.ok) throw new Error('模拟中断失败')
  return await response.json()
}

export function listLedger(params: { report_id?: string; selection_id?: string } = {}): Promise<{
  items: LedgerEntry[]
  total: number
}> {
  return fetchJson(`/api/orphan-files/ledger?${queryString(params)}`)
}

export function getReleaseCount(fileId: number, selectionId?: string): Promise<ReleaseCount> {
  const suffix = selectionId ? `?selection_id=${encodeURIComponent(selectionId)}` : ''
  return fetchJson<ReleaseCount>(`/api/orphan-files/${fileId}/release-count${suffix}`)
}

export async function resetDemo(): Promise<{ ok: boolean; message: string }> {
  const response = await request('/api/orphan-files/reset-demo', { method: 'POST' })
  if (!response.ok) throw new Error('重置演示数据失败')
  return await response.json()
}

export type VacuumJob = {
  id: number
  作业标识: string
  目标湖表: string
  保留版本: string
  清理范围: string
  status: string
}

export type VacuumPreview = {
  ok: boolean
  message?: string
  job_id: string
  table: string
  files_cleaned: number
  reclaimed_bytes: number
  cleanup_scope: string
  candidate_files: {
    id: number
    文件名: string
    目录类型: string
    文件路径: string
    missing_evidence: string
  }[]
  orphan_summary: OrphanSummary
}

export async function listVacuumJobs(): Promise<{ items: VacuumJob[]; total: number }> {
  return fetchJson('/api/orphan-files/vacuum-jobs')
}

export async function previewVacuum(jobId: number): Promise<VacuumPreview> {
  return fetchJson<VacuumPreview>(`/api/orphan-files/vacuum-jobs/${jobId}/preview`)
}

export async function runVacuumCleanup(
  jobId: number,
  payload: { mode: string; file_ids?: number[] },
): Promise<SelectionResult & { selection_id?: string; cleanup_scope?: string; job_id?: string }> {
  const response = await request(`/api/orphan-files/vacuum-jobs/${jobId}/cleanup`, {
    method: 'POST',
    body: JSON.stringify({ mode: payload.mode, file_ids: payload.file_ids ?? [] }),
  })
  if (!response.ok) throw new Error('历史清理执行失败')
  return await response.json()
}
