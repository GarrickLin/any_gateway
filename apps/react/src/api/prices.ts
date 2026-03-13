import client from './client'

export interface ModelPrice {
  id: string
  model_name: string
  unit: string
  price_per_unit: number
  created_at: string
}

export interface ModelPriceCreate {
  model_name: string
  unit: string
  price_per_unit: number
}

export interface ModelPriceUpdate {
  price_per_unit: number
}

export const getPrices = () =>
  client.get('/admin/model-prices')

export const createPrice = (data: ModelPriceCreate) =>
  client.post('/admin/model-prices', data)

export const updatePrice = (id: string, data: ModelPriceUpdate) =>
  client.patch(`/admin/model-prices/${id}`, data)

export const deletePrice = (id: string) =>
  client.delete(`/admin/model-prices/${id}`)
