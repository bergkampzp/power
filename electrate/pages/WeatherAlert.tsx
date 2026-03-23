import { useState } from 'react'
import { Card, Checkbox, DatePicker, Button, Row, Col, Empty } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

const cities = [
  '南京', '无锡', '徐州', '常州', '苏州', '南通',
  '连云港', '淮安', '盐城', '扬州', '镇江', '泰州', '宿迁'
]

export default function WeatherAlert() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['南京'])
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-09'),
    dayjs('2026-03-12')
  ])

  const handleCityChange = (city: string, checked: boolean) => {
    if (checked) {
      setSelectedCities([...selectedCities, city])
    } else {
      setSelectedCities(selectedCities.filter(c => c !== city))
    }
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedCities(cities)
    } else {
      setSelectedCities([])
    }
  }

  return (
    <div>
      <Card>
        {/* 筛选工具栏 */}
        <div style={{ marginBottom: 24 }}>
          <Row gutter={[16, 16]} align="middle">
            <Col>
              <Checkbox
                checked={selectedCities.length === cities.length}
                indeterminate={selectedCities.length > 0 && selectedCities.length < cities.length}
                onChange={(e) => handleSelectAll(e.target.checked)}
              >
                全选
              </Checkbox>
            </Col>
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
              <Button type="primary" icon={<SearchOutlined />}>查询</Button>
            </Col>
          </Row>
        </div>

        {/* 数据展示区 */}
        <Empty
          description="暂无数据"
          style={{ padding: '60px 0' }}
        />
      </Card>
    </div>
  )
}
