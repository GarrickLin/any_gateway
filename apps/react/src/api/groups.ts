import client from './client'

export interface UserGroup {
  id: string
  name: string
  priority: number
  multiplier: number
  created_at: string
}

export interface UserGroupCreate {
  name: string
  priority?: number
  multiplier?: number
}

export const getGroups = (params?: Record<string, unknown>) =>
  client.get('/admin/groups', { params })

export const createGroup = (data: UserGroupCreate) =>
  client.post('/admin/groups', data)

export const updateGroup = (id: string, data: Partial<UserGroupCreate>) =>
  client.patch(`/admin/groups/${id}`, data)

export const deleteGroup = (id: string) =>
  client.delete(`/admin/groups/${id}`)
