import React, { useState, useEffect, useCallback } from 'react'
import {
  Grid, Card, Statistic, Table, Progress,
  Typography, Spin, Message, Input, Space, Tag,
} from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import { Button } from '@arco-design/web-react'
import {
  getStatsOverview, getStatsTokens, getStatsModels,
  getMyStatsOverview, getMyStatsTokens, getMyStatsModels,
} from '../../api/logs'
import { getMe, getMyStatus } from '../../api/auth'
import { useAuthStore } from '../../store/auth'
import { redeemVoucher } from '../../api/vouchers'

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

interface RateLimit {
  rule_id: string
  limit_type: string
  window_sec: number
  limit: number
  current: number
  remaining_pct: number
}

interface GroupStatus {
  group_id: string
  group_name: string
  is_all_visible: boolean
  rate_limits: RateLimit[]
}

interface MyStatus {
  quota_usd: number | null
  used_usd: number
  groups: GroupStatus[]
}

interface RateLimitRow extends RateLimit {
  group_name: string
  is_all_visible: boolean
}

const Dashboard: React.FC = () => {
  const { role } = useAuthStore()
  const isAdmin = role === 'admin' || role === 'superadmin'

  const [overview, setOverview] = useState<Overview | null>(null)
  const [tokens, setTokens] = useState<TokenStat[]>([])
  const [models, setModels] = useState<ModelStat[]>([])
  const [loading, setLoading] = useState(false)
  const [meData, setMeData] = useState<{ quota_usd: number | null; used_usd: number } | null>(null)
  const [myStatus, setMyStatus] = useState<MyStatus | null>(null)
  const [voucherCode, setVoucherCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [voucherError, setVoucherError] = useState('')

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
    try {
      const statusRes = await getMyStatus()
      console.log('myStatus data:', statusRes.data)
      setMyStatus(statusRes.data)
    } catch (err) {
      console.error('Failed to load my status:', err)
      // Redis 不可用或未登录时静默处理
    }
  }, [isAdmin])

  const handleRedeem = async () => {
    if (!voucherCode.trim()) {
      setVoucherError('请输入券码')
      return
    }
    setVoucherError('')
    setRedeeming(true)
    try {
      const res = await redeemVoucher(voucherCode.trim())
      const amount = res.data?.amount_usd ?? 0
      Message.success(`充值 $${amount.toFixed(2)} 成功`)
      setVoucherCode('')
      const me = await getMe()
      setMeData({ quota_usd: me.data.quota_usd, used_usd: me.data.used_usd })
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setVoucherError(typeof detail === 'string' ? detail : '兑换失败')
    } finally {
      setRedeeming(false)
    }
  }

  useEffect(() => { fetchAll() }, [fetchAll])

  const maxModelCount = models[0]?.request_count ?? 1



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
        <Row gutter={16} align="stretch" style={{ marginBottom: 24, flexWrap: 'nowrap' }}>
          <Col flex={1}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="今日请求数"
                value={overview?.request_count ?? 0}
                suffix="次"
              />
            </Card>
          </Col>
          <Col flex={1}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="今日费用（含套餐）"
                value={overview?.total_cost_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col flex={1}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="实际扣费"
                value={(overview as any)?.actual_cost_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col flex={1}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="累计消费"
                value={meData?.used_usd ?? 0}
                precision={4}
                suffix="USD"
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

        {/* 用户余额 Card */}
        {myStatus && (
          <Card style={{ marginTop: 24 }} title="账户余额">
            <Row gutter={24} align="center">
              <Col span={6}>
                <Statistic
                  title="总额度"
                  value={myStatus.quota_usd != null ? myStatus.quota_usd : '无限'}
                  suffix={myStatus.quota_usd != null ? ' USD' : ''}
                />
              </Col>
              <Col span={6}>
                <Statistic title="已消费" value={myStatus.used_usd?.toFixed(4)} suffix=" USD" />
              </Col>
              <Col span={6}>
                <Statistic
                  title="剩余"
                  value={myStatus.quota_usd != null
                    ? (myStatus.quota_usd - myStatus.used_usd).toFixed(4)
                    : '无限'}
                  suffix={myStatus.quota_usd != null ? ' USD' : ''}
                />
              </Col>
              <Col span={6}>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <Input
                    size="small"
                    placeholder="输入券码充值"
                    value={voucherCode}
                    onChange={(v) => { setVoucherCode(v); setVoucherError('') }}
                    style={{ flex: 1 }}
                    onPressEnter={handleRedeem}
                  />
                  <Button size="small" type="primary" loading={redeeming} onClick={handleRedeem}>
                    兑换
                  </Button>
                </div>
                {voucherError && (
                  <div style={{ marginTop: 4, fontSize: 12, color: 'rgb(var(--red-6))' }}>
                    {voucherError}
                  </div>
                )}
              </Col>
            </Row>
          </Card>
        )}

        {/* 分组限流状态 Card */}
        {myStatus && myStatus.groups && myStatus.groups.length > 0 && (
          <Card style={{ marginTop: 16 }} title="分组限流状态">
            <Table
              rowKey="rule_id"
              pagination={false}
              data={myStatus.groups.flatMap((g: GroupStatus) =>
                g.rate_limits.map((r: RateLimit) => ({ ...r, group_name: g.group_name, is_all_visible: g.is_all_visible }))
              )}
              columns={[
                {
                  title: '分组',
                  dataIndex: 'group_name',
                  render: (v: string, row: RateLimitRow) => (
                    <Space size="small">
                      {v}
                      {row.is_all_visible && <Tag color="green" size="small">全员</Tag>}
                    </Space>
                  )
                },
                {
                  title: '类型',
                  dataIndex: 'limit_type',
                  render: (v: string) => ({ request_limit: '请求数', token_limit: 'Token', quota_limit: '金额' }[v] ?? v)
                },
                {
                  title: '窗口',
                  dataIndex: 'window_sec',
                  render: (v: number) => v >= 86400 ? `${v/86400}天` : v >= 3600 ? `${v/3600}小时` : `${Math.round(v/60)}分钟`
                },
                { title: '当前', dataIndex: 'current' },
                { title: '上限', dataIndex: 'limit' },
                {
                  title: '剩余',
                  dataIndex: 'remaining_pct',
                  render: (v: number) => (
                    <Progress
                      percent={v}
                      size="small"
                      style={{ width: 100 }}
                      status={v < 20 ? 'error' : v < 50 ? 'warning' : 'normal'}
                    />
                  )
                },
              ]}
            />
          </Card>
        )}
      </Spin>
    </div>
  )
}

export default Dashboard
