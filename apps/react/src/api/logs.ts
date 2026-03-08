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

export const getLogs = (params?: LogsFilter) =>
  client.get('/admin/logs', { params })

export const getMyLogs = (params?: LogsFilter) =>
  client.get('/user/logs', { params })

export const getLogMessages = (requestId: string) =>
  client.get(`/admin/logs/${requestId}/messages`)

export const getMyLogMessages = (requestId: string) =>
  client.get(`/user/logs/${requestId}/messages`)

export const getStatsOverview = () =>
  client.get('/admin/stats/overview')

export const getStatsTokens = () =>
  client.get('/admin/stats/tokens')

export const getStatsModels = () =>
  client.get('/admin/stats/models')
