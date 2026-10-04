<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api, { errText } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const lofts = ref([])
const stickers = ref([])
const error = ref('')
const okMsg = ref('')
const busy = ref(false)

const isAdmin = computed(() => auth.user?.role === 'admin')

const pasteForm = reactive({
  loftId: null,
  instrumentNo: '',
  stopDate: '',
})
const renewForms = reactive({})

const currentByLoft = computed(() => {
  const map = {}
  for (const s of stickers.value) {
    if (!s.voidedAt) map[s.loftId] = s
  }
  return map
})

const history = computed(() => stickers.value.filter((s) => s.voidedAt))

const pastableLofts = computed(() =>
  lofts.value.filter((l) => !currentByLoft.value[l.id])
)

function todayStr() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 10)
}

function stickerState(s) {
  if (!s) return { text: '未张贴', cls: 'badge-raw' }
  if (s.stopDate < todayStr()) return { text: `已过止日（${s.stopDate}）`, cls: 'badge-expired' }
  if (s.stopDate === todayStr()) return { text: '止日当天（仍有效）', cls: 'badge-dipping' }
  return { text: '有效', cls: 'badge-cured' }
}

async function load() {
  error.value = ''
  try {
    const [l, s] = await Promise.all([api.get('/lofts/'), api.get('/stickers/')])
    lofts.value = l.data.results || l.data
    stickers.value = s.data.results || s.data
    for (const st of stickers.value) {
      if (!st.voidedAt && !renewForms[st.id]) {
        renewForms[st.id] = { stopDate: st.stopDate, instrumentNo: st.instrumentNo }
      }
    }
    if (!pasteForm.loftId && pastableLofts.value.length) {
      pasteForm.loftId = pastableLofts.value[0].id
    }
  } catch (e) {
    error.value = errText(e, '贴纸信息加载失败')
  }
}

async function paste() {
  error.value = ''
  okMsg.value = ''
  busy.value = true
  try {
    await api.post('/stickers/', {
      loftId: pasteForm.loftId,
      instrumentNo: pasteForm.instrumentNo,
      stopDate: pasteForm.stopDate,
    })
    okMsg.value = '已粘贴新贴纸'
    pasteForm.instrumentNo = ''
    pasteForm.stopDate = ''
    pasteForm.loftId = null
    await load()
  } catch (e) {
    error.value = errText(e, '粘贴失败')
  } finally {
    busy.value = false
  }
}

async function renew(sticker) {
  error.value = ''
  okMsg.value = ''
  busy.value = true
  try {
    const form = renewForms[sticker.id] || {}
    await api.post(`/stickers/${sticker.id}/renew/`, {
      stopDate: form.stopDate,
      instrumentNo: form.instrumentNo || undefined,
    })
    okMsg.value = `已续期：${sticker.loftName} 止日改为 ${form.stopDate}`
    await load()
  } catch (e) {
    error.value = errText(e, '续期失败')
  } finally {
    busy.value = false
  }
}

async function voidSticker(sticker) {
  error.value = ''
  okMsg.value = ''
  busy.value = true
  try {
    await api.post(`/stickers/${sticker.id}/void/`)
    okMsg.value = `已作废：${sticker.loftName} 的贴纸`
    await load()
  } catch (e) {
    error.value = errText(e, '作废失败')
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
      贴纸不替代「标已固化需时长满 12 小时」。仅管理员可粘贴、续期与作废。
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="okMsg" class="ok">{{ okMsg }}</p>
    <p v-if="!isAdmin" class="hint" style="margin-bottom: 16px">
      当前为操作工账号：可查看贴纸与填写固化时长，但粘贴、续期、作废仅管理员可执行。
    </p>

    <section class="panel">
      <h2 class="feed-title">各间现行贴纸</h2>
      <table>
        <thead>
          <tr>
            <th>帆布间</th>
            <th>仪器编号</th>
            <th>止日</th>
            <th>粘贴人</th>
            <th>状态</th>
            <th v-if="isAdmin">续期 / 作废</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="loft in lofts" :key="loft.id">
            <td>{{ loft.name }}</td>
            <template v-if="currentByLoft[loft.id]">
              <td>{{ currentByLoft[loft.id].instrumentNo }}</td>
              <td>{{ currentByLoft[loft.id].stopDate }}</td>
              <td>{{ currentByLoft[loft.id].pastedBy }}</td>
              <td>
                <span class="badge" :class="stickerState(currentByLoft[loft.id]).cls">
                  {{ stickerState(currentByLoft[loft.id]).text }}
                </span>
              </td>
              <td v-if="isAdmin" class="renew-cell">
                <input
                  v-model="renewForms[currentByLoft[loft.id].id].stopDate"
                  type="date"
                  required
                />
                <input
                  v-model="renewForms[currentByLoft[loft.id].id].instrumentNo"
                  placeholder="仪器编号"
                />
                <button
                  class="btn"
                  type="button"
                  :disabled="busy || !renewForms[currentByLoft[loft.id].id].stopDate"
                  @click="renew(currentByLoft[loft.id])"
                >
                  续期
                </button>
                <button
                  class="btn secondary"
                  type="button"
                  :disabled="busy"
                  @click="voidSticker(currentByLoft[loft.id])"
                >
                  作废
                </button>
              </td>
            </template>
            <template v-else>
              <td>—</td>
              <td>—</td>
              <td>—</td>
              <td><span class="badge badge-raw">未张贴</span></td>
              <td v-if="isAdmin" class="hint">请在下方粘贴</td>
            </template>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="isAdmin" class="panel">
      <h2 class="feed-title">粘贴新贴纸</h2>
      <p v-if="!pastableLofts.length" class="hint">所有帆布间均已有现行贴纸；如需更换请先作废或使用续期。</p>
      <form v-else class="row" @submit.prevent="paste">
        <label>帆布间
          <select v-model.number="pasteForm.loftId" required>
            <option v-for="l in pastableLofts" :key="l.id" :value="l.id">{{ l.name }}</option>
          </select>
        </label>
        <label>仪器编号
          <input v-model.trim="pasteForm.instrumentNo" required placeholder="如 HYG-01" />
        </label>
        <label>止日（不得为空）
          <input v-model="pasteForm.stopDate" type="date" required />
        </label>
        <button class="btn" type="submit" :disabled="busy">粘贴</button>
      </form>
    </section>

    <section v-if="history.length" class="panel">
      <h2 class="feed-title">已作废贴纸</h2>
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
          <tr v-for="s in history" :key="s.id">
            <td>{{ s.loftName }}</td>
            <td>{{ s.instrumentNo }}</td>
            <td>{{ s.stopDate }}</td>
            <td>{{ s.pastedBy }}</td>
            <td>{{ new Date(s.voidedAt).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.renew-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.renew-cell input {
  min-width: 0;
}
.badge-expired {
  background: #f0d9d9;
  color: #9b2c2c;
}
</style>
