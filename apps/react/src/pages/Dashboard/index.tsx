import React, { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import {
  Grid,
  Card,
  Statistic,
  Table,
  Progress,
  Typography,
  Spin,
  Message,
  Input,
  Space,
  Tag,
  DatePicker,
  Select,
  Button,
} from '@arco-design/web-react'
import { IconRefresh } from '@arco-design/web-react/icon'
import {
  exportMyStatsUsage,
  exportStatsUsage,
  getMyStatsModels,
  getMyStatsOverview,
  getMyStatsUsage,
  getStatsModels,
  getStatsOverview,
  getStatsUsage,
  type ModelStatsItem,
  type StatsOverviewResponse,
  type UsageStatsItem,
} from '../../api/logs'
import { getMyStatus } from '../../api/auth'
import { getUsersList } from '../../api/users'
import { useAuthStore } from '../../store/auth'
import { redeemVoucher } from '../../api/vouchers'

const { Row, Col } = Grid
const { RangePicker } = DatePicker

const today = dayjs().format('YYYY-MM-DD')

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

interface DashboardFilters {
  startDate: string
  endDate: string
  username?: string
}

interface TableState {
  current: number
  pageSize: number
  total: number
  sortBy: string
  sortOrder: 'asc' | 'desc'
}

interface TablePaginationChange {
  current?: number
  pageSize?: number
}

interface SingleTableSorterChange {
  field?: string | number
  direction?: 'ascend' | 'descend'
}

type TableSorterChange = SingleTableSorterChange | SingleTableSorterChange[]

interface RequestError {
  response?: {
    data?: {
      detail?: string
    }
  }
}

const INITIAL_FILTERS: DashboardFilters = {
  startDate: today,
  endDate: today,
}

const INITIAL_USAGE_TABLE: TableState = {
  current: 1,
  pageSize: 20,
  total: 0,
  sortBy: 'date',
  sortOrder: 'desc',
}

const INITIAL_MODEL_TABLE: TableState = {
  current: 1,
  pageSize: 20,
  total: 0,
  sortBy: 'request_count',
  sortOrder: 'desc',
}

const toUtcRange = (startDate: string, endDate: string) => ({
  start_at: new Date(`${startDate}T00:00:00`).toISOString(),
  end_at: new Date(`${endDate}T23:59:59.999`).toISOString(),
})

const buildStatsParams = (filters: DashboardFilters, isAdmin: boolean) => ({
  ...toUtcRange(filters.startDate, filters.endDate),
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  ...(isAdmin && filters.username ? { username: filters.username } : {}),
})

const toApiSortOrder = (direction?: 'ascend' | 'descend'): 'asc' | 'desc' =>
  direction === 'ascend' ? 'asc' : 'desc'

const toArcoSortOrder = (sortOrder: 'asc' | 'desc'): 'ascend' | 'descend' =>
  sortOrder === 'asc' ? 'ascend' : 'descend'

const normalizeSorter = (sorter: TableSorterChange): SingleTableSorterChange =>
  Array.isArray(sorter) ? (sorter[0] ?? {}) : sorter

const Dashboard: React.FC = () => {
  const { role } = useAuthStore()
  const isAdmin = role === 'admin' || role === 'superadmin'

  const [draftFilters, setDraftFilters] = useState<DashboardFilters>(INITIAL_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilters>(INITIAL_FILTERS)
  const [usageTable, setUsageTable] = useState<TableState>(INITIAL_USAGE_TABLE)
  const [modelTable, setModelTable] = useState<TableState>(INITIAL_MODEL_TABLE)

  const [overview, setOverview] = useState<StatsOverviewResponse | null>(null)
  const [usageRows, setUsageRows] = useState<UsageStatsItem[]>([])
  const [modelRows, setModelRows] = useState<ModelStatsItem[]>([])
  const [userOptions, setUserOptions] = useState<Array<{ label: string; value: string }>>([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [myStatus, setMyStatus] = useState<MyStatus | null>(null)
  const [voucherCode, setVoucherCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [voucherError, setVoucherError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const appliedStartDate = appliedFilters.startDate
  const appliedEndDate = appliedFilters.endDate
  const appliedUsername = appliedFilters.username
  const usageCurrent = usageTable.current
  const usagePageSize = usageTable.pageSize
  const usageSortBy = usageTable.sortBy
  const usageSortOrder = usageTable.sortOrder
  const modelCurrent = modelTable.current
  const modelPageSize = modelTable.pageSize
  const modelSortBy = modelTable.sortBy
  const modelSortOrder = modelTable.sortOrder

  useEffect(() => {
    if (isAdmin) return
    setUserOptions([])
    setDraftFilters((prev) => (prev.username ? { ...prev, username: undefined } : prev))
    setAppliedFilters((prev) => (prev.username ? { ...prev, username: undefined } : prev))
  }, [isAdmin])

  useEffect(() => {
    if (!isAdmin) return

    let cancelled = false

    const loadUsers = async () => {
      try {
        const res = await getUsersList()
        if (cancelled) return
        const data = Array.isArray(res.data) ? res.data : []
        setUserOptions(
          data
            .map((item) => ({ label: item.username, value: item.username }))
            .sort((a, b) => a.label.localeCompare(b.label)),
        )
      } catch {
        if (!cancelled) {
          Message.error('用户列表加载失败')
        }
      }
    }

    void loadUsers()

    return () => {
      cancelled = true
    }
  }, [isAdmin])

  useEffect(() => {
    let cancelled = false

    const loadDashboard = async () => {
      setLoading(true)
      const baseParams = buildStatsParams(
        { startDate: appliedStartDate, endDate: appliedEndDate, username: appliedUsername },
        isAdmin,
      )
      const usageParams = {
        ...baseParams,
        page: usageCurrent,
        page_size: usagePageSize,
        sort_by: usageSortBy,
        sort_order: usageSortOrder,
      }
      const modelParams = {
        ...baseParams,
        page: modelCurrent,
        page_size: modelPageSize,
        sort_by: modelSortBy,
        sort_order: modelSortOrder,
      }

      try {
        const [overviewRes, usageRes, modelRes, statusRes] = await Promise.all([
          isAdmin ? getStatsOverview(baseParams) : getMyStatsOverview(baseParams),
          isAdmin ? getStatsUsage(usageParams) : getMyStatsUsage(usageParams),
          isAdmin ? getStatsModels(modelParams) : getMyStatsModels(modelParams),
          getMyStatus(),
        ])

        if (cancelled) return

        setOverview(overviewRes.data)
        setUsageRows(usageRes.data.data ?? [])
        setModelRows(modelRes.data.data ?? [])
        setMyStatus(statusRes.data)

        setUsageTable((prev) =>
          prev.total === usageRes.data.total ? prev : { ...prev, total: usageRes.data.total },
        )
        setModelTable((prev) =>
          prev.total === modelRes.data.total ? prev : { ...prev, total: modelRes.data.total },
        )
      } catch {
        if (!cancelled) {
          Message.error('数据加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadDashboard()

    return () => {
      cancelled = true
    }
  }, [
    isAdmin,
    appliedStartDate,
    appliedEndDate,
    appliedUsername,
    usageCurrent,
    usagePageSize,
    usageSortBy,
    usageSortOrder,
    modelCurrent,
    modelPageSize,
    modelSortBy,
    modelSortOrder,
    refreshKey,
  ])

  const handleSearch = () => {
    setUsageTable((prev) => ({ ...prev, current: 1 }))
    setModelTable((prev) => ({ ...prev, current: 1 }))
    setAppliedFilters({ ...draftFilters, ...(isAdmin ? {} : { username: undefined }) })
    setRefreshKey((prev) => prev + 1)
  }

  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1)
  }

  const handleUsageTableChange = (pagination: TablePaginationChange, sorter: TableSorterChange) => {
    const nextSorter = normalizeSorter(sorter)
    setUsageTable((prev) => ({
      ...prev,
      current: pagination?.current ?? prev.current,
      pageSize: pagination?.pageSize ?? prev.pageSize,
      sortBy: typeof nextSorter.field === 'string' ? nextSorter.field : prev.sortBy,
      sortOrder: nextSorter.direction ? toApiSortOrder(nextSorter.direction) : prev.sortOrder,
    }))
  }

  const handleModelTableChange = (pagination: TablePaginationChange, sorter: TableSorterChange) => {
    const nextSorter = normalizeSorter(sorter)
    setModelTable((prev) => ({
      ...prev,
      current: pagination?.current ?? prev.current,
      pageSize: pagination?.pageSize ?? prev.pageSize,
      sortBy: typeof nextSorter.field === 'string' ? nextSorter.field : prev.sortBy,
      sortOrder: nextSorter.direction ? toApiSortOrder(nextSorter.direction) : prev.sortOrder,
    }))
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const params = {
        ...buildStatsParams(appliedFilters, isAdmin),
        sort_by: usageSortBy,
        sort_order: usageSortOrder,
      }
      const res = isAdmin ? await exportStatsUsage(params) : await exportMyStatsUsage(params)
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `dashboard-usage-${appliedFilters.startDate}-${appliedFilters.endDate}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch {
      Message.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

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
      setRefreshKey((prev) => prev + 1)
    } catch (err: unknown) {
      const detail = (err as RequestError)?.response?.data?.detail
      setVoucherError(typeof detail === 'string' ? detail : '兑换失败')
    } finally {
      setRedeeming(false)
    }
  }

  const usageColumns = [
    {
      title: '日期',
      dataIndex: 'date',
      sorter: true,
      sortOrder: usageTable.sortBy === 'date' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    ...(isAdmin
      ? [{
          title: '用户名',
          dataIndex: 'username',
          sorter: true,
          sortOrder: usageTable.sortBy === 'username' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
          render: (value: string | null) => value ?? '—',
        }]
      : []),
    {
      title: '模型',
      dataIndex: 'model',
      sorter: true,
      sortOrder: usageTable.sortBy === 'model' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
      render: (value: string | null) => value ?? '未知',
    },
    {
      title: '输入 Token',
      dataIndex: 'input_tokens',
      sorter: true,
      sortOrder: usageTable.sortBy === 'input_tokens' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    {
      title: '输出 Token',
      dataIndex: 'output_tokens',
      sorter: true,
      sortOrder: usageTable.sortBy === 'output_tokens' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    {
      title: 'Cache 读取',
      dataIndex: 'cache_read_tokens',
      sorter: true,
      sortOrder: usageTable.sortBy === 'cache_read_tokens' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    {
      title: 'Cache 写入',
      dataIndex: 'cache_creation_tokens',
      sorter: true,
      sortOrder: usageTable.sortBy === 'cache_creation_tokens' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      sorter: true,
      sortOrder: usageTable.sortBy === 'request_count' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
    },
    {
      title: '费用 (USD)',
      dataIndex: 'total_cost_usd',
      sorter: true,
      sortOrder: usageTable.sortBy === 'total_cost_usd' ? toArcoSortOrder(usageTable.sortOrder) : undefined,
      render: (value: number) => value.toFixed(4),
    },
  ]

  const modelColumns = [
    {
      title: '模型',
      dataIndex: 'model',
      sorter: true,
      sortOrder: modelTable.sortBy === 'model' ? toArcoSortOrder(modelTable.sortOrder) : undefined,
      render: (value: string | null) => value ?? '未知',
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      sorter: true,
      sortOrder: modelTable.sortBy === 'request_count' ? toArcoSortOrder(modelTable.sortOrder) : undefined,
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>
          Dashboard
        </Typography.Title>
        <Button icon={<IconRefresh />} loading={loading} onClick={handleRefresh}>刷新</Button>
      </div>

      <div style={{ background: '#fff', padding: 16, marginBottom: 16, borderRadius: 4 }}>
        <Row gutter={16} align="center">
          <Col span={isAdmin ? 8 : 10}>
            <RangePicker
              style={{ width: '100%' }}
              value={[dayjs(draftFilters.startDate), dayjs(draftFilters.endDate)]}
              onChange={(dateStrings) => {
                setDraftFilters((prev) => ({
                  ...prev,
                  startDate: dateStrings?.[0] || today,
                  endDate: dateStrings?.[1] || dateStrings?.[0] || today,
                }))
              }}
            />
          </Col>
          {isAdmin && (
            <Col span={6}>
              <Select
                style={{ width: '100%' }}
                placeholder="选择用户"
                allowClear
                showSearch
                value={draftFilters.username}
                options={userOptions}
                onChange={(value) => {
                  setDraftFilters((prev) => ({ ...prev, username: value || undefined }))
                }}
              />
            </Col>
          )}
          <Col span={isAdmin ? 10 : 14}>
            <Space wrap>
              <Button type="primary" onClick={handleSearch}>查询</Button>
              <Button loading={exporting} onClick={handleExport}>下载 CSV</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <Spin loading={loading} style={{ display: 'block' }}>
        <Row gutter={16} align="stretch" style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} lg={6}>
            <Card style={{ height: '100%' }}>
              <Statistic title="累计请求数" value={overview?.request_count ?? 0} suffix="次" />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="累计费用（含套餐）"
                value={overview?.total_cost_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="实际扣费"
                value={overview?.actual_cost_usd ?? 0}
                precision={4}
                suffix="USD"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="累计 Token 用量"
                value={overview?.total_token_usage ?? 0}
              />
            </Card>
          </Col>
        </Row>

        <Card title="用量统计表" style={{ marginBottom: 16 }}>
          <Table
            rowKey={(record) => `${record.date}:${record.username ?? 'self'}:${record.model ?? 'unknown'}`}
            columns={usageColumns}
            data={usageRows}
            onChange={handleUsageTableChange}
            pagination={{
              current: usageTable.current,
              pageSize: usageTable.pageSize,
              total: usageTable.total,
              showTotal: true,
            }}
            size="small"
            scroll={{ x: 1200 }}
            noDataElement={<span style={{ color: '#999' }}>暂无数据</span>}
          />
        </Card>

        <Card title="模型请求统计表" style={{ marginBottom: 16 }}>
          <Table
            rowKey="model"
            columns={modelColumns}
            data={modelRows}
            onChange={handleModelTableChange}
            pagination={{
              current: modelTable.current,
              pageSize: modelTable.pageSize,
              total: modelTable.total,
              showTotal: true,
            }}
            size="small"
            noDataElement={<span style={{ color: '#999' }}>暂无数据</span>}
          />
        </Card>

        {myStatus && (
          <Card style={{ marginTop: 24 }} title="账户余额">
            <Row gutter={24} align="center">
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
              <Col span={12}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Input
                    size="small"
                    placeholder="输入券码充值"
                    value={voucherCode}
                    onChange={(value) => {
                      setVoucherCode(value)
                      setVoucherError('')
                    }}
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

        {myStatus && (
          <Card style={{ marginTop: 16 }} title="分组限流状态">
            <Table
              rowKey="rule_id"
              pagination={false}
              data={myStatus.groups.flatMap((group: GroupStatus) =>
                group.rate_limits.map((rateLimit: RateLimit) => ({
                  ...rateLimit,
                  group_name: group.group_name,
                  is_all_visible: group.is_all_visible,
                })),
              )}
              noDataElement={<span style={{ color: '#999' }}>暂无分组限流规则</span>}
              columns={[
                {
                  title: '分组',
                  dataIndex: 'group_name',
                  render: (value: string, row: RateLimitRow) => (
                    <Space size="small">
                      {value}
                      {row.is_all_visible && <Tag color="green" size="small">全员</Tag>}
                    </Space>
                  ),
                },
                {
                  title: '类型',
                  dataIndex: 'limit_type',
                  render: (value: string) => (
                    { request_limit: '请求数', token_limit: 'Token', quota_limit: '金额' }[value] ?? value
                  ),
                },
                {
                  title: '窗口',
                  dataIndex: 'window_sec',
                  render: (value: number) => (
                    value >= 86400 ? `${value / 86400}天` : value >= 3600 ? `${value / 3600}小时` : `${Math.round(value / 60)}分钟`
                  ),
                },
                { title: '当前', dataIndex: 'current' },
                { title: '上限', dataIndex: 'limit' },
                {
                  title: '剩余',
                  dataIndex: 'remaining_pct',
                  render: (value: number) => (
                    <Progress
                      percent={value}
                      size="small"
                      style={{ width: 100 }}
                      status={value < 20 ? 'error' : value < 50 ? 'warning' : 'normal'}
                    />
                  ),
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
