<template>
  <section class="page" data-module="orphan_file">
    <header class="page-head">
      <div>
        <h2>孤立数据文件清单</h2>
        <p class="page-desc">
          按目录、湖表及对象版本逐个核查疑似孤立文件，回查缺失的引用证据；
          生产目录与测试目录的同名文件分别核查、分别处置。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="refresh-audit" type="button" @click="refreshAll">
          刷新审计清单
        </button>
        <button class="btn ghost" data-testid="refresh-detail" type="button" @click="refreshDetail">
          刷新执行详情
        </button>
        <button class="btn ghost" data-testid="reset-demo" type="button" @click="resetDemo">
          重置演示数据
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">清单文件数</span>
        <strong class="stat-value" data-testid="stat-total">{{ summary.total }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">疑似孤立</span>
        <strong class="stat-value" data-testid="stat-suspect">{{ summary.suspect }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">受保护</span>
        <strong class="stat-value" data-testid="stat-protected">{{ summary.protected }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">待重新确认</span>
        <strong class="stat-value" data-testid="stat-pending">{{ summary.pending_reconfirm }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已释放 / 释放空间</span>
        <strong class="stat-value" data-testid="stat-released">
          {{ summary.released }} / {{ formatSize(summary.released_bytes) }}
        </strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">生产 / 测试目录</span>
        <strong class="stat-value">{{ summary.production }} / {{ summary.test }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reloadFiles">
      <label class="filter-item">
        <span>目录类型</span>
        <select v-model="filters.directory_type" data-testid="filter-directory-type">
          <option value="">全部目录</option>
          <option v-for="item in options.directory_types" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>湖表</span>
        <select v-model="filters.table" data-testid="filter-table">
          <option value="">全部湖表</option>
          <option v-for="item in options.tables" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>对象版本</span>
        <select v-model="filters.object_version" data-testid="filter-object-version">
          <option value="">全部版本</option>
          <option v-for="item in options.object_versions" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status" data-testid="filter-status">
          <option value="">全部状态</option>
          <option v-for="item in options.statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>文件名 / 路径</span>
        <input v-model="filters.keyword" data-testid="filter-keyword" placeholder="如 f7" />
      </label>
      <button class="btn primary" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table" data-testid="orphan-table">
      <thead>
        <tr>
          <th class="col-check">
            <input
              type="checkbox"
              data-testid="select-all"
              :checked="allSelectableChecked"
              @change="toggleAll"
            />
          </th>
          <th>文件名</th>
          <th>目录类型</th>
          <th>目录路径</th>
          <th>湖表</th>
          <th>对象版本</th>
          <th>大小</th>
          <th>状态</th>
          <th>缺失引用证据</th>
          <th>最近处置</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          :data-testid="`orphan-row-${row.id}`"
          :data-status="row.status"
          :class="{ 'row-active': detailFile?.id === row.id }"
        >
          <td class="col-check">
            <input
              type="checkbox"
              :data-testid="`select-${row.id}`"
              :checked="selectedIds.includes(row.id)"
              :disabled="row.status === '已释放'"
              @change="toggleSelect(row.id)"
            />
          </td>
          <td>{{ row.文件名 }}</td>
          <td>{{ row.目录类型 }}</td>
          <td class="mono">{{ row.目录路径 }}</td>
          <td>{{ row.湖表 }}</td>
          <td>{{ row.对象版本 }}</td>
          <td>{{ row.文件大小 }} MB</td>
          <td><span class="status-chip" :data-status="row.status">{{ row.status }}</span></td>
          <td class="evidence-cell" :class="{ 'evidence-missing': row.missing_evidence.length }">
            {{ row.missing_evidence_text }}
          </td>
          <td>{{ row.上次处置 }}<span v-if="row.上次处置说明 !== '—'" class="muted-note">（{{ row.上次处置说明 }}）</span></td>
          <td class="row-actions">
            <button class="link" type="button" :data-testid="`detail-${row.id}`" @click="openDetail(row)">
              核查依据
            </button>
            <button
              v-if="row.status !== '已释放' && !row.referenced"
              class="link"
              type="button"
              :data-testid="`restore-${row.id}`"
              @click="openRestore(row)"
            >
              补发引用
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="11" class="empty-state">没有符合条件的孤立文件</td>
        </tr>
      </tbody>
    </table>

    <div class="selection-bar">
      <span data-testid="selected-count">已选 {{ selectedIds.length }} 个文件</span>
      <label class="mode-option">
        <input v-model="mode" type="radio" value="safe_subset" data-testid="mode-safe" />
        按文件安全子集（仅释放仍无引用的文件）
      </label>
      <label class="mode-option">
        <input v-model="mode" type="radio" value="whole_batch" data-testid="mode-batch" />
        整批重新确认（有新增引用则整批冻结）
      </label>
      <input
        v-model="selectionNote"
        class="note-input"
        data-testid="selection-note"
        placeholder="处置备注（可选）"
      />
      <button class="btn primary" data-testid="submit-selection" type="button" :disabled="!selectedIds.length || busy" @click="submitCleanup">
        提交清理
      </button>
      <span v-if="message" class="ok-text" data-testid="action-message">{{ message }}</span>
      <span v-if="errorMessage" class="error-text" data-testid="error-message">{{ errorMessage }}</span>
    </div>

    <section v-if="detailFile" class="panel" data-testid="file-detail">
      <header class="panel-head">
        <h3>核查依据：{{ detailFile.目录类型 }} / {{ detailFile.文件名 }} @ {{ detailFile.对象版本 }}</h3>
        <button class="link" type="button" @click="detailFile = null">收起</button>
      </header>
      <p class="muted-note">文件路径：<span class="mono">{{ detailFile.文件路径 }}</span></p>
      <div class="panel-grid">
        <div>
          <h4>引用证据核查</h4>
          <ul class="evidence-list">
            <li v-for="check in detailFile.checks" :key="check.key" :data-testid="`check-${detailFile.id}-${check.key}`">
              <span class="evidence-tag" :class="check.present ? 'present' : 'missing'">
                {{ check.present ? '已引用' : '缺失' }}
              </span>
              <strong>{{ check.label }}</strong>
              <p>{{ check.detail }}</p>
            </li>
          </ul>
          <p v-if="detailFile.reference_restored_at" class="ok-text">
            引用恢复于 {{ detailFile.reference_restored_at }}（{{ detailFile.reference_source }}）
          </p>
        </div>
        <div>
          <h4>引用变更历史</h4>
          <ul v-if="detailFile.reference_history.length" class="history-list">
            <li v-for="(item, index) in detailFile.reference_history" :key="`ref-${index}`">
              <span class="mono">{{ item.at }}</span>
              <strong>{{ item.action }}</strong>
              <p>{{ item.evidence }}</p>
              <p class="muted-note">{{ item.note }}</p>
            </li>
          </ul>
          <p v-else class="muted-note">暂无补发记录</p>

          <h4>处置历史</h4>
          <ul v-if="detailFile.disposition_history.length" class="history-list">
            <li v-for="(item, index) in detailFile.disposition_history" :key="`dis-${index}`">
              <span class="mono">{{ item.at }}</span>
              <strong>{{ item.处置 }}</strong>
              <p>{{ item.说明 }}</p>
              <p v-if="item.selection_id" class="muted-note">选择：{{ item.selection_id }}</p>
            </li>
          </ul>
          <p v-else class="muted-note">暂无处置记录</p>
        </div>
      </div>

      <form class="restore-form" @submit.prevent="submitRestore">
        <h4>目录补发引用</h4>
        <label class="filter-item">
          <span>引用来源</span>
          <input v-model="restoreForm.source" data-testid="restore-source" placeholder="如 生产目录清单同步" />
        </label>
        <label class="filter-item wide">
          <span>引用证据</span>
          <input v-model="restoreForm.evidence" data-testid="restore-evidence" placeholder="如 prod/orders 目录清单包含 f7.parquet@v12" />
        </label>
        <label class="filter-item wide">
          <span>备注</span>
          <input v-model="restoreForm.note" data-testid="restore-note" placeholder="补发说明（可选）" />
        </label>
        <button class="btn" type="submit" :disabled="busy">确认补发</button>
      </form>
    </section>

    <section class="panel" data-testid="selection-panel">
      <header class="panel-head">
        <h3>清理选择与执行详情</h3>
        <span class="muted-note">同一选择并发恢复只计一次释放；新增引用或清理中断时仍可读的文件一律保护</span>
      </header>
      <div class="panel-grid">
        <div>
          <h4>清理选择</h4>
          <table class="data-table compact">
            <thead>
              <tr><th>选择</th><th>本次范围</th><th>状态</th><th>释放/保护/待核</th><th>创建时间</th></tr>
            </thead>
            <tbody>
              <tr
                v-for="item in selections"
                :key="item.id"
                :class="{ 'row-active': selectionDetail?.id === item.id }"
                :data-testid="`selection-row-${item.id}`"
                @click="selectSelection(item.id)"
              >
                <td class="mono">{{ item.id }}</td>
                <td>{{ item.scope }}</td>
                <td>{{ item.status }}</td>
                <td>{{ item.released_count }} / {{ item.protected_file_ids.length }} / {{ item.pending_file_ids.length }}</td>
                <td class="mono">{{ item.created_at }}</td>
              </tr>
              <tr v-if="!selections.length">
                <td colspan="5" class="empty-state">还没有清理选择，请勾选文件后提交清理</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="selectionDetail" class="detail-box" data-testid="execution-detail">
          <h4>执行详情：{{ selectionDetail.id }}</h4>
          <dl class="exec-meta">
            <dt>本次采用范围</dt>
            <dd data-testid="exec-scope">{{ selectionDetail.execution_detail.scope }}</dd>
            <dt>执行状态</dt>
            <dd data-testid="exec-status">{{ selectionDetail.execution_detail.status }}</dd>
            <dt>释放文件数</dt>
            <dd data-testid="exec-released">{{ selectionDetail.execution_detail.released_count }}</dd>
            <dt>受保护 / 待核</dt>
            <dd>{{ selectionDetail.execution_detail.protected_count }} / {{ selectionDetail.execution_detail.pending_count }}</dd>
            <dt>释放空间</dt>
            <dd>{{ formatSize(selectionDetail.execution_detail.released_bytes) }}</dd>
            <dt v-if="selectionDetail.frozen_reason">冻结原因</dt>
            <dd v-if="selectionDetail.frozen_reason" class="error-text" data-testid="exec-frozen-reason">
              {{ selectionDetail.frozen_reason }}
            </dd>
          </dl>
          <p>
            <span class="muted-note">释放次数核对：</span>
            <strong data-testid="release-count">{{ releaseCountText }}</strong>
            <button class="link" type="button" data-testid="check-release-count" @click="checkReleaseCount">
              按文件核对释放次数
            </button>
          </p>
          <div class="page-actions wrap">
            <button
              v-if="selectionDetail.status === '待执行'"
              class="btn primary"
              data-testid="execute-selection"
              type="button"
              :disabled="busy"
              @click="executeSelected"
            >
              执行清理
            </button>
            <button
              v-if="selectionDetail.execution_detail.reconfirm_required"
              class="btn"
              data-testid="resume-selection"
              type="button"
              :disabled="busy"
              @click="resumeSelected"
            >
              继续处理仍无引用文件
            </button>
            <button
              v-if="selectionDetail.execution_detail.reconfirm_required || selectionDetail.frozen_reason"
              class="btn primary"
              data-testid="reconfirm-selection"
              type="button"
              :disabled="busy"
              @click="reconfirmSelected"
            >
              整批重新确认
            </button>
            <button
              v-if="selectionDetail.status !== '已完成'"
              class="btn ghost"
              data-testid="interrupt-selection"
              type="button"
              :disabled="busy"
              @click="interruptSelected"
            >
              模拟清理中断
            </button>
          </div>
          <table class="data-table compact">
            <thead>
              <tr><th>文件</th><th>目录</th><th>当前状态</th><th>缺失证据</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in selectionDetail.file_details" :key="item.id" :data-testid="`exec-file-${item.id}`">
                <td>{{ item.文件名 }}</td>
                <td>{{ item.目录类型 }}</td>
                <td>{{ item.status }}</td>
                <td>{{ item.missing_evidence_text }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="muted-note">选择一个清理选择查看执行详情</p>
      </div>
    </section>

    <section class="panel" data-testid="vacuum-panel">
      <header class="panel-head">
        <h3>历史清理回收范围</h3>
        <span class="muted-note">从孤立文件清单选择回收范围，按文件写入释放结果并回写审计处置台账</span>
      </header>
      <div class="vacuum-bar">
        <label class="filter-item">
          <span>清理作业</span>
          <select v-model.number="vacuumJobId" data-testid="vacuum-job">
            <option :value="0" disabled>选择历史清理作业</option>
            <option v-for="job in vacuumJobs" :key="job.id" :value="job.id">
              {{ job.作业标识 }}（{{ job.目标湖表 }}）
            </option>
          </select>
        </label>
        <button class="btn" data-testid="vacuum-preview" type="button" :disabled="!vacuumJobId || busy" @click="loadVacuumPreview">
          预览回收范围
        </button>
        <label class="mode-option">
          <input v-model="vacuumMode" type="radio" value="safe_subset" data-testid="vacuum-mode-safe" />
          安全子集
        </label>
        <label class="mode-option">
          <input v-model="vacuumMode" type="radio" value="whole_batch" data-testid="vacuum-mode-batch" />
          整批
        </label>
        <button class="btn primary" data-testid="vacuum-run" type="button" :disabled="!vacuumJobId || busy" @click="runVacuum">
          执行清理
        </button>
      </div>
      <div v-if="vacuumPreview" data-testid="vacuum-preview-result">
        <p class="muted-note">
          回收范围：{{ vacuumPreview.cleanup_scope }}；候选 {{ vacuumPreview.files_cleaned }} 个文件，
          预览释放 {{ formatSize(vacuumPreview.reclaimed_bytes) }}
        </p>
        <table class="data-table compact">
          <thead><tr><th>文件</th><th>目录</th><th>路径</th><th>缺失证据</th></tr></thead>
          <tbody>
            <tr v-for="file in vacuumPreview.candidate_files" :key="file.id">
              <td>{{ file.文件名 }}</td>
              <td>{{ file.目录类型 }}</td>
              <td class="mono">{{ file.文件路径 }}</td>
              <td>{{ file.missing_evidence }}</td>
            </tr>
            <tr v-if="!vacuumPreview.candidate_files.length">
              <td colspan="4" class="empty-state">没有可释放的孤立文件</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel" data-testid="ledger-panel">
      <header class="panel-head">
        <h3>湖仓审计处置台账</h3>
        <span class="muted-note">释放结果按文件写入，记录本次采用的范围与缺失证据</span>
      </header>
      <table class="data-table compact">
        <thead>
          <tr>
            <th>台账</th><th>选择</th><th>文件</th><th>目录</th><th>结果</th>
            <th>本次范围</th><th>释放空间</th><th>缺失证据</th><th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in ledger" :key="item.id" :data-testid="`ledger-${item.id}`">
            <td class="mono">{{ item.id }}</td>
            <td class="mono">{{ item.selection_id || '—' }}</td>
            <td>{{ item.文件名 }}<span class="muted-note"> @{{ item.对象版本 }}</span></td>
            <td>{{ item.目录类型 }}</td>
            <td>{{ item.result }}</td>
            <td>{{ item.scope || '—' }}</td>
            <td>{{ item.released_bytes ? formatSize(item.released_bytes) : '—' }}</td>
            <td>{{ item.missing_evidence.join('、') || '—' }}</td>
            <td class="mono">{{ item.at }}</td>
          </tr>
          <tr v-if="!ledger.length">
            <td colspan="9" class="empty-state">暂无处置记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  executeSelection,
  getOrphanOptions,
  listVacuumJobs,
  previewVacuum,
  runVacuumCleanup,
  getOrphanSummary,
  getReleaseCount,
  getSelectionDetail,
  interruptSelection,
  listLedger,
  listOrphanFiles,
  listSelections,
  reconfirmSelection,
  resetDemo as resetDemoApi,
  restoreReference,
  resumeSelection,
  submitSelection,
} from '@/api/orphans'
import type {
  LedgerEntry,
  OrphanFile,
  OrphanFilters,
  OrphanOptions,
  OrphanSummary,
  ReleaseCount,
  Selection,
  SelectionDetail,
  VacuumJob,
  VacuumPreview,
} from '@/api/orphans'

const rows = ref<OrphanFile[]>([])
const options = ref<OrphanOptions>({
  directory_types: [],
  tables: [],
  object_versions: [],
  statuses: [],
})
const summary = ref<OrphanSummary>({
  report_id: null,
  total: 0,
  by_status: {},
  suspect: 0,
  protected: 0,
  pending_reconfirm: 0,
  released: 0,
  releasable: 0,
  released_bytes: 0,
  selection_count: 0,
  ledger_count: 0,
  production: 0,
  test: 0,
})
const filters = reactive<OrphanFilters>({
  directory_type: '',
  table: '',
  object_version: '',
  status: '',
  keyword: '',
})
const selectedIds = ref<number[]>([])
const detailFile = ref<OrphanFile | null>(null)
const restoreForm = reactive({ source: '目录补发', evidence: '', note: '' })
const mode = ref<'safe_subset' | 'whole_batch'>('safe_subset')
const selectionNote = ref('')
const selections = ref<Selection[]>([])
const selectionDetail = ref<SelectionDetail | null>(null)
const ledger = ref<LedgerEntry[]>([])
const releaseCounts = ref<ReleaseCount[]>([])
const releaseCountText = computed(() => {
  if (!releaseCounts.value.length) return '—'
  return releaseCounts.value
    .map((item) => `#${item.file_id}×${item.release_count}`)
    .join('，')
})
const vacuumJobs = ref<VacuumJob[]>([])
const vacuumJobId = ref(0)
const vacuumMode = ref<'safe_subset' | 'whole_batch'>('safe_subset')
const vacuumPreview = ref<VacuumPreview | null>(null)
const busy = ref(false)
const message = ref('')
const errorMessage = ref('')

const selectableIds = computed(() => rows.value.filter((row) => row.status !== '已释放').map((row) => row.id))
const allSelectableChecked = computed(
  () => selectableIds.value.length > 0 && selectableIds.value.every((id) => selectedIds.value.includes(id)),
)

function formatSize(bytes: number): string {
  if (!bytes) return '0 MB'
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`
}

function toggleSelect(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleAll() {
  if (allSelectableChecked.value) {
    selectedIds.value = selectedIds.value.filter((id) => !selectableIds.value.includes(id))
  } else {
    selectedIds.value = [...new Set([...selectedIds.value, ...selectableIds.value])]
  }
}

function resetFilters() {
  filters.directory_type = ''
  filters.table = ''
  filters.object_version = ''
  filters.status = ''
  filters.keyword = ''
  void reloadFiles()
}

async function reloadFiles() {
  errorMessage.value = ''
  try {
    const payload = await listOrphanFiles(filters)
    rows.value = payload.items
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '孤立文件清单读取失败'
  }
}

async function loadSummary() {
  summary.value = await getOrphanSummary()
}

async function loadSelections() {
  const payload = await listSelections()
  selections.value = payload.items
}

async function loadLedger() {
  const payload = await listLedger()
  ledger.value = payload.items
}

async function refreshAll() {
  errorMessage.value = ''
  try {
    await Promise.all([reloadFiles(), loadSummary(), loadSelections(), loadLedger()])
    if (detailFile.value) {
      const item = rows.value.find((row) => row.id === detailFile.value?.id)
      if (item) detailFile.value = item
    }
    if (selectionDetail.value) await refreshDetail()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '刷新审计清单失败'
  }
}

async function refreshDetail() {
  if (!selectionDetail.value) {
    message.value = '尚未选择清理选择，执行详情无需刷新'
    return
  }
  await selectSelection(selectionDetail.value.id)
  message.value = '审计清单与执行详情已刷新'
}

function openDetail(row: OrphanFile) {
  detailFile.value = row
  restoreForm.source = '目录补发'
  restoreForm.evidence = `${row.目录路径} 目录清单包含 ${row.文件名}@${row.对象版本}`
  restoreForm.note = ''
  message.value = ''
}

function openRestore(row: OrphanFile) {
  openDetail(row)
}

async function submitRestore() {
  if (!detailFile.value) return
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await restoreReference(detailFile.value.id, { ...restoreForm })
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    const fileId = detailFile.value.id
    await refreshAll()
    const updated = rows.value.find((row) => row.id === fileId)
    if (updated) detailFile.value = updated
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '补发引用失败'
  } finally {
    busy.value = false
  }
}

async function submitCleanup() {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  releaseCounts.value = []
  try {
    const result = await submitSelection({
      file_ids: [...selectedIds.value],
      mode: mode.value,
      note: selectionNote.value,
    })
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    if (result.selection) await selectSelection(result.selection.id)
    await Promise.all([reloadFiles(), loadSummary(), loadSelections(), loadLedger()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交清理失败'
  } finally {
    busy.value = false
  }
}

async function selectSelection(selectionId: string) {
  errorMessage.value = ''
  try {
    selectionDetail.value = await getSelectionDetail(selectionId)
    releaseCounts.value = []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '执行详情读取失败'
  }
}

async function applySelectionAction(action: () => Promise<{ ok: boolean; message: string }>) {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await action()
    if (!result.ok) throw new Error(result.message)
    message.value = result.message
    const current = selectionDetail.value?.id
    await Promise.all([reloadFiles(), loadSummary(), loadSelections(), loadLedger()])
    if (current) await selectSelection(current)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '执行失败'
  } finally {
    busy.value = false
  }
}

function executeSelected() {
  if (!selectionDetail.value) return
  const id = selectionDetail.value.id
  void applySelectionAction(() => executeSelection(id))
}

function resumeSelected() {
  if (!selectionDetail.value) return
  const id = selectionDetail.value.id
  void applySelectionAction(() => resumeSelection(id))
}

function reconfirmSelected() {
  if (!selectionDetail.value) return
  const id = selectionDetail.value.id
  void applySelectionAction(() => reconfirmSelection(id, '目录引用变化后整批重新确认'))
}

function interruptSelected() {
  if (!selectionDetail.value) return
  const id = selectionDetail.value.id
  void applySelectionAction(() => interruptSelection(id, 1))
}

async function checkReleaseCount() {
  if (!selectionDetail.value) return
  try {
    // 逐个文件核对：同一选择并发恢复时按文件只应计一次。
    releaseCounts.value = await Promise.all(
      selectionDetail.value.file_ids.map((id) => getReleaseCount(id, selectionDetail.value!.id)),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '释放次数读取失败'
  }
}

async function loadVacuumPreview() {
  if (!vacuumJobId.value) return
  errorMessage.value = ''
  try {
    vacuumPreview.value = await previewVacuum(vacuumJobId.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回收范围预览失败'
  }
}

async function runVacuum() {
  if (!vacuumJobId.value) return
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await runVacuumCleanup(vacuumJobId.value, { mode: vacuumMode.value })
    if (!result.ok) throw new Error(result.message)
    message.value = `${result.message}（${result.cleanup_scope || ''}）`
    if (result.selection?.id) await selectSelection(result.selection.id)
    await Promise.all([
      reloadFiles(), loadSummary(), loadSelections(), loadLedger(), loadVacuumPreview(),
    ])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '历史清理执行失败'
  } finally {
    busy.value = false
  }
}

async function resetDemo() {
  busy.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const result = await resetDemoApi()
    message.value = result.message
    selectedIds.value = []
    detailFile.value = null
    selectionDetail.value = null
    releaseCounts.value = []
    vacuumPreview.value = null
    await Promise.all([reloadFiles(), loadSummary(), loadSelections(), loadLedger()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重置演示数据失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    options.value = await getOrphanOptions()
    const jobs = await listVacuumJobs()
    vacuumJobs.value = jobs.items
    if (jobs.items.length) vacuumJobId.value = jobs.items[0].id
    await Promise.all([reloadFiles(), loadSummary(), loadSelections(), loadLedger()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '孤立文件清单初始化失败'
  }
})
</script>

<style scoped>
.col-check { width: 34px; text-align: center; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.muted-note { color: var(--muted); font-size: 12px; }
.ok-text { color: #067647; font-size: 12px; }
.evidence-cell { max-width: 260px; font-size: 12px; }
.evidence-missing { color: #b42318; }
.status-chip { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; background: #eef2f7; }
.status-chip[data-status='受保护'] { background: #e8f2ff; color: #175cd3; }
.status-chip[data-status='已释放'] { background: #ecfdf3; color: #067647; }
.status-chip[data-status='待重新确认'] { background: #fef3f2; color: #b42318; }
.row-active { background: #f5f9ff; }
.selection-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; padding: 10px 12px; background: #fff; border: 1px solid var(--border); border-radius: 8px; font-size: 13px; }
.mode-option { display: inline-flex; gap: 4px; align-items: center; font-size: 12px; }
.note-input { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; flex: 1; min-width: 180px; }
.panel { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.panel-head h3 { margin: 0 0 8px; font-size: 15px; }
.panel-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel h4 { font-size: 13px; margin: 12px 0 6px; }
.evidence-list, .history-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.evidence-list li, .history-list li { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; font-size: 12px; }
.evidence-list p, .history-list p { margin: 4px 0 0; color: var(--muted); }
.evidence-tag { display: inline-block; margin-right: 6px; border-radius: 4px; padding: 1px 6px; font-size: 11px; }
.evidence-tag.present { background: #ecfdf3; color: #067647; }
.evidence-tag.missing { background: #fef3f2; color: #b42318; }
.restore-form { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border); }
.restore-form h4 { width: 100%; margin: 0; }
.filter-item.wide { flex: 1; min-width: 200px; }
.filter-item.wide input { width: 100%; }
.filter-item select, .filter-item input { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.detail-box { background: #fafbfc; border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.exec-meta { display: grid; grid-template-columns: 110px 1fr; gap: 4px 10px; font-size: 12px; margin: 8px 0; }
.exec-meta dt { color: var(--muted); }
.exec-meta dd { margin: 0; }
.vacuum-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin: 8px 0; }
.data-table.compact th, .data-table.compact td { padding: 6px 8px; font-size: 12px; }
.data-table.compact tbody tr { cursor: pointer; }
.page-actions.wrap { flex-wrap: wrap; margin: 8px 0; }
@media (max-width: 1100px) {
  .panel-grid { grid-template-columns: 1fr; }
}
</style>
