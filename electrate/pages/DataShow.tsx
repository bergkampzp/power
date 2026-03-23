import { useState, useEffect } from 'react'
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
  demand: number[]
  price: number[]
  min_price: number[]
  max_price: number[]
}

const data = marketData as MarketData

export default function DataShow() {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-02-01'),
    dayjs('2026-03-10')
  ])
  const [selectedDate, setSelectedDate] = useState<string>('2026-02-01')

  // 找到选中日期的索引
  const dateIndex = data.dates.indexOf(selectedDate)
  
  // 获取日前数据（当天）和实时数据（假设是后一天）
  const getHourlyData = (dateStr: string) => {
    const idx = data.dates.indexOf(dateStr)
    if (idx === -1) return null
    
    // 模拟日前数据（基于当天平均值，按时段分布）
    const baseSolar = data.solar[idx]
    const baseRenewable = data.renewable[idx]
    const baseLoad = data.load[idx]
    const basePrice = data.price[idx]
    
    // 生成24小时分布
    const hours = ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00']
    
    // 光伏出力：白天高夜间低
    const solarDist = [0, 0, 10, 80, 100, 60, 0]
    const solar = solarDist.map(v => baseSolar * v / 100)
    
    // 风电：有一定波动
    const windDist = [90, 85, 80, 75, 80, 90, 95]
    const wind = windDist.map(v => baseRenewable * v / 100 * 0.3)
    
    // 负荷：白天高夜间低
    const loadDist = [65, 58, 55, 70, 95, 105, 90, 75]
    const load = loadDist.map(v => baseLoad * v / 100)
    
    // 外来电
    const external = load.map((v, i) => v * 0.8)
    
    // 电价
    const priceDist = [85, 80, 75, 110, 130, 120, 95]
    const price = priceDist.map(v => basePrice * v / 100)
    
    return { hours, solar, wind, renewable: wind.map((w, i) => w + solar[i]), load, external, price }
  }

  const hourlyData = getHourlyData(selectedDate)

  const marketBoundaryOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['光伏出力', '风电出力', '总新能源', '负荷', '外来电'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: hourlyData?.hours || [],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '功率(MW)',
      min: 0,
      max: 45000,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '光伏出力',
        type: 'line',
        data: hourlyData?.solar || [],
        smooth: true,
        itemStyle: { color: '#faad14' },
        areaStyle: { color: 'rgba(250, 173, 20, 0.2)' }
      },
      {
        name: '风电出力',
        type: 'line',
        data: hourlyData?.wind || [],
        smooth: true,
        itemStyle: { color: '#1E88E5' }
      },
      {
        name: '总新能源',
        type: 'line',
        data: hourlyData?.renewable || [],
        smooth: true,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '负荷',
        type: 'line',
        data: hourlyData?.load || [],
        smooth: true,
        itemStyle: { color: '#f5222d' }
      },
      {
        name: '外来电',
        type: 'line',
        data: hourlyData?.external || [],
        smooth: true,
        itemStyle: { color: '#722ed1' }
      }
    ]
  }

  const priceOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['日前电价', '电价区间'],
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
      data: hourlyData?.hours || [],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '电价(元/MWh)',
      min: 0,
      max: Math.max(...(data.max_price || [500])) * 1.2,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '日前电价',
        type: 'line',
        data: hourlyData?.price || [],
        smooth: true,
        itemStyle: { color: '#f5222d' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245, 34, 45, 0.3)' },
              { offset: 1, color: 'rgba(245, 34, 45, 0.05)' }
            ]
          }
        }
      }
    ]
  }

  // 日趋势图
  const dailyTrendOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['新能源出力', '负荷', '电价'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: data.dates,
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
        name: '电价(元/MWh)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '新能源出力',
        type: 'line',
        data: data.renewable,
        smooth: true,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '负荷',
        type: 'line',
        data: data.load,
        smooth: true,
        itemStyle: { color: '#f5222d' }
      },
      {
        name: '电价',
        type: 'line',
        yAxisIndex: 1,
        data: data.price,
        smooth: true,
        itemStyle: { color: '#faad14' }
      }
    ]
  }

  return (
    <div>
      {/* 市场边界预测 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <h3 style={{ color: '#fff', margin: 0 }}>市场边界预测</h3>
          </Col>
          <Col flex="auto" />
          <Col>
            <Select
              value={selectedDate}
              onChange={setSelectedDate}
              style={{ width: 150 }}
              options={data.dates.map(d => ({ value: d, label: d }))}
            />
          </Col>
          <Col>
            <Button type="primary" icon={<DownloadOutlined />}>下载功率数据</Button>
          </Col>
        </Row>
        <ReactECharts
          option={marketBoundaryOption}
          style={{ height: 400 }}
        />
      </Card>

      {/* 现货电价预测 */}
      <Card style={{ marginBottom: 16 }}>
        <h3 style={{ color: '#fff', marginBottom: 16 }}>现货电价预测</h3>
        <ReactECharts
          option={priceOption}
          style={{ height: 350 }}
        />
      </Card>

      {/* 日趋势 */}
      <Card>
        <h3 style={{ color: '#fff', marginBottom: 16 }}>日趋势分析</h3>
        <ReactECharts
          option={dailyTrendOption}
          style={{ height: 400 }}
        />
      </Card>
    </div>
  )
}
