import { useState } from 'react'
import { Card, DatePicker, Button, Row, Col, Tabs, Table, Select, Tag, Statistic, Progress, Alert } from 'antd'
import { 
  SearchOutlined, 
  DownloadOutlined, 
  PieChartOutlined, 
  LineChartOutlined, 
  BarChartOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  RiseOutlined,
  WarningOutlined
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'

const { TabPane } = Tabs
const { RangePicker } = DatePicker

// 售电辅助决策数据
const decisionColumns = [
  { title: '时段', dataIndex: 'period', key: 'period', width: 100 },
  { title: '预测电价(元/MWh)', dataIndex: 'price', key: 'price', width: 140 },
  { title: '建议策略', dataIndex: 'strategy', key: 'strategy', width: 120, render: (text: string) => (
    <Tag color={text === '买入' ? 'green' : text === '卖出' ? 'red' : 'default'}>{text}</Tag>
  )},
  { title: '建议电量(MWh)', dataIndex: 'amount', key: 'amount', width: 140 },
  { title: '预期收益(元)', dataIndex: 'profit', key: 'profit', width: 140 },
  { title: '风险等级', dataIndex: 'risk', key: 'risk', width: 100, render: (text: string) => (
    <Tag color={text === '低' ? 'green' : text === '中' ? 'orange' : 'red'}>{text}</Tag>
  )},
]

const decisionData = [
  { period: '00:00', price: 280, strategy: '买入', amount: 500, profit: 12500, risk: '低' },
  { period: '04:00', price: 260, strategy: '买入', amount: 800, profit: 19200, risk: '低' },
  { period: '08:00', price: 320, strategy: '观望', amount: 0, profit: 0, risk: '中' },
  { period: '12:00', price: 380, strategy: '卖出', amount: 600, profit: 22800, risk: '中' },
  { period: '16:00', price: 360, strategy: '卖出', amount: 400, profit: 14400, risk: '低' },
  { period: '20:00', price: 340, strategy: '观望', amount: 0, profit: 0, risk: '中' },
]

// 持仓分析数据
const positionColumns = [
  { title: '合约类型', dataIndex: 'contract', key: 'contract', width: 120 },
  { title: '持仓量(MWh)', dataIndex: 'position', key: 'position', width: 130 },
  { title: '持仓均价(元/MWh)', dataIndex: 'avgPrice', key: 'avgPrice', width: 150 },
  { title: '当前市价(元/MWh)', dataIndex: 'marketPrice', key: 'marketPrice', width: 150 },
  { title: '浮动盈亏(元)', dataIndex: 'pnl', key: 'pnl', width: 140, render: (text: number) => (
    <span style={{ color: text >= 0 ? '#52c41a' : '#ff4d4f' }}>{text >= 0 ? '+' : ''}{text.toLocaleString()}</span>
  )},
  { title: '到期日', dataIndex: 'expireDate', key: 'expireDate', width: 120 },
]

const positionData = [
  { contract: '日前合约', position: 2500, avgPrice: 310, marketPrice: 325, pnl: 37500, expireDate: '2026-03-13' },
  { contract: '实时合约', position: 1200, avgPrice: 315, marketPrice: 320, pnl: 6000, expireDate: '2026-03-13' },
  { contract: '月度合约', position: 5000, avgPrice: 305, marketPrice: 312, pnl: 35000, expireDate: '2026-03-31' },
  { contract: '年度合约', position: 8000, avgPrice: 298, marketPrice: 305, pnl: 56000, expireDate: '2026-12-31' },
]

export default function SalesDecision() {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-12'),
    dayjs('2026-03-13')
  ])
  const [activeTab, setActiveTab] = useState('decision')

  // 策略建议图表
  const strategyChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['电价预测', '买入阈值', '卖出阈值'],
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
      data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '电价(元/MWh)',
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '电价预测',
        type: 'line',
        data: [280, 260, 320, 380, 360, 340],
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
        name: '买入阈值',
        type: 'line',
        data: [270, 270, 270, 270, 270, 270],
        lineStyle: { type: 'dashed', color: '#52c41a' },
        itemStyle: { color: '#52c41a' },
        symbol: 'none'
      },
      {
        name: '卖出阈值',
        type: 'line',
        data: [370, 370, 370, 370, 370, 370],
        lineStyle: { type: 'dashed', color: '#ff4d4f' },
        itemStyle: { color: '#ff4d4f' },
        symbol: 'none'
      }
    ]
  }

  // 收益分析图表
  const profitChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['预期收益', '累计收益'],
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
      data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: [
      {
        type: 'value',
        name: '收益(元)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      }
    ],
    series: [
      {
        name: '预期收益',
        type: 'bar',
        data: [12500, 19200, 0, 22800, 14400, 0],
        itemStyle: { 
          color: (params: any) => params.value > 0 ? '#52c41a' : '#ff4d4f'
        }
      },
      {
        name: '累计收益',
        type: 'line',
        data: [12500, 31700, 31700, 54500, 68900, 68900],
        smooth: true,
        itemStyle: { color: '#faad14' }
      }
    ]
  }

  return (
    <div>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日预期收益"
              value={68900}
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
              title="总持仓量"
              value={16700}
              precision={0}
              valueStyle={{ color: '#1E88E5' }}
              prefix={<ThunderboltOutlined />}
              suffix="MWh"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="浮动盈亏"
              value={134500}
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
              title="风险指数"
              value={3.2}
              precision={1}
              valueStyle={{ color: '#faad14' }}
              prefix={<WarningOutlined />}
              suffix="/10"
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
            <Select defaultValue="dayAhead" style={{ width: 140 }}>
              <Select.Option value="dayAhead">日前市场</Select.Option>
              <Select.Option value="realTime">实时市场</Select.Option>
              <Select.Option value="both">双边市场</Select.Option>
            </Select>
          </Col>
          <Col>
            <Button type="primary" icon={<SearchOutlined />}>生成策略</Button>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<DownloadOutlined />}>导出报告</Button>
          </Col>
        </Row>
      </Card>

      <Alert
        message="策略提示：当前电价处于相对低位，建议在 00:00-06:00 时段适量买入，在 12:00-16:00 高价时段卖出。"
        type="info"
        showIcon
        style={{ marginBottom: 16, background: '#1E88E520', border: '1px solid #1E88E5' }}
      />

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><PieChartOutlined />售电辅助决策</span>} key="decision">
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card title="策略建议图表">
                <ReactECharts option={strategyChartOption} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
          <Card title="时段策略明细" style={{ marginTop: 16 }}>
            <Table
              columns={decisionColumns}
              dataSource={decisionData}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 800 }}
              size="small"
            />
          </Card>
        </TabPane>
        
        <TabPane tab={<span><BarChartOutlined />滚撮辅助决策</span>} key="rolling">
          <Card>
            <div style={{ textAlign: 'center', padding: '60px 0', color: '#999' }}>
              <BarChartOutlined style={{ fontSize: 48, marginBottom: 16 }} />
              <p>滚撮辅助决策功能开发中...</p>
            </div>
          </Card>
        </TabPane>
        
        <TabPane tab={<span><LineChartOutlined />售电公司电量预测</span>} key="forecast">
          <Row gutter={[16, 16]}>
            <Col span={24}>
              <Card title="电量预测趋势">
                <ReactECharts option={profitChartOption} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
        </TabPane>
        
        <TabPane tab={<span><PieChartOutlined />持仓分析</span>} key="position">
          <Card title="持仓明细">
            <Table
              columns={positionColumns}
              dataSource={positionData}
              pagination={{ pageSize: 10 }}
              scroll={{ x: 800 }}
              size="small"
            />
          </Card>
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col span={8}>
              <Card title="日前合约">
                <Progress percent={75} status="active" strokeColor="#1E88E5" />
                <div style={{ marginTop: 8, color: '#999' }}>持仓占比 37.5%</div>
              </Card>
            </Col>
            <Col span={8}>
              <Card title="月度合约">
                <Progress percent={60} status="active" strokeColor="#52c41a" />
                <div style={{ marginTop: 8, color: '#999' }}>持仓占比 25.0%</div>
              </Card>
            </Col>
            <Col span={8}>
              <Card title="年度合约">
                <Progress percent={45} status="active" strokeColor="#faad14" />
                <div style={{ marginTop: 8, color: '#999' }}>持仓占比 20.0%</div>
              </Card>
            </Col>
          </Row>
        </TabPane>
      </Tabs>
    </div>
  )
}
