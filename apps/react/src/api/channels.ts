import client from './client'

export interface Channel {
  id: string
  name: string
  provider: string
  base_url: string
  api_key: string
  weight: number
  enabled: boolean
  models: string | null
  model_mapping: string | null
  created_at: string
}

export interface ChannelCreate {
  name: string
  provider: string
  base_url: string
  api_key: string
  weight?: number
  enabled?: boolean
  models?: string | null
  model_mapping?: string | null
}

export const getChannels = (params?: Record<string, unknown>) =>
  client.get('/admin/channels', { params })

export const createChannel = (data: ChannelCreate) =>
  client.post('/admin/channels', data)

export const updateChannel = (id: string, data: Partial<ChannelCreate>) =>
  client.patch(`/admin/channels/${id}`, data)

export const deleteChannel = (id: string) =>
  client.delete(`/admin/channels/${id}`)

export const fetchChannelModels = (id: string) =>
  client.post(`/admin/channels/${id}/fetch-models`)
