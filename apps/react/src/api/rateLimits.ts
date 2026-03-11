import client from './client'

export type LimitType = 'request_limit' | 'token_limit' | 'quota_limit'

export interface RateLimit {
  id: string
  group_id: string
  window_sec: number
  limit_type: LimitType
  value: number
}

export interface RateLimitCreate {
  group_id: string
  window_sec: number
  limit_type: LimitType
  value: number
}

// 获取某 group 的所有限流规则
export const getRateLimits = (groupId: string) =>
  client.get<{ data: RateLimit[] }>('/admin/rate-limits', {
    params: { group_id: groupId },
  })

// 创建规则
export const createRateLimit = (data: RateLimitCreate) =>
  client.post<RateLimit>('/admin/rate-limits', data)

// 删除规则
export const deleteRateLimit = (id: string) =>
  client.delete(`/admin/rate-limits/${id}`)
