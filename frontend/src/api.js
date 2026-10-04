import axios from 'axios'
import { useAuthStore } from './stores/auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const auth = useAuthStore()
    const original = error.config
    if (error.response?.status === 401 && auth.refreshToken && !original._retry) {
      original._retry = true
      try {
        const { data } = await axios.post('/api/auth/token/refresh/', {
          refresh: auth.refreshToken,
        })
        auth.setTokens(data.access, auth.refreshToken)
        original.headers.Authorization = `Bearer ${data.access}`
        return api(original)
      } catch {
        auth.logout()
      }
    }
    return Promise.reject(error)
  }
)

// 从 DRF 错误响应中提取第一条可读文案（含字段级中文报错）
export function errText(e, fallback = '操作失败') {
  const data = e?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  for (const key of Object.keys(data)) {
    const v = data[key]
    if (Array.isArray(v) && v.length) return String(v[0])
    if (typeof v === 'string') return v
  }
  return fallback
}

export default api
