import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
  role: string
}

export interface MeResponse {
  username: string
  role: string
}

export const login = (username: string, password: string) =>
  client.post<LoginResponse>('/admin/auth/login', { username, password })

export const getMe = () =>
  client.get<MeResponse>('/auth/me')
