import { useState, useEffect } from 'react'
import { Card, Checkbox, Button, Row, Col, DatePicker, Spin, Empty } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'

const CITIES = ['昆明', '曲靖', '玉溪', '保山', '昭通', '丽江', '普洱', '临沧',
                '楚雄', '红河', '文山', '西双版纳', '大理', '德宏', '怒江', '迪庆']

const CITY_COLORS = [
  '#f5222d', '#fa541c', '#fa8c16', '#faad14', '#fadb14', '#a0d911',
  '#52c41a', '#13c2c2', '#1890ff', '#2f54eb', '#722ed1', '#eb2f96',
  '#ff85c0', '#ffd666', '#95de64', '#5cdbd3',
]

type DailyRecord = {
  city: string; date: string; temp_max: number; temp_min: number
  humidity: number; precip: number; wind_speed_max: number; cloud: number
}

export default function WeatherDaily() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['昆明', '曲靖', '大理'])
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-15'), dayjs('2026-03-24')
  ])
  const [data, setData] = useState<DailyRecord[]>([])
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    if (selectedCities.length === 0) return
    setLoading(true)
    try {
      const start = dateRange[0].format('YYYY-MM-DD')
      const end = dateRange[1].format('YYYY-MM-DD')
      const res = await fetch(`/api/weather/daily?start_date=${start}&end_date=${end}`)
      const json = await res.json()
      if (json.success) {
        setData((json.data as DailyRecord[]).filter(d => selectedCities.includes(d.city)))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleCityChange = (city: string, checked: boolean) =>
    setSelectedCities(checked ? [...selectedCities, city] : selectedCities.filter(c => c !== city))

  const handleSelectAll = (checked: boolean) =>
    setSelectedCities(checked ? [...CITIES] : [])

  // 按城市分组
  const byCity: Record<string, DailyRecord[]> = {}
  selectedCities.forEach(c => { byCity[c] = [] })
  data.forEach(d => { if (byCity[d.city]) byCity[d.city].push(d) })
  const dates = [...new Set(data.map(d => d.date))].sort()

  const tempOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
    legend: { data: selectedCities, textStyle: { color: '#999' }, top: 4, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '10%', top: 48, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' } },
    yAxis: { type: 'value', name: '°C', nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
    series: selectedCities.map((city, i) => ({
      name: city,
      type: 'line',
      smooth: true,
      showSymbol: true,
      symbolSize: 6,
      data: dates.map(d => byCity[city]?.find(r => r.date === d)?.temp_max ?? null),
      itemStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
      lineStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
    })),
  }

  const precipOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
    legend: { data: selectedCities, textStyle: { color: '#999' }, top: 4, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '10%', top: 48, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' } },
    yAxis: { type: 'value', name: 'mm', nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
    series: selectedCities.map((city, i) => ({
      name: city,
      type: 'bar',
      stack: undefined,
      data: dates.map(d => byCity[city]?.find(r => r.date === d)?.precip ?? null),
      itemStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
    })),
  }

  return (
    <div>
      <Card>
        <div style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]} align="middle">
            <Col>
              <Checkbox
                checked={selectedCities.length === CITIES.length}
                indeterminate={selectedCities.length > 0 && selectedCities.length < CITIES.length}
                onChange={e => handleSelectAll(e.target.checked)}
              >全选</Checkbox>
            </Col>
            <Col flex="auto">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {CITIES.map((city, i) => (
                  <Checkbox
                    key={city}
                    checked={selectedCities.includes(city)}
                    onChange={e => handleCityChange(city, e.target.checked)}
                    style={{ color: CITY_COLORS[i % CITY_COLORS.length] }}
                  >{city}</Checkbox>
                ))}
              </div>
            </Col>
          </Row>
          <Row gutter={16} align="middle" style={{ marginTop: 12 }}>
            <Col>
              <DatePicker.RangePicker
                value={dateRange}
                onChange={dates => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
                format="YYYY-MM-DD"
              />
            </Col>
            <Col>
              <Button type="primary" icon={<SearchOutlined />} onClick={fetchData} loading={loading}>
                查询
              </Button>
            </Col>
          </Row>
        </div>

        <Spin spinning={loading}>
          {data.length === 0 ? <Empty description="暂无数据" style={{ padding: '40px 0' }} /> : (
            <>
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ color: '#fff', marginBottom: 12 }}>云南各地州日最高气温（°C）</h3>
                <ReactECharts option={tempOption} style={{ height: 320 }} />
              </div>
              <div>
                <h3 style={{ color: '#fff', marginBottom: 12 }}>云南各地州日降水量（mm）</h3>
                <ReactECharts option={precipOption} style={{ height: 280 }} />
              </div>
            </>
          )}
        </Spin>
      </Card>
    </div>
  )
}
