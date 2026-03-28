import { useState, useEffect } from 'react'
import { Card, Checkbox, Button, Row, Col, DatePicker, Spin, Empty, Table } from 'antd'
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

type HourlyRecord = {
  city: string; date: string; hour: number
  temp: number | null; humidity: number | null
  wind_speed: number | null; wind_360: number | null
  precip: number | null; cloud: number | null
}

export default function WeatherPredict() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['昆明'])
  const [selectedDate, setSelectedDate] = useState(dayjs('2026-03-20'))
  const [data, setData] = useState<HourlyRecord[]>([])
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    if (selectedCities.length === 0) return
    setLoading(true)
    try {
      const dateStr = selectedDate.format('YYYYMMDD')
      const res = await fetch(`/api/weather/hourly?date=${dateStr}`)
      const json = await res.json()
      if (json.success) {
        setData((json.data as HourlyRecord[]).filter(d => selectedCities.includes(d.city)))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleCityChange = (city: string, checked: boolean) =>
    setSelectedCities(checked ? [...selectedCities, city] : selectedCities.filter(c => c !== city))

  const hours = Array.from({ length: 24 }, (_, i) => i)
  const byCity: Record<string, HourlyRecord[]> = {}
  selectedCities.forEach(c => { byCity[c] = [] })
  data.forEach(d => { if (byCity[d.city]) byCity[d.city].push(d) })

  const tempOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
    legend: { data: selectedCities, textStyle: { color: '#999' }, top: 4, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '10%', top: 48, containLabel: true },
    xAxis: { type: 'category', data: hours.map(h => `${String(h).padStart(2,'0')}:00`), axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 2 } },
    yAxis: { type: 'value', name: '°C', nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
    series: selectedCities.map((city, i) => ({
      name: city,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: hours.map(h => byCity[city]?.find(r => r.hour === h)?.temp ?? null),
      itemStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
      lineStyle: { color: CITY_COLORS[i % CITY_COLORS.length], width: 2 },
      areaStyle: selectedCities.length === 1 ? {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: CITY_COLORS[i % CITY_COLORS.length] + '40' }, { offset: 1, color: CITY_COLORS[i % CITY_COLORS.length] + '05' }] }
      } : undefined,
    })),
  }

  const windOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
    legend: { data: selectedCities, textStyle: { color: '#999' }, top: 4, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '10%', top: 48, containLabel: true },
    xAxis: { type: 'category', data: hours.map(h => `${String(h).padStart(2,'0')}:00`), axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 2 } },
    yAxis: { type: 'value', name: 'm/s', nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
    series: selectedCities.map((city, i) => ({
      name: city,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: hours.map(h => byCity[city]?.find(r => r.hour === h)?.wind_speed ?? null),
      itemStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
      lineStyle: { color: CITY_COLORS[i % CITY_COLORS.length], width: 2 },
    })),
  }

  // 表格：仅展示第一个选中城市的逐小时数据
  const tableCity = selectedCities[0]
  const tableData = byCity[tableCity] || []
  const columns = [
    { title: '时间', dataIndex: 'hour', key: 'hour', width: 80, render: (h: number) => `${String(h).padStart(2,'0')}:00` },
    { title: '温度(°C)', dataIndex: 'temp', key: 'temp', width: 100 },
    { title: '湿度(%)', dataIndex: 'humidity', key: 'humidity', width: 100 },
    { title: '降水(mm)', dataIndex: 'precip', key: 'precip', width: 100 },
    { title: '风速(m/s)', dataIndex: 'wind_speed', key: 'wind_speed', width: 110, render: (v: number | null) => v?.toFixed(2) ?? '-' },
    { title: '风向(°)', dataIndex: 'wind_360', key: 'wind_360', width: 100 },
    { title: '云量(%)', dataIndex: 'cloud', key: 'cloud', width: 100 },
  ]

  return (
    <div>
      <Card>
        <div style={{ marginBottom: 16 }}>
          <Row gutter={[16, 8]} align="middle">
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
              <DatePicker
                value={selectedDate}
                onChange={d => d && setSelectedDate(d)}
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
                <h3 style={{ color: '#fff', marginBottom: 12 }}>逐小时温度（°C）</h3>
                <ReactECharts option={tempOption} style={{ height: 280 }} />
              </div>
              <div style={{ marginBottom: 24 }}>
                <h3 style={{ color: '#fff', marginBottom: 12 }}>逐小时风速（m/s）</h3>
                <ReactECharts option={windOption} style={{ height: 240 }} />
              </div>
              {tableCity && tableData.length > 0 && (
                <div>
                  <h3 style={{ color: '#fff', marginBottom: 12 }}>{tableCity} — 逐小时详情</h3>
                  <Table
                    columns={columns}
                    dataSource={tableData.map(r => ({ ...r, key: r.hour }))}
                    pagination={false}
                    size="small"
                    scroll={{ x: 700, y: 300 }}
                  />
                </div>
              )}
            </>
          )}
        </Spin>
      </Card>
    </div>
  )
}
