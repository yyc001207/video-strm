<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {  Edit, Plus } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import type { OpenListConfig, OpenListServer } from '@/types/openlist'

const loading = ref(false)
const config = ref<OpenListConfig | null>(null)

// 服务器弹窗
const serverDialogVisible = ref(false)
const editingServerId = ref<number | null>(null)
const savingServer = ref(false)
const serverForm = reactive({ name: '', server_url: '', token: '' })

// 全局配置弹窗
const configDialogVisible = ref(false)
const savingConfig = ref(false)
const configForm = reactive({ video_formats: '', subtitle_formats: '', max_concurrent: 1, pause_count: 50, pause_time: '0,3,5', disable_ssl_verify: false, log_to_db: false })

async function load() {
  loading.value = true
  try {
    const res = await openlistApi.getConfig()
    config.value = res.data
  } finally {
    loading.value = false
  }
}

function openCreateServer() {
  editingServerId.value = null
  serverForm.name = ''
  serverForm.server_url = ''
  serverForm.token = ''
  serverDialogVisible.value = true
}

function openEditServer(server: OpenListServer) {
  editingServerId.value = server.id
  serverForm.name = server.name ?? ''
  serverForm.server_url = server.server_url
  // 编辑时不回填 Token：留空表示保持原 Token 不变
  serverForm.token = ''
  serverDialogVisible.value = true
}

async function handleSaveServer() {
  if (!serverForm.server_url.trim()) {
    ElMessage.warning('请填写服务器地址')
    return
  }
  savingServer.value = true
  try {
    if (editingServerId.value != null) {
      await openlistApi.updateServer(editingServerId.value, {
        name: serverForm.name.trim() || undefined,
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined
      })
    } else {
      await openlistApi.createServer({
        name: serverForm.name.trim() || undefined,
        server_url: serverForm.server_url.trim(),
        token: serverForm.token.trim() || undefined
      })
    }
    ElMessage.success('服务器配置已保存')
    serverDialogVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    savingServer.value = false
  }
}

async function handleDeleteServer(server: OpenListServer) {
  try {
    await ElMessageBox.confirm(`确认删除服务器「${server.name ?? server.server_url}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await openlistApi.deleteServer(server.id)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 拦截器提示 */
  }
}

function openEditConfig() {
  if (!config.value) return
  configForm.video_formats = config.value.video_formats ?? ''
  configForm.subtitle_formats = config.value.subtitle_formats ?? ''
  configForm.max_concurrent = config.value.max_concurrent || 1
  configForm.pause_count = config.value.pause_count || 50
  configForm.pause_time = config.value.pause_time ?? '0,3,5'
  configForm.disable_ssl_verify = config.value.disable_ssl_verify ?? false
  configForm.log_to_db = config.value.log_to_db ?? false
  configDialogVisible.value = true
}

async function handleSaveConfig() {
  savingConfig.value = true
  try {
    await openlistApi.updateConfig({
      video_formats: configForm.video_formats.trim(),
      subtitle_formats: configForm.subtitle_formats.trim(),
      max_concurrent: configForm.max_concurrent,
      pause_count: configForm.pause_count,
      pause_time: configForm.pause_time.trim(),
      disable_ssl_verify: configForm.disable_ssl_verify,
      log_to_db: configForm.log_to_db
    })
    ElMessage.success('全局配置已保存')
    configDialogVisible.value = false
    await load()
  } catch {
    /* 拦截器提示 */
  } finally {
    savingConfig.value = false
  }
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="global-config">
    <el-card v-loading="loading" shadow="never" class="global-config__card">
      <template #header>
        <div class="global-config__header">
          <span>服务器配置（支持多个）</span>
          <el-button type="primary" :icon="Plus" @click="openCreateServer">新增服务器</el-button>
        </div>
      </template>

      <el-table v-if="config?.servers?.length" :data="config.servers" row-key="id" class="global-config__table">
        <el-table-column label="名称" min-width="140">
          <template #default="{ row }">{{ row.name || '未命名' }}</template>
        </el-table-column>
        <el-table-column label="服务器地址" prop="server_url" min-width="240" show-overflow-tooltip />
        <el-table-column label="Token" width="100">
          <template #default="{ row }">
            <el-tag :type="row.has_token ? 'success' : 'danger'" effect="light" size="small">
              {{ row.has_token ? '已设置' : '未设置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" effect="light" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditServer(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDeleteServer(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无服务器，点击「新增服务器」配置 OpenList 服务器" />
    </el-card>

    <el-card shadow="never" class="global-config__card">
      <template #header>
        <div class="global-config__header">
          <span>全局配置（所有任务共享）</span>
          <el-button type="primary" :icon="Edit" :disabled="!config" @click="openEditConfig">编辑</el-button>
        </div>
      </template>

      <div class="global-config__view">
        <el-descriptions v-if="config" :column="1" border class="global-config__desc">
          <el-descriptions-item label="同时执行任务个数">{{ config.max_concurrent || 1 }}</el-descriptions-item>
          <el-descriptions-item label="视频格式">{{ config.video_formats || '—' }}</el-descriptions-item>
          <el-descriptions-item label="字幕格式">{{ config.subtitle_formats || '—' }}</el-descriptions-item>
          <el-descriptions-item label="限流间隔文件数">{{ config.pause_count || 50 }}</el-descriptions-item>
          <el-descriptions-item label="限流暂停时间">{{ config.pause_time || '0,3,5' }}</el-descriptions-item>
          <el-descriptions-item label="禁用 SSL 验证">
            <el-tag :type="config.disable_ssl_verify ? 'warning' : 'success'" effect="light" size="small">
              {{ config.disable_ssl_verify ? '开启（不校验）' : '关闭（校验）' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="日志写入数据库">
            <el-tag :type="config.log_to_db ? 'warning' : 'success'" effect="light" size="small">
              {{ config.log_to_db ? '开启（双写）' : '关闭（仅写文件）' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-dialog v-model="serverDialogVisible" :title="editingServerId != null ? '编辑服务器' : '新增服务器'" width="520px"
      destroy-on-close>
      <el-form label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="serverForm.name" placeholder="如：主服务器 / 备服务器" maxlength="128" />
        </el-form-item>
        <el-form-item label="服务器地址">
          <el-input v-model="serverForm.server_url" placeholder="http://192.168.199.238:5244" maxlength="512" />
          <div class="global-config__remark">OpenList/AList 等 API 地址</div>
        </el-form-item>
        <el-form-item label="访问 Token">
          <el-input v-model="serverForm.token" type="password" show-password autocomplete="new-password"
            :placeholder="editingServerId != null ? '已设置，留空保持不变' : '请输入 Token'" maxlength="512" />
          <div class="global-config__remark">编辑时不回填，留空表示保持原 Token 不变</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="serverDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingServer" @click="handleSaveServer">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="configDialogVisible" title="编辑全局配置" width="520px" destroy-on-close>
      <el-form label-width="130px">
        <el-form-item label="同时执行任务个数">
          <el-input-number v-model="configForm.max_concurrent" :min="1" :max="100" />
          <div class="global-config__remark">限制同时运行的任务数量，超出排队等待</div>
        </el-form-item>
        <el-form-item label="视频格式">
          <el-input v-model="configForm.video_formats" placeholder="mp4,mkv,avi,wmv,flv,mov,webm,ts" maxlength="512" />
          <div class="global-config__remark">英文逗号分隔</div>
        </el-form-item>
        <el-form-item label="字幕格式">
          <el-input v-model="configForm.subtitle_formats" placeholder="srt,ass,ssa,sub,vtt" maxlength="512" />
          <div class="global-config__remark">英文逗号分隔</div>
        </el-form-item>
        <el-form-item label="限流间隔文件数">
          <el-input-number v-model="configForm.pause_count" :min="1" :max="100000" />
          <div class="global-config__remark">每隔 N 个文件限流暂停一次</div>
        </el-form-item>
        <el-form-item label="限流暂停时间">
          <el-input v-model="configForm.pause_time" placeholder="0,3,5" maxlength="512" />
          <div class="global-config__remark">秒，逗号分隔；随机暂停其中一项；填 0 表示不限流</div>
        </el-form-item>
        <el-form-item label="禁用 SSL 验证">
          <el-switch v-model="configForm.disable_ssl_verify" />
          <div class="global-config__remark">默认关闭（校验证书）；内网自签名 HTTPS 时开启可禁用验证</div>
        </el-form-item>
        <el-form-item label="日志写入数据库">
          <el-switch v-model="configForm.log_to_db" />
          <div class="global-config__remark">默认关闭（仅写日志文件，DB 不再积累日志）；需结构化日志时开启</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="handleSaveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.global-config {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow: auto;

  &__card {
    flex-shrink: 0;
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__view {
    padding-top: 4px;
  }

  &__desc {
    max-width: 640px;
  }

  &__remark {
    font-size: var(--el-font-size-extra-small);
    color: var(--el-text-color-secondary);
    margin-top: 2px;
  }
}
</style>
