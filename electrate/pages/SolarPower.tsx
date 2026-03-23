import { useState } from 'react'
import { Card, DatePicker, Button, Row, Col, Select } from 'antd'
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import marketData from '../data/market_data.json'

interface MarketData {
  dates: string[]
  solar: number[]
  renewable: number[]
  load: number[]
  price: number[]
}

const data = marketData as MarketData

export default function SolarPower() {
  const [selectedDate, setSelectedDate] = useState<string>('2026-02-01')

  // 模拟光伏数据分布（白天有，夜间无）
  const getSolarData = () => {
    const idx = data.dates.indexOf(selectedDate)
    if (idx === -1) return { hours: [], dayAhead: [], realTime: [], fullTime: [] }
    
    const base = data.solar[idx]
    const hours = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00']
    // 光伏出力分布：夜间0，白天高峰
    const dist = [0, 0, 20, 95, 100, 50, 0]
    
    return {
      hours,
      dayAhead: dist.map(v => base * v / 100),
      realTime: dist.map(v => base * v * (0.9 + Math.random() * 0.2) / 100),
      fullTime: dist.map(v => base * v * 1.05 / 100)
    }
  }

  const solarData = getSolarData()

  const heatmapOption = {
    backgroundColor: 'transparent',
    tooltip: { position: 'top' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: data.dates.slice(0, 15),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999', rotate: 45 }
    },
    yAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, i) => `${i}:00`),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    visualMap: {
      min: 0,
      max: 100,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      inRange: { color: ['#1f1f1f', '#faad14'] },
      textStyle: { color: '#999' }
    },
    series: [{
      name: '数据覆盖',
      type: 'heatmap',
      data: data.dates.slice(0, 15).flatMap((d, di) => 
        Array.from({ length: 24 }, (_, hi) => [di, hi, hi >= 6 && hi <= 18 ? Math.random() * 100 : null])
      ),
      label: { show: false },
      itemStyle: { borderColor: '#1f1f1f', borderWidth: 1 }
    }]
  }

  const chartOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['日前预测', '实时预测', '全时预测'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      data: solarData.hours,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '功率(MW)',
      min: 0,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '日前预测',
        type: 'line',
        data: solarData.dayAhead,
        smooth: true,
        itemStyle: { color: '#faad14' },
        areaStyle: { color: 'rgba(250, 173, 20, 0.2)' }
      },
      {
        name: '实时预测',
        type: 'line',
        data: solarData.realTime,
        smooth: true,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#f5222d' }
      },
      {
        name: '全时预测',
        type: 'line',
        data: solarData.fullTime,
        smooth: true,
        itemStyle: { color: '#52c41a' }
      }
    ]
  }

  return (
    <div>
      <Card title="现货数据上传总览" style={{ marginBottom: 16 }}>
        <ReactECharts option={heatmapOption} style={{ height: 300 }} />
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <Select
              value={selectedDate}
              onChange={setSelectedDate}
              style={{ width: 150 }}
              options={data.dates.map(d => ({ value: d, label: d }))}
            />
          </Col>
          <Col>
            <Button type="primary" icon={<SearchOutlined />}>查询</Button>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button type="primary" icon={<DownloadOutlined />}>下载光伏96点数据</Button>
          </Col>
        </Row>
      </Card>

      <Card>
        <ReactECharts option={chartOption} style={{ height: 400 }} />
      </Card>
    </div>
  )
}
