import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Role = 'user' | 'admin' | 'superadmin'

interface AuthState {
  token: string | null
  username: string | null
  role: Role | null
  setAuth: (token: string, username: string, role: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      setAuth: (token, username, role) =>
        set({ token, username, role: role as Role }),
      logout: () => set({ token: null, username: null, role: null }),
    }),
    { name: 'auth-storage' }
  )
)
