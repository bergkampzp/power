import { useState, useEffect } from 'react'
import { Card, Checkbox, Button, Row, Col, DatePicker, Spin, Empty, Select, Table } from 'antd'
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

export default function WeatherNWP() {
  const [selectedCities, setSelectedCities] = useState<string[]>(['昆明', '大理', '昭通'])
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-03-20'), dayjs('2026-03-20')
  ])
  const [field, setField] = useState<'temp' | 'wind_speed' | 'humidity' | 'precip'>('temp')
  const [data, setData] = useState<HourlyRecord[]>([])
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    if (selectedCities.length === 0) return
    setLoading(true)
    try {
      const dateStr = dateRange[0].format('YYYYMMDD')
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

  const handleSelectAll = (checked: boolean) =>
    setSelectedCities(checked ? [...CITIES] : [])

  const hours = Array.from({ length: 24 }, (_, i) => i)
  const byCity: Record<string, HourlyRecord[]> = {}
  selectedCities.forEach(c => { byCity[c] = [] })
  data.forEach(d => { if (byCity[d.city]) byCity[d.city].push(d) })

  const fieldLabels: Record<string, string> = {
    temp: '温度(°C)', wind_speed: '风速(m/s)', humidity: '湿度(%)', precip: '降水(mm)'
  }

  const chartOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
    legend: { data: selectedCities, textStyle: { color: '#999' }, top: 4, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '10%', top: 48, containLabel: true },
    xAxis: { type: 'category', data: hours.map(h => `${String(h).padStart(2,'0')}:00`), axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 2 } },
    yAxis: { type: 'value', name: fieldLabels[field], nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
    series: selectedCities.map((city, i) => ({
      name: city,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: hours.map(h => {
        const r = byCity[city]?.find(r => r.hour === h)
        return r ? (r[field] ?? null) : null
      }),
      itemStyle: { color: CITY_COLORS[i % CITY_COLORS.length] },
      lineStyle: { color: CITY_COLORS[i % CITY_COLORS.length], width: 2 },
    })),
  }

  // 表格：所有城市 × 某几个小时的对比
  const pivotHours = [0, 3, 6, 9, 12, 15, 18, 21]
  const tableColumns = [
    { title: '地州', dataIndex: 'city', key: 'city', fixed: 'left' as const, width: 90 },
    ...pivotHours.map(h => ({
      title: `${String(h).padStart(2,'0')}:00`,
      dataIndex: `h${h}`,
      key: `h${h}`,
      width: 80,
      render: (v: number | null) => v != null ? v.toFixed(1) : '-',
    }))
  ]
  const tableData = selectedCities.map(city => {
    const row: any = { key: city, city }
    pivotHours.forEach(h => {
      const r = byCity[city]?.find(r => r.hour === h)
      row[`h${h}`] = r ? (r[field] ?? null) : null
    })
    return row
  })

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
              <Select
                value={field}
                onChange={v => setField(v)}
                style={{ width: 140 }}
                options={[
                  { value: 'temp', label: '温度' },
                  { value: 'wind_speed', label: '风速' },
                  { value: 'humidity', label: '湿度' },
                  { value: 'precip', label: '降水' },
                ]}
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
                <h3 style={{ color: '#fff', marginBottom: 12 }}>
                  云南各地州逐小时{fieldLabels[field]}对比（{dateRange[0].format('YYYY-MM-DD')}）
                </h3>
                <ReactECharts option={chartOption} style={{ height: 320 }} />
              </div>
              <div>
                <h3 style={{ color: '#fff', marginBottom: 12 }}>各时段{fieldLabels[field]}对比表</h3>
                <Table
                  columns={tableColumns}
                  dataSource={tableData}
                  pagination={false}
                  size="small"
                  scroll={{ x: 800 }}
                />
              </div>
            </>
          )}
        </Spin>
      </Card>
    </div>
  )
}
