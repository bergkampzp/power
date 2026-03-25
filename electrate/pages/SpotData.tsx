import { useState } from 'react'
import { Card, Row, Col, Select, Table } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import marketData from '../src/data/market_data.json'

interface MarketData {
  dates: string[]
  solar: number[]
  renewable: number[]
  load: number[]
  demand: number[]
  price: number[]
  min_price: number[]
  max_price: number[]
}

const data = marketData as MarketData

export default function SpotData() {
  const [activeTab, setActiveTab] = useState('history')

  // 生成历史数据表格
  const historyData = data.dates.slice(0, 10).map((date, idx) => {
    const load = data.load[idx]
    const solar = data.solar[idx]
    const renewable = data.renewable[idx]
    return {
      key: idx,
      date: date,
      period: '日前',
      wind: (renewable - solar).toFixed(0),
      solar: solar.toFixed(0),
      load: load.toFixed(0),
      price: data.price[idx].toFixed(2),
      external: (load * 0.8).toFixed(0)
    }
  })

  // 生成日统计
  const dailyData = data.dates.slice(0, 10).map((date, idx) => ({
    key: idx,
    date: date,
    windGen: ((data.renewable[idx] - data.solar[idx]) * 24 / 10).toFixed(0),
    solarGen: (data.solar[idx] * 24 / 10).toFixed(0),
    totalLoad: (data.load[idx] * 24 / 10).toFixed(0),
    avgPrice: data.price[idx].toFixed(2),
    maxPrice: data.max_price[idx].toFixed(2),
    minPrice: data.min_price[idx].toFixed(2)
  }))

  const historyColumns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '时段', dataIndex: 'period', key: 'period', width: 80 },
    { title: '风电(MW)', dataIndex: 'wind', key: 'wind', width: 100 },
    { title: '光伏(MW)', dataIndex: 'solar', key: 'solar', width: 100 },
    { title: '负荷(MW)', dataIndex: 'load', key: 'load', width: 100 },
    { title: '电价', dataIndex: 'price', key: 'price', width: 80 },
    { title: '外来电', dataIndex: 'external', key: 'external', width: 100 }
  ]

  const dailyColumns = [
    { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
    { title: '风电(万kWh)', dataIndex: 'windGen', key: 'windGen', width: 110 },
    { title: '光伏(万kWh)', dataIndex: 'solarGen', key: 'solarGen', width: 110 },
    { title: '负荷(万kWh)', dataIndex: 'totalLoad', key: 'totalLoad', width: 110 },
    { title: '均价', dataIndex: 'avgPrice', key: 'avgPrice', width: 80 },
    { title: '最高价', dataIndex: 'maxPrice', key: 'maxPrice', width: 80 },
    { title: '最低价', dataIndex: 'minPrice', key: 'minPrice', width: 80 }
  ]

  // 逐时分析图表
  const hourlyChartOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: {
      data: ['新能源出力', '光伏', '负荷', '电价'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.dates.slice(0, 10),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999', rotate: 45 }
    },
    yAxis: [
      {
        type: 'value',
        name: '功率(MW)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      },
      {
        type: 'value',
        name: '电价',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '新能源出力',
        type: 'line',
        data: data.renewable.slice(0, 10),
        smooth: true,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '光伏',
        type: 'line',
        data: data.solar.slice(0, 10),
        smooth: true,
        itemStyle: { color: '#faad14' }
      },
      {
        name: '负荷',
        type: 'line',
        data: data.load.slice(0, 10),
        smooth: true,
        itemStyle: { color: '#f5222d' }
      },
      {
        name: '电价',
        type: 'line',
        yAxisIndex: 1,
        data: data.price.slice(0, 10),
        smooth: true,
        itemStyle: { color: '#722ed1' }
      }
    ]
  }

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <Select
              defaultValue={data.dates[0]}
              style={{ width: 150 }}
              options={data.dates.map(d => ({ value: d, label: d }))}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <span style={{ color: '#999', marginRight: 16 }}>96点: {data.dates.length * 96}</span>
            <span style={{ color: '#999', marginRight: 16 }}>24点: {data.dates.length}</span>
          </Col>
          <Col>
            <span style={{ color: '#52c41a', marginRight: 8 }}>● 数据完整</span>
          </Col>
          <Col>
            <span style={{ color: '#999' }}>最后更新: {data.dates[data.dates.length - 1]}</span>
          </Col>
        </Row>
      </Card>

      <Card>
        <div style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={6}>
              <div style={{ background: '#1f1f1f', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#999' }}>新能源出力</div>
                <div style={{ color: '#52c41a', fontSize: 24, fontWeight: 'bold' }}>
                  {data.renewable[data.renewable.length - 1].toFixed(0)} MW
                </div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#1f1f1f', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#999' }}>光伏出力</div>
                <div style={{ color: '#faad14', fontSize: 24, fontWeight: 'bold' }}>
                  {data.solar[data.solar.length - 1].toFixed(0)} MW
                </div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#1f1f1f', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#999' }}>系统负荷</div>
                <div style={{ color: '#f5222d', fontSize: 24, fontWeight: 'bold' }}>
                  {data.load[data.load.length - 1].toFixed(0)} MW
                </div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#1f1f1f', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#999' }}>日前电价</div>
                <div style={{ color: '#722ed1', fontSize: 24, fontWeight: 'bold' }}>
                  {data.price[data.price.length - 1].toFixed(2)} 元
                </div>
              </div>
            </Col>
          </Row>
        </div>

        <ReactECharts option={hourlyChartOption} style={{ height: 350 }} />
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <h4 style={{ color: '#fff' }}>现货历史数据</h4>
            <Table
              columns={historyColumns}
              dataSource={historyData}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
          </Col>
          <Col span={12}>
            <h4 style={{ color: '#fff' }}>逐日统计</h4>
            <Table
              columns={dailyColumns}
              dataSource={dailyData}
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
          </Col>
        </Row>
      </Card>
    </div>
  )
}
