import { useState, useEffect } from 'react'
import { Card, Checkbox, Button, Row, Col, DatePicker, Spin, Empty, Tag } from 'antd'
import { SearchOutlined, WarningOutlined } from '@ant-design/icons'
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

// 预警阈值
const THRESHOLDS = {
  precip: { warn: 10, danger: 25, label: '强降水' },
  temp_max: { warn: 32, danger: 37, label: '高温' },
  wind_speed_max: { warn: 10.8, danger: 17.2, label: '大风' },
}

function getAlerts(records: DailyRecord[]) {
  const alerts: { city: string; date: string; type: string; value: number; level: 'warning' | 'danger' }[] = []
  records.forEach(r => {
    Object.entries(THRESHOLDS).forEach(([key, cfg]) => {
      const val = r[key as keyof DailyRecord] as number
      if (val >= cfg.danger) alerts.push({ city: r.city, date: r.date, type: cfg.label, value: val, level: 'danger' })
      else if (val >= cfg.warn) alerts.push({ city: r.city, date: r.date, type: cfg.label, value: val, level: 'warning' })
    })
  })
  return alerts.sort((a, b) => (b.level === 'danger' ? 1 : 0) - (a.level === 'danger' ? 1 : 0))
}

export default function WeatherAlert() {
  const [selectedCities, setSelectedCities] = useState<string[]>([...CITIES])
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

  const alerts = getAlerts(data)
  const dangerCount = alerts.filter(a => a.level === 'danger').length
  const warnCount = alerts.filter(a => a.level === 'warning').length

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
          {data.length === 0 ? (
            <Empty description="暂无数据" style={{ padding: '40px 0' }} />
          ) : (
            <>
              {/* 统计概览 */}
              <Row gutter={16} style={{ marginBottom: 20 }}>
                <Col span={6}>
                  <div style={{ background: '#2a1215', border: '1px solid #5c0011', borderRadius: 8, padding: '12px 16px', textAlign: 'center' }}>
                    <div style={{ color: '#ff4d4f', fontSize: 28, fontWeight: 'bold' }}>{dangerCount}</div>
                    <div style={{ color: '#999', fontSize: 12 }}>红色预警</div>
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ background: '#2b1d11', border: '1px solid #613400', borderRadius: 8, padding: '12px 16px', textAlign: 'center' }}>
                    <div style={{ color: '#fa8c16', fontSize: 28, fontWeight: 'bold' }}>{warnCount}</div>
                    <div style={{ color: '#999', fontSize: 12 }}>橙色预警</div>
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ background: '#141414', border: '1px solid #303030', borderRadius: 8, padding: '12px 16px', textAlign: 'center' }}>
                    <div style={{ color: '#fff', fontSize: 28, fontWeight: 'bold' }}>{selectedCities.length}</div>
                    <div style={{ color: '#999', fontSize: 12 }}>监测地州数</div>
                  </div>
                </Col>
                <Col span={6}>
                  <div style={{ background: '#141414', border: '1px solid #303030', borderRadius: 8, padding: '12px 16px', textAlign: 'center' }}>
                    <div style={{ color: '#52c41a', fontSize: 28, fontWeight: 'bold' }}>
                      {selectedCities.length - new Set(alerts.map(a => a.city)).size}
                    </div>
                    <div style={{ color: '#999', fontSize: 12 }}>正常地州数</div>
                  </div>
                </Col>
              </Row>

              {/* 预警列表 */}
              {alerts.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '40px 0', color: '#52c41a' }}>
                  <div style={{ fontSize: 48, marginBottom: 8 }}>✓</div>
                  <div>所有地州气象指标正常，无预警</div>
                </div>
              ) : (
                <div>
                  <h3 style={{ color: '#fff', marginBottom: 12 }}>
                    <WarningOutlined style={{ color: '#fa8c16', marginRight: 8 }} />
                    气象预警列表
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {alerts.map((a, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        background: a.level === 'danger' ? '#2a1215' : '#2b1d11',
                        border: `1px solid ${a.level === 'danger' ? '#5c0011' : '#613400'}`,
                        borderRadius: 8, padding: '10px 16px',
                      }}>
                        <Tag color={a.level === 'danger' ? 'red' : 'orange'} style={{ minWidth: 60, textAlign: 'center' }}>
                          {a.level === 'danger' ? '红色' : '橙色'}
                        </Tag>
                        <span style={{ color: CITY_COLORS[CITIES.indexOf(a.city) % CITY_COLORS.length], fontWeight: 600, minWidth: 64 }}>
                          {a.city}
                        </span>
                        <span style={{ color: '#999', minWidth: 96 }}>{a.date}</span>
                        <Tag color={a.type === '强降水' ? 'blue' : a.type === '高温' ? 'volcano' : 'purple'}>
                          {a.type}预警
                        </Tag>
                        <span style={{ color: '#fff', marginLeft: 'auto' }}>
                          {a.type === '强降水' ? `降水 ${a.value} mm` : a.type === '高温' ? `最高温 ${a.value}°C` : `风速 ${a.value} m/s`}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </Spin>
      </Card>
    </div>
  )
}
