import client from './client'

export interface GroupModelPrice {
  id: string
  group_id: string
  model_name: string
  unit: string
  price_per_unit: number
  created_at: string
}

export interface GroupModelPriceCreate {
  group_id: string
  model_name: string
  unit: string
  price_per_unit: number
}

export const getGroupPrices = (groupId: string) =>
  client.get('/admin/group-model-prices', { params: { group_id: groupId } })

export const createGroupPrice = (data: GroupModelPriceCreate) =>
  client.post('/admin/group-model-prices', data)

export const deleteGroupPrice = (id: string) =>
  client.delete(`/admin/group-model-prices/${id}`)
