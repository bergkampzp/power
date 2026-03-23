import { useState } from 'react'
import { Card, DatePicker, Button, Row, Col, Tabs, Table, Select, Tag, Statistic, Alert, message } from 'antd'
import { 
  SearchOutlined, 
  DownloadOutlined, 
  SwapOutlined,
  LineChartOutlined, 
  BarChartOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  RiseOutlined,
  ReloadOutlined
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'

const { TabPane } = Tabs
const { RangePicker } = DatePicker

// 滚撮撮合记录
const scrollColumns = [
  { title: '时间', dataIndex: 'time', key: 'time', width: 100 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (text: string) => (
    <Tag color={text === '买入' ? 'green' : 'red'}>{text}</Tag>
  )},
  { title: '电量(MWh)', dataIndex: 'volume', key: 'volume', width: 100 },
  { title: '价格(元/MWh)', dataIndex: 'price', key: 'price', width: 120 },
  { title: '对手方', dataIndex: 'counterparty', key: 'counterparty', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (text: string) => (
    <Tag color={text === '成交' ? 'green' : text === '待撮合' ? 'orange' : 'default'}>{text}</Tag>
  )},
]

const scrollData = [
  { time: '09:35', type: '买入', volume: 200, price: 315, counterparty: '电厂A', status: '成交' },
  { time: '09:40', type: '卖出', volume: 150, price: 318, counterparty: '售电公司B', status: '成交' },
  { time: '09:45', type: '买入', volume: 300, price: 312, counterparty: '电厂C', status: '待撮合' },
  { time: '09:50', type: '卖出', volume: 180, price: 320, counterparty: '用户D', status: '已撤销' },
  { time: '09:55', type: '买入', volume: 250, price: 314, counterparty: '电厂E', status: '成交' },
  { time: '10:00', type: '卖出', volume: 200, price: 319, counterparty: '售电公司F', status: '成交' },
]

// 持仓明细
const positionColumns = [
  { title: '合约类型', dataIndex: 'contract', key: 'contract', width: 120 },
  { title: '持仓量(MWh)', dataIndex: 'position', key: 'position', width: 120 },
  { title: '持仓均价(元/MWh)', dataIndex: 'avgPrice', key: 'avgPrice', width: 140 },
  { title: '当前价(元/MWh)', dataIndex: 'currentPrice', key: 'currentPrice', width: 130 },
  { title: '持仓盈亏(元)', dataIndex: 'pnl', key: 'pnl', width: 130, render: (text: number) => (
    <span style={{ color: text >= 0 ? '#52c41a' : '#ff4d4f' }}>{text >= 0 ? '+' : ''}{text.toLocaleString()}</span>
  )},
  { title: '占比', dataIndex: 'ratio', key: 'ratio', width: 80 },
]

const positionData = [
  { contract: '日前合约', position: 3500, avgPrice: 312, currentPrice: 318, pnl: 21000, ratio: '35%' },
  { contract: '实时合约', position: 2000, avgPrice: 315, currentPrice: 320, pnl: 10000, ratio: '20%' },
  { contract: '月度合约', position: 3000, avgPrice: 308, currentPrice: 315, pnl: 21000, ratio: '30%' },
  { contract: '日前持仓', position: 1500, avgPrice: 320, currentPrice: 318, pnl: -3000, ratio: '15%' },
]

// 成交统计
const dealColumns = [
  { title: '时段', dataIndex: 'period', key: 'period', width: 100 },
  { title: '成交量(MWh)', dataIndex: 'volume', key: 'volume', width: 120 },
  { title: '成交均价(元/MWh)', dataIndex: 'avgPrice', key: 'avgPrice', width: 140 },
  { title: '买电量(MWh)', dataIndex: 'buyVolume', key: 'buyVolume', width: 120 },
  { title: '卖电量(MWh)', dataIndex: 'sellVolume', key: 'sellVolume', width: 120 },
  { title: '净成交量(MWh)', dataIndex: 'netVolume', key: 'netVolume', width: 120, render: (text: number) => (
    <span style={{ color: text >= 0 ? '#52c41a' : '#ff4d4f' }}>{text >= 0 ? '+' : ''}{text}</span>
  )},
]

const dealData = [
  { period: '09:00-10:00', volume: 1250, avgPrice: 316, buyVolume: 680, sellVolume: 570, netVolume: 110 },
  { period: '10:00-11:00', volume: 980, avgPrice: 318, buyVolume: 450, sellVolume: 530, netVolume: -80 },
  { period: '11:00-12:00', volume: 1560, avgPrice: 320, buyVolume: 820, sellVolume: 740, netVolume: 80 },
  { period: '14:00-15:00', volume: 2100, avgPrice: 322, buyVolume: 1100, sellVolume: 1000, netVolume: 100 },
  { period: '15:00-16:00', volume: 1850, avgPrice: 319, buyVolume: 900, sellVolume: 950, netVolume: -50 },
]

export default function ScrollDecision() {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-12'),
    dayjs('2026-03-12')
  ])
  const [activeTab, setActiveTab] = useState('match')
  const [loading, setLoading] = useState(false)

  // 实时价格走势图
  const priceChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['买入价', '卖出价', '市场均价'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['09:00', '09:15', '09:30', '09:45', '10:00', '10:15', '10:30', '10:45', '11:00'],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '价格(元/MWh)',
      min: 300,
      max: 330,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '买入价',
        type: 'line',
        data: [312, 314, 316, 315, 318, 320, 319, 321, 322],
        smooth: true,
        itemStyle: { color: '#52c41a' },
        symbol: 'circle',
        symbolSize: 6
      },
      {
        name: '卖出价',
        type: 'line',
        data: [318, 320, 322, 321, 324, 326, 325, 327, 328],
        smooth: true,
        itemStyle: { color: '#ff4d4f' },
        symbol: 'circle',
        symbolSize: 6
      },
      {
        name: '市场均价',
        type: 'line',
        data: [315, 317, 319, 318, 321, 323, 322, 324, 325],
        smooth: true,
        itemStyle: { color: '#1E88E5' },
        symbol: 'none',
        lineStyle: { type: 'dashed' }
      }
    ]
  }

  // 成交量分布图
  const volumeChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['买入成交量', '卖出成交量'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['09:00', '09:15', '09:30', '09:45', '10:00', '10:15', '10:30', '10:45', '11:00'],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '成交量(MWh)',
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '买入成交量',
        type: 'bar',
        stack: 'total',
        data: [150, 180, 220, 200, 250, 280, 240, 300, 320],
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '卖出成交量',
        type: 'bar',
        stack: 'total',
        data: [120, 160, 200, 180, 220, 250, 210, 270, 290],
        itemStyle: { color: '#ff4d4f' }
      }
    ]
  }

  // 持仓变化图
  const positionChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['日前持仓', '实时持仓', '总持仓'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['09:00', '09:15', '09:30', '09:45', '10:00', '10:15', '10:30', '10:45', '11:00'],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '持仓量(MWh)',
      axisLine: { lineLine: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '日前持仓',
        type: 'line',
        data: [3500, 3550, 3600, 3580, 3650, 3700, 3680, 3750, 3800],
        smooth: true,
        itemStyle: { color: '#1E88E5' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(30, 136, 229, 0.3)' },
              { offset: 1, color: 'rgba(30, 136, 229, 0.05)' }
            ]
          }
        }
      },
      {
        name: '实时持仓',
        type: 'line',
        data: [2000, 2050, 2100, 2080, 2150, 2200, 2180, 2250, 2300],
        smooth: true,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '总持仓',
        type: 'line',
        data: [5500, 5600, 5700, 5660, 5800, 5900, 5860, 6000, 6100],
        smooth: true,
        itemStyle: { color: '#faad14' }
      }
    ]
  }

  const handleRefresh = () => {
    setLoading(true)
    message.loading({ content: '正在刷新数据...', key: 'refresh' })
    setTimeout(() => {
      setLoading(false)
      message.success({ content: '数据已更新', key: 'refresh' })
    }, 1500)
  }

  return (
    <div>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日成交量"
              value={8740}
              precision={0}
              valueStyle={{ color: '#1E88E5' }}
              prefix={<SwapOutlined />}
              suffix="MWh"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="成交金额"
              value={2785680}
              precision={0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<DollarOutlined />}
              suffix="元"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="持仓盈亏"
              value={59000}
              precision={0}
              valueStyle={{ color: '#52c41a' }}
              prefix={<RiseOutlined />}
              suffix="元"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="持仓总量"
              value={10000}
              precision={0}
              valueStyle={{ color: '#faad14' }}
              prefix={<ThunderboltOutlined />}
              suffix="MWh"
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <RangePicker
              value={dateRange}
              onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              format="YYYY-MM-DD"
            />
          </Col>
          <Col>
            <Select defaultValue="day" style={{ width: 100 }}>
              <Select.Option value="day">按天</Select.Option>
              <Select.Option value="hour">按时</Select.Option>
              <Select.Option value="15min">按15分钟</Select.Option>
            </Select>
          </Col>
          <Col>
            <Select defaultValue="all" style={{ width: 120 }}>
              <Select.Option value="all">全部市场</Select.Option>
              <Select.Option value="dayAhead">日前市场</Select.Option>
              <Select.Option value="realTime">实时市场</Select.Option>
            </Select>
          </Col>
          <Col>
            <Button type="primary" icon={<SearchOutlined />}>查询</Button>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={loading}>刷新</Button>
          </Col>
          <Col>
            <Button icon={<DownloadOutlined />}>导出</Button>
          </Col>
        </Row>
      </Card>

      <Alert
        message="滚撮提示：当前市场买入需求旺盛，建议在10:00-11:00时段适量卖出，获取更高收益。"
        type="success"
        showIcon
        style={{ marginBottom: 16, background: '#52c41a20', border: '1px solid #52c41a' }}
      />

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><SwapOutlined />实时撮合</span>} key="match">
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card title="实时价格走势">
                <ReactECharts option={priceChartOption} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col span={24}>
              <Card title="成交量分布">
                <ReactECharts option={volumeChartOption} style={{ height: 250 }} />
              </Card>
            </Col>
          </Row>
          <Card title="撮合记录" style={{ marginTop: 16 }}>
            <Table
              columns={scrollColumns}
              dataSource={scrollData}
              pagination={{ pageSize: 8 }}
              scroll={{ x: 700 }}
              size="small"
            />
          </Card>
        </TabPane>
        
        <TabPane tab={<span><ThunderboltOutlined />持仓分析</span>} key="position">
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card title="持仓变化趋势">
                <ReactECharts option={positionChartOption} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
          <Card title="持仓明细" style={{ marginTop: 16 }}>
            <Table
              columns={positionColumns}
              dataSource={positionData}
              pagination={{ pageSize: 8 }}
              scroll={{ x: 700 }}
              size="small"
            />
          </Card>
        </TabPane>
        
        <TabPane tab={<span><BarChartOutlined />成交统计</span>} key="deal">
          <Card title="分时段成交统计">
            <Table
              columns={dealColumns}
              dataSource={dealData}
              pagination={{ pageSize: 8 }}
              scroll={{ x: 700 }}
              size="small"
            />
          </Card>
        </TabPane>
        
        <TabPane tab={<span><LineChartOutlined />盈亏分析</span>} key="pnl">
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Card>
                <Statistic
                  title="今日盈亏"
                  value={59000}
                  precision={0}
                  valueStyle={{ color: '#52c41a' }}
                  prefix="+"
                  suffix="元"
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="本月盈亏"
                  value={328000}
                  precision={0}
                  valueStyle={{ color: '#52c41a' }}
                  prefix="+"
                  suffix="元"
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic
                  title="年化收益率"
                  value={18.5}
                  precision={1}
                  valueStyle={{ color: '#52c41a' }}
                  suffix="%"
                />
              </Card>
            </Col>
          </Row>
        </TabPane>
      </Tabs>
    </div>
  )
}
