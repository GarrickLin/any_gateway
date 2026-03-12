import React, { useState, useEffect, useCallback } from 'react'
import {
  Grid, Card, Statistic, Table, Progress,
  Typography, Spin, Message,
} from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { Button } from '@arco-design/web-react'
import {
  getStatsOverview, getStatsTokens, getStatsModels,
  getMyStatsOverview, getMyStatsTokens, getMyStatsModels,
} from '../../api/logs'
import { getMe } from '../../api/auth'
import { useAuthStore } from '../../store/auth'

const { Row, Col } = Grid

interface Overview {
  total_cost_usd: number
  request_count: number
  date: string
}

interface TokenStat {
  token_id: string
  username: string | null
  token_name: string | null
  total_cost_usd: number
  request_count: number
}

interface ModelStat {
  model: string
  request_count: number
}

const Dashboard: React.FC = () => {
  const { role } = useAuthStore()
  const isAdmin = role === 'admin' || role === 'superadmin'

  const [overview, setOverview] = useState<Overview | null>(null)
  const [tokens, setTokens] = useState<TokenStat[]>([])
  const [models, setModels] = useState<ModelStat[]>([])
  const [loading, setLoading] = useState(false)
  const [meData, setMeData] = useState<{ quota_usd: number | null; used_usd: number } | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, tk, md, me] = await Promise.all(
        isAdmin
          ? [getStatsOverview(), getStatsTokens(), getStatsModels(), getMe()]
          : [getMyStatsOverview(), getMyStatsTokens(), getMyStatsModels(), getMe()],
      )
      setOverview(ov.data)
      setTokens(tk.data ?? [])
      setModels(md.data ?? [])
      setMeData({ quota_usd: me.data.quota_usd, used_usd: me.data.used_usd })
    } catch {
      Message.error('数据加载失败')
    } finally {
      setLoading(false)
    }
  }, [isAdmin])

  useEffect(() => { fetchAll() }, [fetchAll])

  const maxModelCount = models[0]?.request_count ?? 1

  const formatQuota = (quota: number | null): string => {
    if (quota === null) return 'NaN'
    if (quota === 0) return '余额已耗尽'
    return `$${quota.toFixed(2)}`
  }

  const quotaColor = (quota: number | null): string => {
    if (quota === null) return 'inherit'
    if (quota === 0) return 'rgb(var(--red-6))'
    return 'rgb(var(--green-6))'
  }

  const adminTokenColumns = [
    { title: '用户名', dataIndex: 'username', render: (v: string) => v ?? '—' },
    { title: 'Key 名称', dataIndex: 'token_name', render: (v: string) => v ?? '—' },
    { title: '请求数', dataIndex: 'request_count', width: 90 },
    {
      title: '费用 (USD)',
      dataIndex: 'total_cost_usd',
      width: 110,
      render: (v: number) => v.toFixed(4),
    },
  ]

  const userTokenColumns = [
    { title: 'Key 名称', dataIndex: 'token_name', render: (v: string) => v ?? '—' },
    { title: '请求数', dataIndex: 'request_count', width: 90 },
    {
      title: '费用 (USD)',
      dataIndex: 'total_cost_usd',
      width: 110,
      render: (v: number) => v.toFixed(4),
    },
  ]

  const modelColumns = [
    { title: '模型', dataIndex: 'model', render: (v: string) => v ?? '未知' },
    {
      title: '请求数',
      dataIndex: 'request_count',
      render: (v: number) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Progress
            percent={Math.round((v / maxModelCount) * 100)}
            showText={false}
            style={{ width: 120 }}
          />
          <span style={{ minWidth: 32, textAlign: 'right' }}>{v}</span>
        </div>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>
          Dashboard
        </Typography.Title>
        <Button icon={<IconRefresh />} loading={loading} onClick={fetchAll}>刷新</Button>
      </div>

      <Spin loading={loading} style={{ display: 'block' }}>
        {/* 概览卡片 */}
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card>
              <Statistic
                title="今日请求数"
                value={overview?.request_count ?? 0}
                suffix="次"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="今日费用"
                value={overview?.total_cost_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="累计消费"
                value={meData?.used_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="账户余额"
                value={meData ? formatQuota(meData.quota_usd) : '—'}
                style={{ color: meData ? quotaColor(meData.quota_usd) : 'inherit' }}
              />
            </Card>
          </Col>
        </Row>

        {/* Top 10 表格 */}
        <Row gutter={16}>
          <Col span={12}>
            <Card title="Token 用量 Top 10（今日）">
              <Table
                rowKey="token_id"
                columns={isAdmin ? adminTokenColumns : userTokenColumns}
                data={tokens}
                pagination={false}
                size="small"
                noDataElement={<span style={{ color: '#999' }}>暂无数据</span>}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card title="模型请求 Top 10（今日）">
              <Table
                rowKey="model"
                columns={modelColumns}
                data={models}
                pagination={false}
                size="small"
                noDataElement={<span style={{ color: '#999' }}>暂无数据</span>}
              />
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}

export default Dashboard
