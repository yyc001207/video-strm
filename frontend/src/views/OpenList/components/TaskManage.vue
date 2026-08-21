<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, Plus } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import { useOpenlistStore } from '@/stores/openlist'
import type { OpenListPreset, OpenListTask } from '@/types/openlist'

const store = useOpenlistStore()

const list = ref<OpenListTask[]>([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const selectedIds = ref<number[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  output_dir: '',
  process_path: '',
  preset_id: null as number | null,
  pause_count: null as number | null,
  pause_time: '' as string
})

async function load() {
  loading.value = true
  try {
    // 任务、预设与全局配置并行加载：预设用于弹窗「选择预设自动填充」下拉，配置用于取前缀
    const [tasksRes] = await Promise.all([
      openlistApi.listTasks(keyword.value || undefined),
      store.fetchPresets(),
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
  form.name = ''
  form.output_dir = ''
  form.process_path = ''
  form.preset_id = null
  form.pause_count = null
  form.pause_time = ''
  dialogVisible.value = true
}

function openEdit(row: OpenListTask) {
  editingId.value = row.id
  form.name = row.name
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.preset_id = null
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
}

/** 前缀拼接：前缀为空则原样返回；路径已带此前缀则不重复拼接；否则前缀 + 去头斜杠的路径。 */
function applyPrefix(prefix: string, path: string): string {
  const p = prefix.trim().replace(/\/+$/, '')
  if (!p) return path
  if (path === p || path.startsWith(`${p}/`)) return path
  return `${p}/${path.replace(/^\/+/, '')}`
}

watch(
  () => form.preset_id,
  presetId => {
    const preset: OpenListPreset | undefined = store.presets.find(p => p.id === presetId)
    if (preset) {
      // 处理路径/输出目录按全局配置前缀拼接（默认空则保持预设路径原样，不再硬编码 emby 前缀）
      form.process_path = applyPrefix(store.config?.process_path_prefix ?? '', preset.preset_path)
      form.output_dir = applyPrefix(store.config?.output_dir_prefix ?? '', preset.preset_path)
    }
  }
)

async function handleSave() {
  if (!form.name.trim() || !form.output_dir.trim() || !form.process_path.trim()) {
    ElMessage.warning('请填写任务名称、输出目录与处理路径')
    return
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
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
      await openlistApi.createTask(payload as { name: string; output_dir: string; process_path: string })
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
  form.name = `${row.name} - 复制`
  form.output_dir = row.output_dir
  form.process_path = row.process_path
  form.preset_id = null
  form.pause_count = row.pause_count
  form.pause_time = row.pause_time ?? ''
  dialogVisible.value = true
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
        <el-table-column label="任务名称" prop="name" min-width="160" show-overflow-tooltip />
        <el-table-column label="处理路径" prop="process_path" min-width="200" show-overflow-tooltip />
        <el-table-column label="输出目录" prop="output_dir" min-width="200" show-overflow-tooltip />
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
        <el-form-item label="任务名称">
          <el-input v-model="form.name" placeholder="如：TV 剧集" maxlength="128" />
        </el-form-item>
        <el-form-item label="选择预设">
          <el-select v-model="form.preset_id" placeholder="选择预设自动填充" clearable class="task-manage__preset">
            <el-option v-for="p in store.presets" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <div class="task-manage__remark">选择后自动填充处理路径与输出目录（前缀取自全局配置，默认空）</div>
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

  &__table {
    flex: 1;
    min-height: 0;
  }

  &__preset {
    width: 100%;
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
