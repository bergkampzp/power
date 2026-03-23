import { useState } from 'react'
import { Card, Checkbox, Button, Row, Col } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'

const cities = [
  '南京', '无锡', '徐州', '常州', '苏州', '南通',
  '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁'
]

const dailyData = [
  { date: '2026-03-12', temp: 14, precip: 0 },
  { date: '2026-03-13', temp: 16, precip: 0 },
  { date: '2026-03-14', temp: 18, precip: 0 },
  { date: '2026-03-15', temp: 20, precip: 0 },
  { date: '2026-03-16', temp: 19, precip: 5 },
  { date: '2026-03-17', temp: 17, precip: 12 },
  { date: '2026-03-18', temp: 15, precip: 8 },
  { date: '2026-04-13', temp: 22, precip: 0 },
]

export default function WeatherDaily() {
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
      data: ['温度(预估)', '降水(≥62 km/h)'],
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
      data: dailyData.map(d => d.date),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: [
      {
        type: 'value',
        name: '温度(°C)',
        min: 0,
        max: 25,
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      },
      {
        type: 'value',
        name: '降水(mm)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '温度(预估)',
        type: 'line',
        data: dailyData.map(d => d.temp),
        smooth: true,
        itemStyle: { color: '#999' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(153, 153, 153, 0.3)' },
              { offset: 1, color: 'rgba(153, 153, 153, 0.05)' }
            ]
          }
        }
      },
      {
        name: '降水(≥62 km/h)',
        type: 'scatter',
        yAxisIndex: 1,
        data: dailyData.map(d => d.precip),
        symbolSize: 15,
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
          <Row style={{ marginTop: 16 }}>
            <Col>
              <Button type="primary" icon={<SearchOutlined />}>获取气象预测</Button>
            </Col>
          </Row>
        </div>

        {/* 图表 */}
        <div>
          <h3 style={{ color: '#fff', marginBottom: 16 }}>南京-气象预测信息</h3>
          <h4 style={{ color: '#999', marginBottom: 16 }}>温度预报区域</h4>
          <ReactECharts
            option={chartOption}
            style={{ height: 400 }}
          />
        </div>
      </Card>
    </div>
  )
}
