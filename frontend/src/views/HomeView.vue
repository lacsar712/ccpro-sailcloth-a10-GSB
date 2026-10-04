<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const lofts = ref([])
const rolls = ref([])
const dips = ref([])
const stickers = ref([])
const error = ref('')
const panelError = ref('')
const selectedId = ref(null)
const panelBusy = ref(false)
const cureBusyId = ref(null)
const cureDrafts = reactive({})

const statusLabel = { raw: '原布', dipping: '浸渍中', cured: '已固化' }

const dipForm = reactive({
  startedAt: '',
  resinPct: 28,
  cureHours: '',
  notes: '',
})

function localNow() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

function errMsg(e, fallback) {
  const d = e.response?.data
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  for (const key of ['cureHours', 'status', 'stopDate', 'nonFieldErrors']) {
    const v = d[key]
    if (Array.isArray(v) && v.length) return String(v[0])
    if (typeof v === 'string') return v
  }
  return fallback
}

const selected = computed(() => rolls.value.find((r) => r.id === selectedId.value) || null)

const stickerByLoft = computed(() => {
  const map = new Map()
  for (const s of stickers.value) {
    if (!s.voidedAt) map.set(s.loftId, s)
  }
  return map
})

const selectedSticker = computed(() => {
  if (!selected.value) return null
  return stickerByLoft.value.get(selected.value.loftId) || null
})

const rollsByLoft = computed(() => {
  return lofts.value.map((loft) => ({
    loft,
    rolls: rolls.value.filter((r) => r.loftId === loft.id),
  }))
})

const selectedDips = computed(() => {
  if (!selectedId.value) return []
  return dips.value.filter((d) => d.rollId === selectedId.value)
})

const recentFeed = computed(() => dips.value.slice(0, 12))

async function load() {
  error.value = ''
  try {
    const [l, r, d, s] = await Promise.all([
      api.get('/lofts/'),
      api.get('/rolls/'),
      api.get('/dips/'),
      api.get('/stickers/', { params: { current: 1 } }),
    ])
    lofts.value = l.data.results || l.data
    rolls.value = r.data.results || r.data
    dips.value = d.data.results || d.data
    stickers.value = s.data.results || s.data
    for (const dip of dips.value) {
      cureDrafts[dip.id] = dip.cureHours ?? ''
    }
  } catch {
    error.value = '晾晒架加载失败'
  }
}

function openRoll(roll) {
  selectedId.value = roll.id
  panelError.value = ''
  dipForm.startedAt = localNow()
  dipForm.resinPct = 28
  dipForm.cureHours = ''
  dipForm.notes = ''
}

function closePanel() {
  selectedId.value = null
  panelError.value = ''
}

async function setStatus(status) {
  if (!selected.value) return
  panelError.value = ''
  panelBusy.value = true
  try {
    await api.patch(`/rolls/${selected.value.id}/`, { status })
    await load()
  } catch (e) {
    panelError.value = errMsg(e, '状态更新失败（标「已固化」需最近浸渍固化时长 ≥ 12 小时）')
  } finally {
    panelBusy.value = false
  }
}

async function logDip() {
  if (!selected.value) return
  panelError.value = ''
  panelBusy.value = true
  try {
    await api.post('/dips/', {
      rollId: selected.value.id,
      startedAt: new Date(dipForm.startedAt).toISOString(),
      resinPct: dipForm.resinPct,
      cureHours:
        dipForm.cureHours === '' || dipForm.cureHours === null
          ? null
          : dipForm.cureHours,
      notes: dipForm.notes,
    })
    if (selected.value.status === 'raw') {
      try {
        await api.patch(`/rolls/${selected.value.id}/`, { status: 'dipping' })
      } catch {
        /* 浸渍已记；状态跟进失败不阻断 */
      }
    }
    dipForm.cureHours = ''
    dipForm.notes = ''
    dipForm.startedAt = localNow()
    await load()
  } catch (e) {
    panelError.value = errMsg(e, '登记浸渍失败')
  } finally {
    panelBusy.value = false
  }
}

async function saveCureHours(dip) {
  panelError.value = ''
  cureBusyId.value = dip.id
  try {
    const raw = cureDrafts[dip.id]
    await api.patch(`/dips/${dip.id}/`, {
      cureHours: raw === '' || raw === null ? null : raw,
    })
    await load()
  } catch (e) {
    panelError.value = errMsg(e, '保存固化时长失败')
  } finally {
    cureBusyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="rack-page">
    <header class="rack-head">
      <div>
        <h1>帆布间晾晒架</h1>
        <p class="sub">
          按帆布间挂卷；点选布卷登记浸渍或标固化。固化规则：最近浸渍时长 ≥ 12 小时；
          补写/改写时长还须该间湿度计贴纸在止日内。
        </p>
      </div>
      <button class="btn secondary" type="button" @click="load">刷新架面</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="rack-floor">
      <section
        v-for="group in rollsByLoft"
        :key="group.loft.id"
        class="loft-bay"
      >
        <div class="bay-rail">
          <span class="bay-name">{{ group.loft.name }}</span>
          <span class="bay-meta">{{ group.loft.location || '工位' }} · {{ group.rolls.length }} 卷</span>
          <span v-if="stickerByLoft.get(group.loft.id)" class="bay-meta">
            贴纸止日 {{ stickerByLoft.get(group.loft.id).stopDate }}<template v-if="stickerByLoft.get(group.loft.id).isExpired">（已过）</template>
          </span>
          <span v-else class="bay-meta">无现行贴纸</span>
        </div>
        <div class="peg-row">
          <button
            v-for="roll in group.rolls"
            :key="roll.id"
            type="button"
            class="roll-chip"
            :class="[
              'chip-' + roll.status,
              { 'is-selected': selectedId === roll.id },
            ]"
            @click="openRoll(roll)"
          >
            <span class="peg" aria-hidden="true" />
            <span class="hang-tag" :class="'tag-' + roll.status">
              {{ statusLabel[roll.status] || roll.status }}
            </span>
            <span class="chip-code">{{ roll.rollCode }}</span>
            <span class="chip-gsm">{{ roll.fabricWeightGsm }} gsm</span>
          </button>
          <p v-if="!group.rolls.length" class="empty-bay">此间暂无布卷</p>
        </div>
      </section>
      <p v-if="!lofts.length && !error" class="hint">尚无帆布间数据</p>
    </div>

    <section class="dip-feed panel">
      <h2 class="feed-title">浸渍流水</h2>
      <p class="hint" style="margin: 0 0 12px">架下次要信息流；主操作在右侧布卷面板完成。</p>
      <ul v-if="recentFeed.length" class="feed-list">
        <li v-for="row in recentFeed" :key="row.id">
          <strong>{{ row.rollCode }}</strong>
          <span class="feed-loft">{{ row.loftName }}</span>
          <span>{{ new Date(row.startedAt).toLocaleString() }}</span>
          <span>树脂 {{ row.resinPct }}%</span>
          <span>固化 {{ row.cureHours ?? '—' }} h</span>
        </li>
      </ul>
      <p v-else class="hint" style="margin:0">暂无浸渍记录</p>
    </section>

    <div
      v-if="selected"
      class="drawer-backdrop"
      @click.self="closePanel"
    />
    <aside v-if="selected" class="roll-drawer" aria-label="布卷操作">
      <header class="drawer-head">
        <div>
          <p class="drawer-kicker">{{ selected.loftName }}</p>
          <h2>{{ selected.rollCode }}</h2>
        </div>
        <button class="btn secondary" type="button" @click="closePanel">关闭</button>
      </header>

      <div class="drawer-status">
        <span class="hang-tag" :class="'tag-' + selected.status">
          {{ statusLabel[selected.status] }}
        </span>
        <span class="hint">{{ selected.fabricWeightGsm }} gsm</span>
      </div>

      <p v-if="selectedSticker" class="hint">
        湿度计贴纸：{{ selectedSticker.instrumentNo }} · 止日 {{ selectedSticker.stopDate }}
        <template v-if="selectedSticker.isExpired">（已过止日，禁止补写/改写时长）</template>
      </p>
      <p v-else class="hint">湿度计贴纸：本间无现行贴纸，禁止补写/改写时长</p>

      <p v-if="selected.notes" class="hint">{{ selected.notes }}</p>
      <p v-if="panelError" class="error">{{ panelError }}</p>

      <div class="drawer-actions">
        <button
          class="btn secondary"
          type="button"
          :disabled="panelBusy || selected.status === 'raw'"
          @click="setStatus('raw')"
        >
          标为原布
        </button>
        <button
          class="btn secondary"
          type="button"
          :disabled="panelBusy || selected.status === 'dipping'"
          @click="setStatus('dipping')"
        >
          标为浸渍中
        </button>
        <button
          class="btn"
          type="button"
          :disabled="panelBusy || selected.status === 'cured'"
          @click="setStatus('cured')"
        >
          标为已固化
        </button>
      </div>

      <form class="drawer-form" @submit.prevent="logDip">
        <h3>登记浸渍</h3>
        <label>开始时间
          <input v-model="dipForm.startedAt" type="datetime-local" required />
        </label>
        <label>树脂 %
          <input v-model.number="dipForm.resinPct" type="number" step="0.1" required />
        </label>
        <label>固化时长 h（可空；留空不看贴纸）
          <input v-model="dipForm.cureHours" type="number" step="0.1" />
        </label>
        <label>备注
          <input v-model="dipForm.notes" />
        </label>
        <button class="btn" type="submit" :disabled="panelBusy">写入浸渍记录</button>
      </form>

      <div class="drawer-history">
        <h3>本卷浸渍 · 补写/改写时长</h3>
        <ul v-if="selectedDips.length" class="feed-list compact">
          <li v-for="row in selectedDips" :key="row.id">
            <span>{{ new Date(row.startedAt).toLocaleString() }}</span>
            <span>{{ row.resinPct }}%</span>
            <input
              v-model="cureDrafts[row.id]"
              class="cure-input"
              type="number"
              step="0.1"
              min="0"
              placeholder="时长 h"
            />
            <button
              class="btn secondary"
              type="button"
              :disabled="cureBusyId === row.id"
              @click="saveCureHours(row)"
            >
              保存时长
            </button>
          </li>
        </ul>
        <p v-else class="hint" style="margin:0">本卷尚无浸渍</p>
      </div>
    </aside>
  </div>
</template>
