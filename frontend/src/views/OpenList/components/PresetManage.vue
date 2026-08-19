<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import type { OpenListPreset } from '@/types/openlist'

const list = ref<OpenListPreset[]>([])
const loading = ref(false)
const saving = ref(false)
const selectedIds = ref<number[]>([])

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', preset_path: '', sort_order: 0 })

async function load() {
  loading.value = true
  try {
    const res = await openlistApi.listPresets()
    list.value = res.data.list
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.preset_path = ''
  form.sort_order = 0
  dialogVisible.value = true
}

function openEdit(row: OpenListPreset) {
  editingId.value = row.id
  form.name = row.name
  form.preset_path = row.preset_path
  form.sort_order = row.sort_order
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim() || !form.preset_path.trim()) {
    ElMessage.warning('请填写预设名称与预设路径')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      preset_path: form.preset_path.trim(),
      sort_order: Number(form.sort_order) || 0
    }
    if (editingId.value != null) {
      await openlistApi.updatePreset(editingId.value, payload)
    } else {
      await openlistApi.createPreset(payload)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: OpenListPreset) {
  try {
    await ElMessageBox.confirm(`确认删除预设「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await openlistApi.deletePreset(row.id)
  ElMessage.success('已删除')
  await load()
}

async function handleBatchDelete() {
  const count = selectedIds.value.length
  if (count === 0) {
    ElMessage.warning('请先选择要删除的预设')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${count} 个预设？此操作不可恢复。`, '批量删除', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await openlistApi.batchDeletePresets(selectedIds.value)
    ElMessage.success(`已删除 ${count} 个预设`)
    selectedIds.value = []
    await load()
  } catch {
    /* 拦截器提示 */
  }
}

async function handleMove(row: OpenListPreset, dir: -1 | 1) {
  const index = list.value.findIndex(p => p.id === row.id)
  const target = index + dir
  if (target < 0 || target >= list.value.length) return
  const ids = list.value.map(p => p.id)
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  await openlistApi.reorderPresets(ids)
  await load()
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="preset-manage">
    <el-card shadow="never" class="preset-manage__card">
      <template #header>
        <div class="preset-manage__header">
          <span>预设配置</span>
          <div class="preset-manage__actions">
            <el-button type="danger" plain :disabled="selectedIds.length === 0" @click="handleBatchDelete">
              批量删除{{ selectedIds.length > 0 ? `（${selectedIds.length}）` : '' }}
            </el-button>
            <el-button type="primary" :icon="Plus" @click="openCreate">新建预设</el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="list"
        row-key="id"
        height="100%"
        class="preset-manage__table"
        @selection-change="rows => (selectedIds = rows.map(r => r.id))"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column label="编号" prop="id" width="80" />
        <el-table-column label="预设名称" prop="name" min-width="160" show-overflow-tooltip />
        <el-table-column label="预设路径" prop="preset_path" min-width="220" show-overflow-tooltip />
        <el-table-column label="排序值" prop="sort_order" width="100" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :disabled="row.sort_order === 0" @click="handleMove(row, -1)">
              上移
            </el-button>
            <el-button link type="primary" :disabled="row.sort_order === list.length - 1" @click="handleMove(row, 1)">
              下移
            </el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId != null ? '编辑预设' : '新建预设'" width="480px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="预设名称">
          <el-input v-model="form.name" placeholder="如：TV 剧集" maxlength="128" />
        </el-form-item>
        <el-form-item label="预设路径">
          <el-input v-model="form.preset_path" placeholder="如：/emby/电视剧" maxlength="512" />
          <div class="preset-manage__remark">将自动填充到任务的处理路径与输出目录</div>
        </el-form-item>
        <el-form-item label="排序值">
          <el-input-number v-model="form.sort_order" :min="0" />
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
.preset-manage {
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

  &__table {
    flex: 1;
    min-height: 0;
  }

  &__remark {
    font-size: var(--el-font-size-extra-small);
    color: var(--el-text-color-secondary);
    margin-top: 2px;
  }
}
</style>
