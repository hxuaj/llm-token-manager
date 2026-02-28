/**
 * API 调用层
 * 封装所有与后端的 HTTP 交互
 */
import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器 - 自动添加 JWT Token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器 - 处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 登录接口的 401 不重定向，让组件自己处理错误提示
      const isLoginRequest = error.config?.url?.includes('/api/auth/login')
      if (!isLoginRequest) {
        // Token 过期或无效，清除本地存储并跳转到登录页
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ─────────────────────────────────────────────────────────────────────
// 认证接口
// ─────────────────────────────────────────────────────────────────────

export const authApi = {
  /**
   * 用户注册
   */
  register: (data) => api.post('/api/auth/register', data),

  /**
   * 用户登录
   */
  login: (data) => api.post('/api/auth/login', data),

  /**
   * 获取当前用户信息
   */
  me: () => api.get('/api/auth/me'),
}

// ─────────────────────────────────────────────────────────────────────
// 用户 Key 管理接口
// ─────────────────────────────────────────────────────────────────────

export const userKeyApi = {
  /**
   * 获取我的 Key 列表
   */
  list: () => api.get('/api/user/keys'),

  /**
   * 创建新 Key
   */
  create: (name) => api.post('/api/user/keys', { name }),

  /**
   * 吊销 Key
   */
  revoke: (id) => api.delete(`/api/user/keys/${id}`),

  /**
   * 获取某个 Key 的统计信息
   */
  stats: (id) => api.get(`/api/user/keys/${id}/stats`),

  /**
   * 获取我的用量统计
   */
  usage: () => api.get('/api/user/usage'),
}

// ─────────────────────────────────────────────────────────────────────
// Admin 用户管理接口
// ─────────────────────────────────────────────────────────────────────

export const adminUserApi = {
  /**
   * 获取用户列表
   */
  list: (params) => api.get('/api/admin/users', { params }),

  /**
   * 获取单个用户
   */
  get: (id) => api.get(`/api/admin/users/${id}`),

  /**
   * 更新用户
   */
  update: (id, data) => api.put(`/api/admin/users/${id}`, data),

  /**
   * 获取用户的所有 Key
   */
  keys: (id) => api.get(`/api/admin/users/${id}/keys`),

  /**
   * 吊销用户的某个 Key
   */
  revokeKey: (userId, keyId) => api.delete(`/api/admin/users/${userId}/keys/${keyId}`),
}

// ─────────────────────────────────────────────────────────────────────
// Admin 供应商管理接口
// ─────────────────────────────────────────────────────────────────────

export const adminProviderApi = {
  /**
   * 获取供应商列表
   */
  list: () => api.get('/api/admin/providers'),

  /**
   * 创建供应商
   */
  create: (data) => api.post('/api/admin/providers', data),

  /**
   * 更新供应商
   */
  update: (id, data) => api.put(`/api/admin/providers/${id}`, data),

  /**
   * 删除供应商
   */
  delete: (id) => api.delete(`/api/admin/providers/${id}`),

  /**
   * 获取供应商的 Key 列表
   */
  keys: (id) => api.get(`/api/admin/providers/${id}/keys`),

  /**
   * 添加供应商 Key
   */
  addKey: (id, data) => api.post(`/api/admin/providers/${id}/keys`, data),

  /**
   * 删除供应商 Key
   */
  deleteKey: (providerId, keyId) =>
    api.delete(`/api/admin/providers/${providerId}/keys/${keyId}`),

  /**
   * 获取模型定价列表
   */
  pricing: (providerId) => api.get(`/api/admin/providers/${providerId}/pricing`),

  /**
   * 设置模型定价
   */
  setPricing: (providerId, data) =>
    api.post(`/api/admin/providers/${providerId}/pricing`, data),
}

// ─────────────────────────────────────────────────────────────────────
// 模型列表接口（需要平台 Key 认证，但前端用于展示）
// ─────────────────────────────────────────────────────────────────────

export const modelApi = {
  /**
   * 获取可用模型列表
   */
  list: () => api.get('/v1/models'),
}

// ─────────────────────────────────────────────────────────────────────
// 用户用量统计接口
// ─────────────────────────────────────────────────────────────────────

export const userUsageApi = {
  /**
   * 按模型统计
   */
  byModel: (params) => api.get('/api/user/usage/by-model', { params }),

  /**
   * 按 Key 统计
   */
  byKey: (params) => api.get('/api/user/usage/by-key', { params }),

  /**
   * 时间线统计
   */
  timeline: (params) => api.get('/api/user/usage/timeline', { params }),
}

// ─────────────────────────────────────────────────────────────────────
// Admin 用量统计接口
// ─────────────────────────────────────────────────────────────────────

export const adminUsageApi = {
  /**
   * 用量概览
   */
  overview: (params) => api.get('/api/admin/usage/overview', { params }),

  /**
   * 按模型统计
   */
  byModel: (params) => api.get('/api/admin/usage/by-model', { params }),

  /**
   * 按用户统计
   */
  byUser: (params) => api.get('/api/admin/usage/by-user', { params }),

  /**
   * 导出 CSV
   */
  export: (params) => api.get('/api/admin/usage/export', {
    params,
    responseType: 'blob'
  }),
}

// ─────────────────────────────────────────────────────────────────────
// Admin 模型管理接口
// ─────────────────────────────────────────────────────────────────────

export const adminModelApi = {
  /**
   * 获取供应商的模型列表
   */
  list: (providerId) => api.get(`/api/admin/providers/${providerId}/models`),

  /**
   * 触发模型发现
   */
  discover: (providerId) => api.post(`/api/admin/providers/${providerId}/discover-models`),

  /**
   * 更新模型状态
   */
  updateStatus: (modelId, status) => api.put(`/api/admin/models/${modelId}/status`, { status }),

  /**
   * 更新模型定价
   */
  updatePricing: (modelId, data) => api.put(`/api/admin/models/${modelId}/pricing`, data),

  /**
   * 手动添加模型
   */
  create: (data) => api.post('/api/admin/models', data),

  /**
   * 批量启用模型
   */
  batchActivate: (providerId, data) => api.post(`/api/admin/providers/${providerId}/models/batch-activate`, data),
}

export default api
