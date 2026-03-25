import { useState } from 'react'
import { Card, DatePicker, Button, Row, Col, Select } from 'antd'
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import marketData from '../src/data/market_data.json'

interface MarketData {
  dates: string[]
  load: number[]
  demand: number[]
  price: number[]
}

const data = marketData as MarketData

export default function LoadPower() {
  const [selectedDate, setSelectedDate] = useState<string>('2026-02-01')

  // 模拟负荷数据分布
  const getLoadData = () => {
    const idx = data.dates.indexOf(selectedDate)
    if (idx === -1) return { hours: [], dayAhead: [], realTime: [], fullTime: [] }
    
    const base = data.load[idx]
    const hours = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00']
    // 负荷分布：夜间低，白天高
    const dist = [65, 58, 55, 75, 95, 105, 70]
    
    return {
      hours,
      dayAhead: dist.map(v => base * v / 100),
      realTime: dist.map(v => base * v * (0.95 + Math.random() * 0.1) / 100),
      fullTime: dist.map(v => base * v * 1.02 / 100)
    }
  }

  const loadData = getLoadData()

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
      inRange: { color: ['#1f1f1f', '#eb2f96'] },
      textStyle: { color: '#999' }
    },
    series: [{
      name: '数据覆盖',
      type: 'heatmap',
      data: data.dates.slice(0, 15).flatMap((d, di) => 
        Array.from({ length: 24 }, (_, hi) => [di, hi, Math.random() > 0.1 ? Math.random() * 100 : null])
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
      data: loadData.hours,
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
        data: loadData.dayAhead,
        smooth: true,
        itemStyle: { color: '#eb2f96' }
      },
      {
        name: '实时预测',
        type: 'line',
        data: loadData.realTime,
        smooth: true,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#faad14' }
      },
      {
        name: '全时预测',
        type: 'line',
        data: loadData.fullTime,
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
            <Button type="primary" icon={<DownloadOutlined />}>下载负荷96点数据</Button>
          </Col>
        </Row>
      </Card>

      <Card>
        <ReactECharts option={chartOption} style={{ height: 400 }} />
      </Card>
    </div>
  )
}
