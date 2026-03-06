import client from './client'

export interface AdminUser {
  username: string
  role: 'admin' | 'superadmin'
  created_by: string | null
  created_at: string
}

export interface PromoteRequest {
  username: string
  role: 'admin' | 'superadmin'
}

export const getAdminUsers = () =>
  client.get<AdminUser[]>('/admin/users')

export const promoteUser = (data: PromoteRequest) =>
  client.post('/admin/users/promote', data)

export const demoteUser = (username: string) =>
  client.delete(`/admin/users/${username}`)
