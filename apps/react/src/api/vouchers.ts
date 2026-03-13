import client from './client'

export interface Voucher {
  id: string
  code: string
  amount_usd: number
  expires_at: string | null
  used: boolean
  used_by: string | null
  used_at: string | null
}

export interface VoucherCreate {
  amount_usd: number
  expires_at?: string
}

// Admin endpoints
export const getVouchers = () =>
  client.get('/admin/vouchers')

export const createVoucher = (data: VoucherCreate) =>
  client.post('/admin/vouchers', data)

export const deleteVoucher = (id: string) =>
  client.delete(`/admin/vouchers/${id}`)

// User endpoints
export const redeemVoucher = (code: string) =>
  client.post('/user/vouchers/redeem', { code })
