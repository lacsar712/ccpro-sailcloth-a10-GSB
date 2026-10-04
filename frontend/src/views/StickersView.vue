<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')

const lofts = ref([])
const stickers = ref([])
const error = ref('')
const notice = ref('')
const busy = ref(false)

// 每间帆布间的粘贴/续期表单草稿
const drafts = reactive({})

function draftFor(loftId) {
  if (!drafts[loftId]) {
    drafts[loftId] = { instrumentNo: '', stopDate: '' }
  }
  return drafts[loftId]
}

const currentByLoft = computed(() => {
  const map = new Map()
  for (const s of stickers.value) {
    if (!s.voidedAt) map.set(s.loftId, s)
  }
  return map
})

const voidedStickers = computed(() => stickers.value.filter((s) => s.voidedAt))

function errMsg(e, fallback) {
  const d = e.response?.data
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  for (const key of ['stopDate', 'instrumentNo', 'loftId', 'nonFieldErrors']) {
    const v = d[key]
    if (Array.isArray(v) && v.length) return String(v[0])
    if (typeof v === 'string') return v
  }
  return fallback
}

async function load() {
  error.value = ''
  try {
    const [l, s] = await Promise.all([api.get('/lofts/'), api.get('/stickers/')])
    lofts.value = l.data.results || l.data
    stickers.value = s.data.results || s.data
    for (const loft of lofts.value) {
      const cur = currentByLoft.value.get(loft.id)
      const d = draftFor(loft.id)
      d.instrumentNo = cur ? cur.instrumentNo : d.instrumentNo
      d.stopDate = cur ? cur.stopDate : d.stopDate
    }
  } catch {
    error.value = '贴纸数据加载失败'
  }
}

async function paste(loft) {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const d = draftFor(loft.id)
    await api.post('/stickers/', {
      loftId: loft.id,
      instrumentNo: d.instrumentNo,
      stopDate: d.stopDate,
    })
    notice.value = `${loft.name} 贴纸已粘贴`
    await load()
  } catch (e) {
    error.value = errMsg(e, '粘贴失败')
  } finally {
    busy.value = false
  }
}

async function renew(loft, sticker) {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const d = draftFor(loft.id)
    await api.patch(`/stickers/${sticker.id}/`, {
      stopDate: d.stopDate,
      instrumentNo: d.instrumentNo,
    })
    notice.value = `${loft.name} 贴纸已续期`
    await load()
  } catch (e) {
    error.value = errMsg(e, '续期失败')
  } finally {
    busy.value = false
  }
}

async function voidSticker(loft, sticker) {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    await api.post(`/stickers/${sticker.id}/void/`)
    notice.value = `${loft.name} 贴纸已作废`
    await load()
  } catch (e) {
    error.value = errMsg(e, '作废失败')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1>湿度计止日贴纸</h1>
    <p class="sub">
      每间帆布间现行贴纸最多一张；止日当天仍有效，过了止日禁止给浸渍补写或改写固化时长。
      标「已固化」仍须时长满十二小时，贴纸不替代时长。
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="ok">{{ notice }}</p>
    <p v-if="!isAdmin" class="hint" style="margin-bottom: 16px">
      当前为操作工账号：可查看贴纸与填写固化时长，但粘贴、续期与作废仅管理员可办。
    </p>

    <div class="sticker-grid">
      <section v-for="loft in lofts" :key="loft.id" class="sticker-card">
        <h2>{{ loft.name }}</h2>

        <template v-if="currentByLoft.get(loft.id)">
          <div class="sticker-line">
            <span><span class="k">仪器编号</span> {{ currentByLoft.get(loft.id).instrumentNo }}</span>
            <span><span class="k">止日</span> {{ currentByLoft.get(loft.id).stopDate }}</span>
            <span><span class="k">粘贴人</span> {{ currentByLoft.get(loft.id).pastedBy }}</span>
          </div>
          <div class="sticker-line">
            <span
              class="sticker-state"
              :class="currentByLoft.get(loft.id).isExpired ? 'sticker-expired' : 'sticker-ok'"
            >
              {{ currentByLoft.get(loft.id).isExpired ? '已过止日 · 禁止写时长' : '现行有效' }}
            </span>
          </div>
        </template>
        <div v-else class="sticker-line">
          <span class="sticker-state sticker-none">无现行贴纸 · 禁止写时长</span>
        </div>

        <div v-if="isAdmin" class="sticker-actions">
          <label>仪器编号
            <input v-model="draftFor(loft.id).instrumentNo" placeholder="如 HYG-01" />
          </label>
          <label>止日
            <input v-model="draftFor(loft.id).stopDate" type="date" required />
          </label>
          <button
            v-if="currentByLoft.get(loft.id)"
            class="btn"
            type="button"
            :disabled="busy"
            @click="renew(loft, currentByLoft.get(loft.id))"
          >
            续期
          </button>
          <button
            v-else
            class="btn"
            type="button"
            :disabled="busy"
            @click="paste(loft)"
          >
            粘贴
          </button>
          <button
            v-if="currentByLoft.get(loft.id)"
            class="btn secondary"
            type="button"
            :disabled="busy"
            @click="voidSticker(loft, currentByLoft.get(loft.id))"
          >
            作废
          </button>
        </div>
      </section>
      <p v-if="!lofts.length && !error" class="hint">尚无帆布间数据</p>
    </div>

    <section v-if="voidedStickers.length" class="panel">
      <h2 class="feed-title">已作废贴纸（次要）</h2>
      <table>
        <thead>
          <tr>
            <th>帆布间</th>
            <th>仪器编号</th>
            <th>止日</th>
            <th>粘贴人</th>
            <th>作废时刻</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in voidedStickers" :key="row.id">
            <td>{{ row.loftName }}</td>
            <td>{{ row.instrumentNo }}</td>
            <td>{{ row.stopDate }}</td>
            <td>{{ row.pastedBy }}</td>
            <td>{{ new Date(row.voidedAt).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
