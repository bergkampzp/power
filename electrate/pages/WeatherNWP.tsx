import { useState } from 'react'
import { Card, Checkbox, DatePicker, Button, Row, Col, Table, Select, Alert } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'

const cities = [
  '南京', '无锡', '徐州', '常州', '苏州', '南通',
  '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁'
]

const mockData = [
  { time: '2026-03-10 00:00', temp: 5.6, wind10m: 2.47, wind80m: 4.96, wind100m: 5.26, dir10m: 104, dir80m: 99, dir100m: 97 },
  { time: '2026-03-10 03:00', temp: 4.2, wind10m: 2.12, wind80m: 4.35, wind100m: 4.68, dir10m: 108, dir80m: 102, dir100m: 100 },
  { time: '2026-03-10 06:00', temp: 3.8, wind10m: 1.89, wind80m: 3.92, wind100m: 4.21, dir10m: 112, dir80m: 105, dir100m: 103 },
  { time: '2026-03-10 09:00', temp: 7.5, wind10m: 2.68, wind80m: 5.12, wind100m: 5.48, dir10m: 98, dir80m: 94, dir100m: 92 },
  { time: '2026-03-10 12:00', temp: 12.3, wind10m: 3.15, wind80m: 5.89, wind100m: 6.32, dir10m: 88, dir80m: 85, dir100m: 83 },
  { time: '2026-03-10 15:00', temp: 14.2, wind10m: 3.42, wind80m: 6.21, wind100m: 6.68, dir10m: 82, dir80m: 79, dir100m: 77 },
  { time: '2026-03-10 18:00', temp: 11.8, wind10m: 2.95, wind80m: 5.68, wind100m: 6.12, dir10m: 92, dir80m: 88, dir100m: 86 },
  { time: '2026-03-10 21:00', temp: 8.5, wind10m: 2.56, wind80m: 5.02, wind100m: 5.42, dir10m: 102, dir80m: 97, dir100m: 95 },
]

const columns = [
  { title: '时间', dataIndex: 'time', key: 'time', width: 160 },
  { title: '温度(°C)', dataIndex: 'temp', key: 'temp', width: 100 },
  { title: '10m风速(m/s)', dataIndex: 'wind10m', key: 'wind10m', width: 120 },
  { title: '80m风速(m/s)', dataIndex: 'wind80m', key: 'wind80m', width: 120 },
  { title: '100m风速(m/s)', dataIndex: 'wind100m', key: 'wind100m', width: 120 },
  { title: '10m风向', dataIndex: 'dir10m', key: 'dir10m', width: 100 },
  { title: '80m风向', dataIndex: 'dir80m', key: 'dir80m', width: 100 },
  { title: '100m风向', dataIndex: 'dir100m', key: 'dir100m', width: 100 },
]

export default function WeatherNWP() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['南京'])
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-10'),
    dayjs('2026-03-19')
  ])
  const [model, setModel] = useState('gfs_global')

  const handleCityChange = (city: string, checked: boolean) => {
    if (checked) {
      setSelectedCities([...selectedCities, city])
    } else {
      setSelectedCities(selectedCities.filter(c => c !== city))
    }
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
      data: ['10m风速', '80m风速', '100m风速', '温度'],
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
      data: mockData.map(d => d.time),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999', rotate: 30 }
    },
    yAxis: [
      {
        type: 'value',
        name: '风速(m/s)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      },
      {
        type: 'value',
        name: '温度(°C)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '10m风速',
        type: 'line',
        data: mockData.map(d => d.wind10m),
        smooth: true,
        itemStyle: { color: '#1E88E5' }
      },
      {
        name: '80m风速',
        type: 'line',
        data: mockData.map(d => d.wind80m),
        smooth: true,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '100m风速',
        type: 'line',
        data: mockData.map(d => d.wind100m),
        smooth: true,
        itemStyle: { color: '#faad14' }
      },
      {
        name: '温度',
        type: 'line',
        yAxisIndex: 1,
        data: mockData.map(d => d.temp),
        smooth: true,
        itemStyle: { color: '#ff4d4f' }
      }
    ]
  }

  return (
    <div>
      <Card>
        {/* 工具栏 */}
        <div style={{ marginBottom: 24 }}>
          <Row gutter={[16, 16]} align="middle">
            <Col flex="auto">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
                {cities.map(city => (
                  <Checkbox
                    key={city}
                    checked={selectedCities.includes(city)}
                    onChange={(e) => handleCityChange(city, e.target.checked)}
                  >
                    {city}
                  </Checkbox>
                ))}
              </div>
            </Col>
          </Row>
          <Row gutter={[16, 16]} align="middle" style={{ marginTop: 16 }}>
            <Col>
              <DatePicker.RangePicker
                value={dateRange}
                onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
                format="YYYY-MM-DD"
              />
            </Col>
            <Col>
              <Select
                value={model}
                onChange={setModel}
                style={{ width: 180 }}
                options={[
                  { value: 'gfs_global', label: '美国 - gfs_global' },
                  { value: 'ecmwf', label: '欧洲 - ECMWF' },
                  { value: 'cma', label: '中国 - CMA' },
                ]}
              />
            </Col>
            <Col>
              <Button type="primary" icon={<SearchOutlined />}>获取数值预测数据</Button>
            </Col>
          </Row>
          <Alert
            message="数据日期范围要求：起止日期间隔不超过10天"
            type="info"
            showIcon
            style={{ marginTop: 16, background: '#1E88E520', border: '1px solid #1E88E5' }}
          />
        </div>

        {/* 数据表格 */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ color: '#fff', marginBottom: 16 }}>南京-数值预测信息</h3>
          <Table
            columns={columns}
            dataSource={mockData}
            pagination={false}
            size="small"
            scroll={{ x: 800, y: 300 }}
          />
        </div>

        {/* 图表 */}
        <div>
          <h3 style={{ color: '#fff', marginBottom: 16 }}>数值预测图表</h3>
          <ReactECharts
            option={chartOption}
            style={{ height: 350 }}
          />
        </div>
      </Card>
    </div>
  )
}
