import { useState } from 'react'
import { Card, DatePicker, Button, Row, Col, Checkbox } from 'antd'
import { SearchOutlined, DownloadOutlined, RedoOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'

const mockHeatmapData: any[] = []
for (let i = 0; i < 24; i++) {
  for (let j = 0; j < 15; j++) {
    mockHeatmapData.push([j, i, Math.random() > 0.3 ? Math.random() * 100 : null])
  }
}

const timeLabels = Array.from({ length: 15 }, (_, i) => dayjs('2026-03-05').add(i, 'day').format('MM-DD'))

const mockPriceData = [
  { time: '2026-03-05 00:00', dayAhead: 280, realTime: 275, fullTime: 285 },
  { time: '2026-03-05 04:00', dayAhead: 260, realTime: 255, fullTime: 265 },
  { time: '2026-03-05 08:00', dayAhead: 320, realTime: 315, fullTime: 325 },
  { time: '2026-03-05 12:00', dayAhead: 380, realTime: 375, fullTime: 385 },
  { time: '2026-03-05 16:00', dayAhead: 360, realTime: 355, fullTime: 365 },
  { time: '2026-03-05 20:00', dayAhead: 340, realTime: 335, fullTime: 345 },
  { time: '2026-03-05 24:00', dayAhead: 290, realTime: 285, fullTime: 295 },
]

export default function LoadPrice() {
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-05'),
    dayjs('2026-03-19')
  ])

  const heatmapOption = {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: timeLabels,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
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
      inRange: {
        color: ['#1f1f1f', '#f5222d']
      },
      textStyle: { color: '#999' }
    },
    series: [{
      name: '数据覆盖',
      type: 'heatmap',
      data: mockHeatmapData,
      label: { show: false },
      itemStyle: {
        borderColor: '#1f1f1f',
        borderWidth: 1
      }
    }]
  }

  const chartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['日前预测', '实时预测', '全时预测'],
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
      data: mockPriceData.map(d => d.time.split(' ')[1]),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '电价(元/MWh)',
      min: 0,
      max: 400,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '日前预测',
        type: 'line',
        data: mockPriceData.map(d => d.dayAhead),
        smooth: true,
        itemStyle: { color: '#f5222d' }
      },
      {
        name: '实时预测',
        type: 'line',
        data: mockPriceData.map(d => d.realTime),
        smooth: true,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: '#faad14' }
      },
      {
        name: '全时预测',
        type: 'line',
        data: mockPriceData.map(d => d.fullTime),
        smooth: true,
        itemStyle: { color: '#52c41a' }
      }
    ]
  }

  return (
    <div>
      {/* 现货数据上传总览 */}
      <Card title="现货数据上传总览" style={{ marginBottom: 16 }}>
        <ReactECharts
          option={heatmapOption}
          style={{ height: 300 }}
        />
      </Card>

      {/* 工具栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <DatePicker.RangePicker
              value={dateRange}
              onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              format="YYYY-MM-DD"
            />
          </Col>
          <Col>
            <Button type="primary" icon={<SearchOutlined />}>查询</Button>
          </Col>
          <Col>
            <Button icon={<RedoOutlined />}>数据更新时间</Button>
          </Col>
          <Col flex="auto" />
          <Col>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <Checkbox>日期</Checkbox>
              <Checkbox>全时</Checkbox>
              <Checkbox>日前预测</Checkbox>
            </div>
          </Col>
          <Col>
            <div style={{ display: 'flex', gap: 8 }}>
              <span style={{ color: '#999' }}>96点: 0</span>
              <span style={{ color: '#999' }}>24点: 0</span>
            </div>
          </Col>
          <Col>
            <Button type="primary" icon={<DownloadOutlined />}>下载电价96点数据</Button>
          </Col>
        </Row>
      </Card>

      {/* 图表 */}
      <Card title="电价预测">
        <ReactECharts
          option={chartOption}
          style={{ height: 400 }}
        />
      </Card>
    </div>
  )
}
