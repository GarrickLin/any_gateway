import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
  role: string
}

export interface MeResponse {
  username: string
  role: string
  quota_usd: number | null
  used_usd: number
}

export const login = (username: string, password: string) =>
  client.post<LoginResponse>('/admin/auth/login', { username, password })

export const getMe = () =>
  client.get<MeResponse>('/auth/me')

export const getMyStatus = () =>
  client.get<{
    quota_usd: number | null
    used_usd: number
    groups: Array<{
      group_id: string
      group_name: string
      is_all_visible: boolean
      rate_limits: Array<{
        rule_id: string
        limit_type: string
        window_sec: number
        limit: number
        current: number
        remaining_pct: number
      }>
    }>
  }>('/auth/my-status')
