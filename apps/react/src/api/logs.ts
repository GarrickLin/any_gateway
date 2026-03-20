import client from './client'

export interface LogsFilter {
  start_date?: string
  end_date?: string
  token_id?: string
  username?: string
  model?: string
  group_id?: string
  status?: number
  page?: number
  page_size?: number
}

export interface DashboardStatsFilter {
  start_at?: string
  end_at?: string
  username?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface StatsOverviewResponse {
  total_cost_usd: number
  actual_cost_usd: number
  request_count: number
  total_token_usage: number
  date: string
}

export interface UsageStatsItem {
  username: string | null
  model: string | null
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  total_token_usage: number
  request_count: number
  total_cost_usd: number
}

export interface ModelStatsItem {
  model: string | null
  request_count: number
}

export interface PaginatedStatsResponse<T> {
  data: T[]
  total: number
  page: number
  page_size: number
}

export const getLogs = (params?: LogsFilter) =>
  client.get('/admin/logs', { params })

export const getMyLogs = (params?: LogsFilter) =>
  client.get('/user/logs', { params })

export const getLogMessages = (requestId: string) =>
  client.get(`/admin/logs/${requestId}/messages`)

export const getMyLogMessages = (requestId: string) =>
  client.get(`/user/logs/${requestId}/messages`)

export const getStatsOverview = (params?: DashboardStatsFilter) =>
  client.get<StatsOverviewResponse>('/admin/stats/overview', { params })

export const getStatsTokens = () =>
  client.get('/admin/stats/tokens')

export const getStatsUsage = (params?: DashboardStatsFilter) =>
  client.get<PaginatedStatsResponse<UsageStatsItem>>('/admin/stats/usage', { params })

export const exportStatsUsage = (params?: DashboardStatsFilter) =>
  client.get('/admin/stats/usage/export', { params, responseType: 'blob' })

export const getStatsModels = (params?: DashboardStatsFilter) =>
  client.get<PaginatedStatsResponse<ModelStatsItem>>('/admin/stats/models', { params })

export const getMyStatsOverview = (params?: DashboardStatsFilter) =>
  client.get<StatsOverviewResponse>('/user/stats/overview', { params })

export const getMyStatsTokens = () =>
  client.get('/user/stats/tokens')

export const getMyStatsUsage = (params?: DashboardStatsFilter) =>
  client.get<PaginatedStatsResponse<UsageStatsItem>>('/user/stats/usage', { params })

export const exportMyStatsUsage = (params?: DashboardStatsFilter) =>
  client.get('/user/stats/usage/export', { params, responseType: 'blob' })

export const getMyStatsModels = (params?: DashboardStatsFilter) =>
  client.get<PaginatedStatsResponse<ModelStatsItem>>('/user/stats/models', { params })
