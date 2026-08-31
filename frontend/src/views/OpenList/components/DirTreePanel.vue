<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'

import { openlistApi } from '@/api/openlist'
import type { ServerDirItem } from '@/types/openlist'

/**
 * 目录选择面板：el-tree 懒加载逐层下钻 + 本地模糊搜索 + 缓存刷新。
 * - 搜索只匹配已加载（已缓存）的目录，不请求服务器
 * - 通过 v-model 双向绑定勾选的目录路径数组（任意层级可单独勾选）
 */

const props = defineProps<{
  serverId: number | null
  parentDir: string
}>()

const selected = defineModel<string[]>({ default: () => [] })

const treeKey = ref(0)
const treeRef = ref<{ getCheckedNodes(leafOnly?: boolean): Array<{ path: string }>; setChecked(key: string, checked: boolean): void } | null>(null)

interface DirTreeNode {
  name: string
  path: string
  isLeaf: boolean
}

/** 已加载（已缓存）的目录节点：path -> {name, path}，用于本地模糊搜索。 */
const loadedNodes = new Map<string, { name: string; path: string }>()

// 服务器或父级目录变化：清空勾选、清空已缓存节点、重载目录树
watch([() => props.serverId, () => props.parentDir], () => {
  selected.value = []
  loadedNodes.clear()
  searchKeyword.value = ''
  searchResults.value = []
  treeKey.value += 1
})

/** 勾选集合变化（树勾选 / 搜索选择 / 外部移除）时同步树的勾选状态。
 * - 新增的路径（如搜索点击选择）：节点已加载则勾选显示
 * - 移除的路径（如预览删除、标签移除）：取消树勾选
 * setChecked 对未加载节点为安全空操作，幂等，不会与树自身 @check 冲突。
 */
watch(
  selected,
  (next, prev) => {
    const prevSet = new Set(prev ?? [])
    const nextSet = new Set(next)
    for (const path of prevSet) {
      if (!nextSet.has(path)) {
        try {
          treeRef.value?.setChecked(path, false)
        } catch {
          /* 忽略 */
        }
      }
    }
    for (const path of nextSet) {
      if (!prevSet.has(path)) {
        try {
          treeRef.value?.setChecked(path, true)
        } catch {
          /* 忽略 */
        }
      }
    }
  },
  { deep: true }
)

/** 缓存优先的 dirs 接口拉取某路径下一级子目录，转成树节点并记录到本地缓存。 */
async function fetchDirNodes(path: string): Promise<DirTreeNode[]> {
  if (props.serverId == null || !path) return []
  try {
    const res = await openlistApi.getServerDirs(props.serverId, path)
    const nodes = res.data.list.map((d: ServerDirItem) => ({
      name: d.name,
      path: d.path,
      isLeaf: false
    }))
    for (const node of nodes) {
      loadedNodes.set(node.path, { name: node.name, path: node.path })
    }
    return nodes
  } catch {
    return []
  }
}

/** el-tree 懒加载：根节点加载父级目录的一级子目录，其余节点逐层按需加载。 */
async function loadTreeNode(node: { level: number; data?: DirTreeNode }, resolve: (nodes: DirTreeNode[]) => void) {
  const path = node.level === 0 ? props.parentDir : (node.data?.path ?? '')
  resolve(await fetchDirNodes(path))
}

function handleTreeCheck() {
  selected.value = (treeRef.value?.getCheckedNodes(false) ?? []).map(n => n.path)
}

function removeSelected(path: string) {
  // 仅更新数据源；树的勾选状态由 watch(selected) 同步取消
  selected.value = selected.value.filter(p => p !== path)
}

// ---------- 本地模糊搜索（只搜已缓存目录，不请求服务器） ----------
const searchKeyword = ref('')
const searchResults = ref<Array<{ name: string; path: string }>>([])

function handleSearchInput() {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) {
    searchResults.value = []
    return
  }
  // 模糊匹配：目录名包含关键字（不区分大小写），结果按路径排序
  searchResults.value = [...loadedNodes.values()]
    .filter(n => n.name.toLowerCase().includes(keyword))
    .sort((a, b) => a.path.localeCompare(b.path))
}

function pickSearchResult(item: { name: string; path: string }) {
  if (!selected.value.includes(item.path)) {
    selected.value = [...selected.value, item.path]
  }
  searchKeyword.value = ''
  searchResults.value = []
}

// ---------- 缓存刷新 ----------
const refreshing = ref(false)

async function handleRefresh() {
  if (props.serverId == null || !props.parentDir) return
  refreshing.value = true
  try {
    const res = await openlistApi.refreshServerDirs(props.serverId, props.parentDir)
    ElMessage.success(`目录缓存已刷新（${res.data.count} 个子目录）`)
    loadedNodes.clear()
    treeKey.value += 1
  } catch {
    /* 拦截器提示 */
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <div class="dir-tree-panel">
    <div class="dir-tree-panel__toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索已缓存目录（模糊匹配）"
        clearable
        class="dir-tree-panel__search"
        :disabled="!parentDir"
        @input="handleSearchInput"
        @clear="searchResults = []"
      />
      <el-button :loading="refreshing" :disabled="!parentDir" @click="handleRefresh">刷新缓存</el-button>
    </div>

    <div v-if="searchResults.length" class="dir-tree-panel__results">
      <div
        v-for="item in searchResults"
        :key="item.path"
        class="dir-tree-panel__result"
        @click="pickSearchResult(item)"
      >
        <el-icon class="dir-tree-panel__result-icon"><FolderOpened /></el-icon>
        <span class="dir-tree-panel__result-path">{{ item.path }}</span>
        <el-button link type="primary" size="small">选择</el-button>
      </div>
    </div>

    <div class="dir-tree-panel__tree-wrap" :class="{ 'is-disabled': !parentDir }">
      <el-tree
        v-if="parentDir"
        :key="treeKey"
        ref="treeRef"
        lazy
        :load="loadTreeNode"
        :props="{ label: 'name', children: 'children', isLeaf: 'isLeaf' }"
        node-key="path"
        show-checkbox
        check-strictly
        highlight-current
        class="dir-tree-panel__tree"
        @check="handleTreeCheck"
      />
      <el-empty v-else description="请先选择父级目录" :image-size="60" />
    </div>

    <div v-if="selected.length" class="dir-tree-panel__selected">
      <el-tag
        v-for="path in selected"
        :key="path"
        type="info"
        effect="plain"
        closable
        class="dir-tree-panel__tag"
        @close="removeSelected(path)"
      >
        {{ path }}
      </el-tag>
    </div>
  </div>
</template>

<style scoped lang="scss">
.dir-tree-panel {
  width: 100%;

  &__toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }

  &__search {
    width: 260px;
  }

  &__results {
    max-height: 180px;
    overflow: auto;
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
    margin-bottom: 8px;
  }

  &__result {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    cursor: pointer;
    transition: background-color 0.15s;

    &:hover {
      background: var(--el-fill-color-light);
    }

    & + .dir-tree-panel__result {
      border-top: 1px solid var(--el-border-color-lighter);
    }
  }

  &__result-icon {
    color: var(--el-color-primary);
    flex-shrink: 0;
  }

  &__result-path {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--el-font-size-small);
  }

  &__tree-wrap {
    max-height: 280px;
    overflow: auto;
    border: 1px solid var(--el-border-color);
    border-radius: 4px;
    padding: 4px 8px;

    &.is-disabled {
      opacity: 0.6;
      pointer-events: none;
    }
  }

  &__tree {
    --el-tree-node-hover-bg-color: var(--el-fill-color-light);
    background: transparent;
  }

  &__selected {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  &__tag {
    max-width: 100%;
  }
}
</style>
