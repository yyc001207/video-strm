<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, FolderAdd, Plus } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListTask } from '@/types/openlist'
import DirTreePanel from './DirTreePanel.vue'

const store = useOpenlistStore()

const list = ref<OpenListTask[]>([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const serverFilter = ref<number | null>(null)
const selectedIds = ref<number[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  server_id: null as number | null,
  name: '',
  output_dir: '',
  process_path: '',
  pause_count: null as number | null,
  pause_time: '' as string
})

async function load() {
  loading.value = true
  try {
    // 任务与全局配置并行加载：配置用于取服务器列表与前缀
    const [tasksRes] = await Promise.all([
      openlistApi.listTasks(keyword.value || undefined, serverFilter.value),
      store.fetchConfig()
    ])
    list.value = tasksRes.data.list
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  await load()
}

function openCreate() {
  editingId.value = null
  form.server_id = null
  form.name = ''
  form.output_dir = ''
  form.process_path = ''
  form.pause_count = null
  form.pause_time = ''
  dialogVisible.value = true
}

function openEdit(row: OpenListTask) {
  editingId.value = row.id
  form.server_id = row.server_id
  form.name = row.name
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
}

async function handleSave() {
  if (form.server_id == null) {
    ElMessage.warning('请选择任务所属服务器')
    return
  }
  if (!form.name.trim() || !form.output_dir.trim() || !form.process_path.trim()) {
    ElMessage.warning('请填写任务名称、输出目录与处理路径')
    return
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      server_id: form.server_id,
      name: form.name.trim(),
      output_dir: form.output_dir.trim(),
      process_path: form.process_path.trim()
    }
    // 限流字段：留空表示使用全局配置（不提交 / 置 null）
    if (form.pause_count != null) payload.pause_count = form.pause_count
    if (form.pause_time.trim()) payload.pause_time = form.pause_time.trim()
    if (editingId.value != null) {
      await openlistApi.updateTask(editingId.value, payload)
    } else {
      await openlistApi.createTask(payload as { server_id: number; name: string; output_dir: string; process_path: string })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: OpenListTask) {
  try {
    await ElMessageBox.confirm(`确认删除任务「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await openlistApi.deleteTask(row.id)
  ElMessage.success('已删除')
  await Promise.all([load(), store.fetchTasks()])
}

async function handleBatchDelete() {
  const count = selectedIds.value.length
  if (count === 0) {
    ElMessage.warning('请先选择要删除的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${count} 个任务？此操作不可恢复。`, '批量删除', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await openlistApi.batchDeleteTasks(selectedIds.value)
    ElMessage.success(`已删除 ${count} 个任务`)
    selectedIds.value = []
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  }
}

async function handleCopy(row: OpenListTask) {
  // 复制：仅带入用户可编辑参数（排除 id 等系统自动生成字段），不立即新建
  editingId.value = null
  form.server_id = row.server_id
  form.name = `${row.name} - 复制`
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
}

// ---------- 快速添加（按目录批量生成任务配置） ----------

const quickDialogVisible = ref(false)
const quickServerId = ref<number | null>(null)
const quickParentDir = ref('')
const quickSelected = ref<string[]>([])
const quickCreating = ref(false)
const quickPauseCount = ref<number | null>(null)
const quickPauseTime = ref('')
// 快速新增父级目录子对话框
const quickParentDialogVisible = ref(false)
const quickParentSaving = ref(false)
const quickNewDirs = ref('')

const quickServerOptions = computed(() => store.servers.filter(s => s.is_active))
const quickServer = computed(() => quickServerOptions.value.find(s => s.id === quickServerId.value))
const quickParentOptions = computed(() => quickServer.value?.parent_dirs ?? [])

/** 任务名称：季文件夹（Season 01 / S01 / Season 1 等）→「上级文件夹名S季号」，其余取目录名。 */
function buildTaskName(path: string): string {
  const parts = path.split('/').filter(Boolean)
  const base = parts[parts.length - 1] ?? ''
  // 匹配季文件夹：Season 01 / season2 / S01 / s3（不区分大小写），季号原样保留
  const seasonMatch = /^(?:season\s*|s)(\d+)$/i.exec(base)
  if (seasonMatch) {
    const parent = parts[parts.length - 2]
    if (parent) return `${parent}S${seasonMatch[1]}`
  }
  return base
}

/** 输出目录推导：全局「输出目录前缀」+（可选父级目录 + ）相对父级目录的路径。
 * 带父级目录：以父级目录开头（如 /emby/电视剧）；不带：以一级子目录开头（如 /电视剧）。
 * 前缀空则以 / 开头（收敛到 output/ 下）。
 */
function deriveQuickOutputDir(parentDir: string, path: string, withParent: boolean): string {
  const parentStripped = parentDir.replace(/^\/+/, '').replace(/\/+$/, '')
  let rel = path
  if (parentStripped && path.startsWith(parentStripped)) {
    rel = path.slice(parentStripped.length).replace(/^\/+/, '')
  }
  if (!rel) rel = path
  const relClean = rel.replace(/^\/+/, '')
  const base = withParent && parentStripped ? `${parentStripped}/${relClean}` : relClean
  const prefix = (store.config?.output_dir_prefix ?? '').trim().replace(/\/+$/, '')
  return prefix ? `${prefix}/${base}` : `/${base}`
}

/** 勾选目录 → 将创建的任务配置预览（可包含父级目录本身）。 */
const quickIncludeParent = ref(false)
/** 输出目录是否带父级目录（默认不带，以一级子目录开头）。 */
const quickWithParent = ref(false)
const quickPreview = computed(() => {
  const items = quickSelected.value.map(path => ({
    path,
    name: buildTaskName(path),
    process_path: `/${path.replace(/^\/+/, '')}`,
    output_dir: deriveQuickOutputDir(quickParentDir.value, path, quickWithParent.value)
  }))
  // 勾选「包含父级目录」时，把父级目录本身也作为一条任务配置（置顶）
  // 输出目录默认留空，用单个斜杠 / 表示（父级作为根，输出收敛到 output/ 下）
  if (quickIncludeParent.value && quickParentDir.value) {
    const parentPath = quickParentDir.value
    if (!items.some(i => i.path === parentPath)) {
      items.unshift({
        path: parentPath,
        name: buildTaskName(parentPath),
        process_path: `/${parentPath.replace(/^\/+/, '')}`,
        output_dir: '/'
      })
    }
  }
  return items
})

function openQuickAdd() {
  quickDialogVisible.value = true
  quickSelected.value = []
  quickIncludeParent.value = false
  quickWithParent.value = false
  quickPauseCount.value = null
  quickPauseTime.value = ''
  if (quickServerOptions.value.length > 0) {
    quickServerId.value = quickServerOptions.value[0].id
  } else {
    quickServerId.value = null
    quickParentDir.value = ''
  }
}

// 切换服务器：父级目录重置为第一个
watch(quickServerId, () => {
  quickParentDir.value = quickParentOptions.value[0] ?? ''
})

// 切换父级目录：清空已选目录
watch(quickParentDir, () => {
  quickSelected.value = []
})

/** 预览中删除一条：更新数据源（树勾选由 DirTreePanel 的 watch(selected) 自动同步）。 */
function removeQuickPreview(path: string) {
  // 删除的是"父级目录本身"那条 → 取消「包含父级目录」
  if (quickIncludeParent.value && path === quickParentDir.value) {
    quickIncludeParent.value = false
    return
  }
  quickSelected.value = quickSelected.value.filter(p => p !== path)
}

/** 批量创建任务配置：勾选几个目录就创建几条。 */
async function handleQuickAdd() {
  if (quickPreview.value.length === 0) {
    ElMessage.warning('请先在目录树中勾选目录')
    return
  }
  quickCreating.value = true
  try {
    if (quickServerId.value == null) {
      ElMessage.warning('请先选择服务器')
      return
    }
    const payloads = quickPreview.value.map(item => {
      const payload: Record<string, unknown> = {
        server_id: quickServerId.value,
        name: item.name,
        process_path: item.process_path,
        output_dir: item.output_dir
      }
      // 限流字段：留空表示使用全局配置（不提交）
      if (quickPauseCount.value != null) payload.pause_count = quickPauseCount.value
      if (quickPauseTime.value.trim()) payload.pause_time = quickPauseTime.value.trim()
      return payload
    })
    await Promise.all(payloads.map(p => openlistApi.createTask(p as { server_id: number; name: string; process_path: string; output_dir: string })))
    ElMessage.success(`已添加 ${payloads.length} 条任务配置`)
    quickDialogVisible.value = false
    quickSelected.value = []
    await Promise.all([load(), store.fetchTasks()])
  } catch {
    /* 拦截器提示 */
  } finally {
    quickCreating.value = false
  }
}

// ---------- 快速新增父级目录 ----------

function openQuickAddParentDir() {
  quickNewDirs.value = ''
  quickParentDialogVisible.value = true
}

/** 解析父级目录输入（每行一个，去空白去重）。 */
function parseParentDirs(text: string): string[] {
  const dirs: string[] = []
  for (const line of text.split('\n')) {
    const path = line.trim()
    if (path && !dirs.includes(path)) dirs.push(path)
  }
  return dirs
}

/** 快速新增父级目录：追加到当前服务器，校验通过后自动选中新增的第一个。 */
async function handleQuickAddParentDir() {
  const serverId = quickServerId.value
  if (serverId == null) {
    ElMessage.warning('请先选择服务器')
    return
  }
  const newDirs = parseParentDirs(quickNewDirs.value)
  if (newDirs.length === 0) {
    ElMessage.warning('请输入父级目录')
    return
  }
  quickParentSaving.value = true
  try {
    await openlistApi.addServerParentDirs(serverId, newDirs)
    await store.fetchConfig()
    quickParentDir.value = newDirs[0]
    quickParentDialogVisible.value = false
    quickNewDirs.value = ''
    ElMessage.success(`已新增 ${newDirs.length} 个父级目录`)
  } catch {
    /* 拦截器提示 */
  } finally {
    quickParentSaving.value = false
  }
}

onMounted(async () => {
  await load()
})

defineExpose({ reload: load })
</script>

<template>
  <div class="task-manage">
    <el-card shadow="never" class="task-manage__card">
      <template #header>
        <div class="task-manage__header">
          <span>任务配置</span>
          <div class="task-manage__actions">
            <el-select
              v-model="serverFilter"
              placeholder="全部服务器"
              clearable
              class="task-manage__server-filter"
              @change="handleSearch"
            >
              <el-option
                v-for="server in store.servers"
                :key="server.id"
                :label="server.name || server.server_url"
                :value="server.id"
              />
            </el-select>
            <el-input
              v-model="keyword"
              placeholder="任务名称关键字"
              clearable
              class="task-manage__keyword"
              @keyup.enter="handleSearch"
              @clear="handleSearch"
            />
            <el-button type="danger" plain :disabled="selectedIds.length === 0" @click="handleBatchDelete">
              批量删除{{ selectedIds.length > 0 ? `（${selectedIds.length}）` : '' }}
            </el-button>
            <el-button type="primary" plain :icon="FolderAdd" @click="openQuickAdd">快速添加</el-button>
            <el-button type="primary" :icon="Plus" @click="openCreate">新建任务</el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="list"
        row-key="id"
        height="100%"
        class="task-manage__table"
        @selection-change="rows => (selectedIds = rows.map(r => r.id))"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column label="编号" prop="id" width="80" />
        <el-table-column label="任务名称" prop="name" min-width="150" show-overflow-tooltip />
        <el-table-column label="服务器" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.server_name || row.server_url || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="处理路径" prop="process_path" min-width="190" show-overflow-tooltip />
        <el-table-column label="输出目录" prop="output_dir" min-width="190" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary"  @click="handleCopy(row)">复制</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId != null ? '编辑任务' : '新建任务'" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="所属服务器">
          <el-select v-model="form.server_id" placeholder="请选择任务所属服务器" class="task-manage__server-select">
            <el-option
              v-for="server in store.servers"
              :key="server.id"
              :label="server.name || server.server_url"
              :value="server.id"
            />
          </el-select>
          <div class="task-manage__remark">任务强关联服务器，执行时只能在该服务器上运行</div>
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="如：TV 剧集" maxlength="128" />
        </el-form-item>
        <el-form-item label="处理路径">
          <el-input v-model="form.process_path" placeholder="如：/电视剧" maxlength="512" />
        </el-form-item>
        <el-form-item label="输出目录">
          <el-input v-model="form.output_dir" placeholder="如：/tv" maxlength="512" />
        </el-form-item>
        <el-form-item label="限流间隔">
          <el-input-number v-model="form.pause_count" :min="1" :max="100000" placeholder="用全局" class="task-manage__pause-count" />
          <div class="task-manage__remark">留空则使用全局配置；每隔 N 个文件暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停">
          <el-input v-model="form.pause_time" placeholder="用全局，如 0,3,5" maxlength="512" />
          <div class="task-manage__remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 快速添加：按目录批量生成任务配置（抽屉，便于上下滚动） -->
    <el-drawer
      v-model="quickDialogVisible"
      title="快速添加任务配置（按目录）"
      size="800px"
      destroy-on-close
      class="task-manage__quick-drawer"
    >
      <el-form label-width="90px">
        <el-form-item label="选择服务器">
          <el-select v-model="quickServerId" placeholder="请选择服务器配置" class="task-manage__quick-select">
            <el-option
              v-for="server in quickServerOptions"
              :key="server.id"
              :label="server.name || server.server_url"
              :value="server.id"
            />
          </el-select>
          <span v-if="!quickServerOptions.length" class="task-manage__remark">请先在「全局配置」新增服务器</span>
        </el-form-item>
        <el-form-item label="父级目录">
          <div class="task-manage__parent-row">
            <el-select v-model="quickParentDir" placeholder="请选择父级目录" class="task-manage__quick-select">
              <el-option v-for="dir in quickParentOptions" :key="dir" :label="dir" :value="dir" />
            </el-select>
            <el-button :icon="Plus" plain @click="openQuickAddParentDir">新增</el-button>
          </div>
          <span v-if="quickServer && !quickParentOptions.length" class="task-manage__remark">
            该服务器未配置父级目录，可点击「新增」快速添加
          </span>
        </el-form-item>
        <el-form-item label="选择目录">
          <DirTreePanel v-model="quickSelected" :server-id="quickServerId" :parent-dir="quickParentDir" />
          <div class="task-manage__include-parent">
            <el-checkbox v-model="quickIncludeParent" :disabled="!quickParentDir">
              同时把父级目录「{{ quickParentDir || '—' }}」本身作为一条任务配置
            </el-checkbox>
          </div>
          <div class="task-manage__include-parent">
            <el-checkbox v-model="quickWithParent" :disabled="!quickParentDir">
              输出目录带父级目录（选中以父级目录开头，如 /emby/电视剧；不选以一级子目录开头，如 /电视剧）
            </el-checkbox>
          </div>
          <div class="task-manage__remark">勾选目录后点击下方「添加任务配置」，每个目录生成一条任务配置</div>
        </el-form-item>
        <el-form-item label="限流间隔">
          <el-input-number v-model="quickPauseCount" :min="1" :max="100000" placeholder="用全局" class="task-manage__pause-count" />
          <div class="task-manage__remark">留空则使用全局配置；每隔 N 个文件暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停">
          <el-input v-model="quickPauseTime" placeholder="用全局，如 0,3,5" maxlength="512" />
          <div class="task-manage__remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
        <el-form-item v-if="quickPreview.length" label="添加预览">
          <el-table :data="quickPreview" size="small" max-height="220" class="task-manage__quick-table">
            <el-table-column label="任务名称" prop="name" min-width="110" show-overflow-tooltip />
            <el-table-column label="处理路径" prop="process_path" min-width="150" show-overflow-tooltip />
            <el-table-column label="输出目录" prop="output_dir" min-width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="70" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" @click="removeQuickPreview(row.path)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="task-manage__drawer-footer">
          <el-button @click="quickDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="quickCreating" :disabled="quickPreview.length === 0" @click="handleQuickAdd">
            添加 {{ quickPreview.length }} 条任务配置
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 快速新增父级目录 -->
    <el-dialog v-model="quickParentDialogVisible" title="快速新增父级目录" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="父级目录">
          <el-input
            v-model="quickNewDirs"
            type="textarea"
            :rows="4"
            placeholder="每行一个目录，自动补全 / 前缀，如：&#10;emby/动漫&#10;音乐"
          />
          <div class="task-manage__remark">保存时自动校验格式、存在性与读写权限，校验通过后自动缓存一级子目录并选中</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="quickParentDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="quickParentSaving" @click="handleQuickAddParentDir">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.task-manage {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;

  &__card {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;

    :deep(.el-card__body) {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  &__keyword {
    width: 180px;
  }

  &__server-filter {
    width: 180px;
  }

  &__server-select {
    width: 100%;
  }

  &__quick-select {
    width: 340px;
  }

  &__parent-row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }

  &__include-parent {
    margin: 6px 0 2px;
  }

  &__drawer-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }

  &__quick-table {
    width: 100%;
  }

  &__table {
    flex: 1;
    min-height: 0;
  }

  &__pause-count {
    width: 200px;
  }

  &__remark {
    font-size: var(--el-font-size-extra-small);
    color: var(--el-text-color-secondary);
    margin-top: 2px;
  }
}
</style>
