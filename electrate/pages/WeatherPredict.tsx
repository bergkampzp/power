import { useState } from 'react'
import { Card, Checkbox, Button, Row, Col, Table } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'

const cities = [
  '南京', '无锡', '徐州', '常州', '苏州', '南通',
  '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁'
]

const mockData = [
  { time: '2026-03-12 12:00', temp: 14, weather: '晴', windDir360: 48, windDir: '东北风', windLevel: 2, windSpeed: 9 },
  { time: '2026-03-12 13:00', temp: 15, weather: '晴', windDir360: 43, windDir: '东北风', windLevel: 2, windSpeed: 9 },
  { time: '2026-03-12 14:00', temp: 16, weather: '晴', windDir360: 38, windDir: '东北风', windLevel: 2, windSpeed: 10 },
  { time: '2026-03-12 15:00', temp: 16, weather: '晴', windDir360: 35, windDir: '东北风', windLevel: 2, windSpeed: 10 },
  { time: '2026-03-12 16:00', temp: 15, weather: '晴', windDir360: 40, windDir: '东北风', windLevel: 2, windSpeed: 9 },
  { time: '2026-03-12 17:00', temp: 14, weather: '晴', windDir360: 45, windDir: '东北风', windLevel: 2, windSpeed: 8 },
  { time: '2026-03-12 18:00', temp: 12, weather: '晴', windDir360: 50, windDir: '东北风', windLevel: 1, windSpeed: 7 },
  { time: '2026-03-12 19:00', temp: 11, weather: '晴', windDir360: 55, windDir: '东北偏东风', windLevel: 1, windSpeed: 6 },
  { time: '2026-03-12 20:00', temp: 10, weather: '晴', windDir360: 60, windDir: '东北偏东风', windLevel: 1, windSpeed: 6 },
  { time: '2026-03-12 21:00', temp: 9, weather: '晴', windDir360: 65, windDir: '东北偏东风', windLevel: 1, windSpeed: 6 },
  { time: '2026-03-12 22:00', temp: 9, weather: '晴', windDir360: 70, windDir: '东北偏东风', windLevel: 2, windSpeed: 7 },
  { time: '2026-03-12 23:00', temp: 8, weather: '晴', windDir360: 75, windDir: '东北偏东风', windLevel: 2, windSpeed: 7 },
]

const columns = [
  { title: '预报时间', dataIndex: 'time', key: 'time', width: 160 },
  { title: '温度(°C)', dataIndex: 'temp', key: 'temp', width: 100 },
  { title: '天气状况', dataIndex: 'weather', key: 'weather', width: 100 },
  { title: '风向360角度', dataIndex: 'windDir360', key: 'windDir360', width: 120 },
  { title: '风向', dataIndex: 'windDir', key: 'windDir', width: 120 },
  { title: '风力等级', dataIndex: 'windLevel', key: 'windLevel', width: 100 },
  { title: '风速(km/h)', dataIndex: 'windSpeed', key: 'windSpeed', width: 120 },
]

export default function WeatherPredict() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['南京'])

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
      data: ['温度', '风速', '风向'],
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
      data: mockData.map(d => d.time.split(' ')[1]),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: [
      {
        type: 'value',
        name: '温度(°C)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      },
      {
        type: 'value',
        name: '风速(km/h)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '温度',
        type: 'line',
        data: mockData.map(d => d.temp),
        smooth: true,
        itemStyle: { color: '#ff4d4f' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(255, 77, 79, 0.3)' },
              { offset: 1, color: 'rgba(255, 77, 79, 0.05)' }
            ]
          }
        }
      },
      {
        name: '风速',
        type: 'line',
        yAxisIndex: 1,
        data: mockData.map(d => d.windSpeed),
        smooth: true,
        itemStyle: { color: '#1E88E5' }
      },
      {
        name: '风向',
        type: 'scatter',
        yAxisIndex: 1,
        data: mockData.map(d => d.windDir360 / 10),
        itemStyle: { color: '#52c41a' }
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
          <Row style={{ marginTop: 16 }}>
            <Col>
              <Button type="primary" icon={<SearchOutlined />}>获取气象预测</Button>
            </Col>
          </Row>
        </div>

        {/* 数据表格 */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ color: '#fff', marginBottom: 16 }}>南京-气象预测信息</h3>
          <Table
            columns={columns}
            dataSource={mockData}
            pagination={false}
            size="small"
            scroll={{ y: 300 }}
          />
        </div>

        {/* 图表 */}
        <div>
          <h3 style={{ color: '#fff', marginBottom: 16 }}>气象预测图表</h3>
          <ReactECharts
            option={chartOption}
            style={{ height: 350 }}
          />
        </div>
      </Card>
    </div>
  )
}
