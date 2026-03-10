import client from './client'

export interface Token {
  id: string
  name: string
  key: string
  group_id: string | null
  quota_usd: number
  used_usd: number
  frozen: boolean
  expires_at: string | null
  created_at: string
  last_used: string | null
}

export interface TokenCreate {
  name: string
  group_id?: string | null
  quota_usd?: number
  expires_at?: string | null
}

export interface TokenUpdate {
  name?: string
  group_id?: string | null
  quota_usd?: number
  expires_at?: string | null
  frozen?: boolean
}

export interface GroupOption {
  id: string
  name: string
}

export const getTokens = (params?: Record<string, unknown>) =>
  client.get('/user/tokens', { params })

export const createToken = (data: TokenCreate) =>
  client.post('/user/tokens', data)

export const updateToken = (id: string, data: TokenUpdate) =>
  client.patch(`/user/tokens/${id}`, data)

export const deleteToken = (id: string) =>
  client.delete(`/user/tokens/${id}`)

export const freezeToken = (id: string, frozen: boolean) =>
  client.post(`/user/tokens/${id}/freeze`, { frozen })

export const getUserGroups = () =>
  client.get<GroupOption[]>('/user/groups')
