/**
 * 电价总览 V2.0
 */
import { useState, useEffect, useRef } from 'react'
import { Card, Row, Col, DatePicker, Spin, Alert, Empty, Tag, Statistic, Badge } from 'antd'
import { LineChartOutlined, ThunderboltOutlined, RiseOutlined, ClockCircleOutlined } from '@ant-design/icons'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { priceService } from '../src/services'

const SingleDatePicker = DatePicker

const C = {
  dayAheadNode: '#f5222d',
  dayAheadDemand: '#1890ff',
  realtimeNode: '#52c41a',
  realtimeDemand: '#722ed1',
  solar: '#fadb14',
  predicted: '#faad14',
  actual: '#13c2c2',
}

const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`)

type PredDay = { date: string; predicted: number[]; actual: (number | null)[] }
type DemandSolar = { hour: number; period: string; demand: number | null; solar_forecast: number | null }

export default function PriceOverviewV2() {
  const [selectedDate, setSelectedDate] = useState(dayjs('2026-03-10'))
  const [dayAheadNode, setDayAheadNode] = useState<any[]>([])
  const [dayAheadDemand, setDayAheadDemand] = useState<any[]>([])
  const [realtimeNode, setRealtimeNode] = useState<any[]>([])
  const [demandSolar, setDemandSolar] = useState<DemandSolar[]>([])
  const [predHourly, setPredHourly] = useState<PredDay[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const chart1Ref = useRef<HTMLDivElement>(null)
  const chart2Ref = useRef<HTMLDivElement>(null)
  const chart3Ref = useRef<HTMLDivElement>(null)
  const chart4Ref = useRef<HTMLDivElement>(null)
  const predChart0Ref = useRef<HTMLDivElement>(null)
  const predChart1Ref = useRef<HTMLDivElement>(null)
  const predChart2Ref = useRef<HTMLDivElement>(null)
  const predChartRefs = [predChart0Ref, predChart1Ref, predChart2Ref]

  const fetchData = async () => {
    setLoading(true)
    setError(null)
    const dateStr = selectedDate.format('YYYY-MM-DD')
    try {
      const [daNode, daDemand, rtNode, rtDemandSolar, predH] = await Promise.all([
        priceService.getDayAheadNodePrice(dateStr),
        priceService.getDayAheadDemandPrice(dateStr),
        priceService.getRealtimeNodePrice(dateStr),
        priceService.getRealtimeDemandWithSolar(dateStr),
        priceService.get3DayPredictionHourly(dateStr),
      ])
      setDayAheadNode(daNode || [])
      setDayAheadDemand(daDemand || [])
      setRealtimeNode(rtNode || [])
      setDemandSolar(rtDemandSolar || [])
      setPredHourly(predH || [])
    } catch (err: any) {
      setError(err.message || '获取数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [selectedDate])

  // 96点 -> 24小时均价
  const transform96to24 = (data: any[]): (number | null)[] => {
    const hourly = new Array(24).fill(0)
    const count = new Array(24).fill(0)
    data.forEach((item: any) => {
      const hour = parseInt(item.period.split(':')[0])
      if (hour >= 0 && hour < 24) { hourly[hour] += item.avg || 0; count[hour]++ }
    })
    return hourly.map((v, i) => count[i] > 0 ? v / count[i] : null)
  }

  // 分时 -> 24小时均值（demand字段）
  const transform48to24 = (data: any[]): (number | null)[] => {
    const hourly = new Array(24).fill(0)
    const count = new Array(24).fill(0)
    data.forEach((item: any) => {
      const hour = parseInt(item.period.split(':')[0])
      if (hour >= 0 && hour < 24) { hourly[hour] += item.demand || 0; count[hour]++ }
    })
    return hourly.map((v, i) => count[i] > 0 ? v / count[i] : null)
  }

  const calcStats = (data: (number | null)[]) => {
    const valid = data.filter(v => v != null) as number[]
    if (valid.length === 0) return { avg: '0', max: '0', min: '0' }
    return {
      avg: (valid.reduce((a, b) => a + b, 0) / valid.length).toFixed(1),
      max: Math.max(...valid).toFixed(1),
      min: Math.min(...valid).toFixed(1),
    }
  }

  // 图表1-3：简单单线图
  useEffect(() => {
    const charts = [
      { ref: chart1Ref, data: transform96to24(dayAheadNode), color: C.dayAheadNode, title: '日前节点电价', yUnit: '元/MWh' },
      { ref: chart2Ref, data: transform48to24(dayAheadDemand), color: C.dayAheadDemand, title: '日前用电侧负荷', yUnit: 'MW' },
      { ref: chart3Ref, data: transform96to24(realtimeNode), color: C.realtimeNode, title: '实时节点电价', yUnit: '元/MWh' },
    ]
    charts.forEach(({ ref, data, color, title, yUnit }) => {
      if (!ref.current) return
      const inst = echarts.getInstanceByDom(ref.current) || echarts.init(ref.current)
      inst.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: '#2a2a2a', borderColor: '#434343', textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
        xAxis: { type: 'category', data: HOURS, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 5 } },
        yAxis: { type: 'value', name: yUnit, nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
        series: [{ name: title, type: 'line', data, smooth: true, showSymbol: false, itemStyle: { color }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '40' }, { offset: 1, color: color + '05' }] } } }],
      })
    })
  }, [dayAheadNode, dayAheadDemand, realtimeNode])

  // 图表4：实时用电侧负荷 + 光伏预测出力（双系列，共用 Y 轴，单位均为 MW）
  useEffect(() => {
    if (!chart4Ref.current || demandSolar.length === 0) return
    const demandData = demandSolar.map(d => d.demand)
    const solarData = demandSolar.map(d => d.solar_forecast)
    const hasSolar = solarData.some(v => v !== null && v > 0)
    const inst = echarts.getInstanceByDom(chart4Ref.current) || echarts.init(chart4Ref.current)
    inst.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#2a2a2a',
        borderColor: '#434343',
        textStyle: { color: '#fff' },
        formatter: (params: any) => {
          let html = `<div style="margin-bottom:4px;color:#aaa">${params[0]?.axisValue}</div>`
          params.forEach((p: any) => {
            const val = p.value != null ? `${Number(p.value).toFixed(1)} MW` : '暂无'
            html += `<div>${p.marker}${p.seriesName}: <b>${val}</b></div>`
          })
          return html
        },
      },
      legend: {
        data: ['实时用电侧负荷', ...(hasSolar ? ['光伏预测出力'] : [])],
        textStyle: { color: '#999' },
        top: 2,
        right: 8,
      },
      grid: { left: '3%', right: '4%', bottom: '10%', top: 32, containLabel: true },
      xAxis: { type: 'category', data: HOURS, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 5 } },
      yAxis: [
        {
          type: 'value',
          name: '负荷 (MW)',
          nameTextStyle: { color: C.realtimeDemand },
          axisLine: { lineStyle: { color: C.realtimeDemand } },
          axisLabel: { color: C.realtimeDemand },
          splitLine: { lineStyle: { color: '#303030' } },
          position: 'left',
        },
        {
          type: 'value',
          name: '光伏 (MW)',
          nameTextStyle: { color: C.solar },
          axisLine: { lineStyle: { color: C.solar } },
          axisLabel: { color: C.solar },
          splitLine: { show: false },
          position: 'right',
        },
      ],
      series: [
        {
          name: '实时用电侧负荷',
          type: 'line',
          data: demandData,
          smooth: true,
          showSymbol: false,
          yAxisIndex: 0,
          itemStyle: { color: C.realtimeDemand },
          lineStyle: { color: C.realtimeDemand, width: 2 },
          areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: C.realtimeDemand + '40' }, { offset: 1, color: C.realtimeDemand + '05' }] } },
        },
        ...(hasSolar ? [{
          name: '光伏预测出力',
          type: 'line',
          data: solarData,
          smooth: true,
          showSymbol: false,
          yAxisIndex: 1,
          itemStyle: { color: C.solar },
          lineStyle: { color: C.solar, width: 2, type: 'dashed' as const },
          areaStyle: { color: { type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: C.solar + '35' }, { offset: 1, color: C.solar + '05' }] } },
        }] : []),
      ],
    })
  }, [demandSolar])

  // 预测对比图（3天）
  useEffect(() => {
    predHourly.forEach((day, idx) => {
      const ref = predChartRefs[idx]
      if (!ref.current) return
      const hasActual = day.actual.some(v => v !== null)
      const inst = echarts.getInstanceByDom(ref.current) || echarts.init(ref.current)
      inst.setOption({
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'axis',
          backgroundColor: '#2a2a2a',
          borderColor: '#434343',
          textStyle: { color: '#fff' },
          formatter: (params: any) => {
            let html = `<div style="margin-bottom:4px;color:#aaa">${params[0].axisValue}</div>`
            params.forEach((p: any) => {
              const val = p.value != null ? `${Number(p.value).toFixed(1)} 元/MWh` : '暂无数据'
              html += `<div>${p.marker}${p.seriesName}: <b>${val}</b></div>`
            })
            return html
          },
        },
        legend: { data: ['预测电价', ...(hasActual ? ['实时节点均价'] : [])], textStyle: { color: '#999' }, top: 4 },
        grid: { left: '3%', right: '4%', bottom: '8%', top: 36, containLabel: true },
        xAxis: { type: 'category', data: HOURS, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999', interval: 5 } },
        yAxis: { type: 'value', name: '元/MWh', nameTextStyle: { color: '#999' }, axisLine: { lineStyle: { color: '#434343' } }, axisLabel: { color: '#999' }, splitLine: { lineStyle: { color: '#303030' } } },
        series: [
          {
            name: '预测电价',
            type: 'line',
            data: day.predicted,
            smooth: true,
            showSymbol: false,
            lineStyle: { color: C.predicted, width: 2, type: 'dashed' },
            itemStyle: { color: C.predicted },
            areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: C.predicted + '30' }, { offset: 1, color: C.predicted + '05' }] } },
          },
          ...(hasActual ? [{
            name: '实时节点均价',
            type: 'line',
            data: day.actual,
            smooth: true,
            showSymbol: false,
            lineStyle: { color: C.actual, width: 2 },
            itemStyle: { color: C.actual },
            connectNulls: false,
          }] : []),
        ],
      })
    })
  }, [predHourly])

  const demandData = demandSolar.map(d => d.demand)
  const solarData = demandSolar.map(d => d.solar_forecast)
  const demandStats = calcStats(demandData)
  const solarPeak = calcStats(solarData).max

  return (
    <div style={{ padding: 16 }}>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <span style={{ color: '#999', marginRight: 8 }}>选择日期:</span>
            <SingleDatePicker value={selectedDate} onChange={(date) => date && setSelectedDate(date)} format="YYYY-MM-DD" />
          </Col>
          <Col><Tag color="blue">数据日期: {selectedDate.format('YYYY-MM-DD')}</Tag></Col>
          <Col flex="auto"><Badge status="success" text={<span style={{ color: '#52c41a' }}>数据已更新</span>} /></Col>
        </Row>
      </Card>

      {error && <Alert type="error" message="数据加载失败" description={error} style={{ marginBottom: 16 }} />}

      <Spin spinning={loading}>
        {/* 行1：日前节点电价 + 日前用电侧负荷 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title={<span><LineChartOutlined style={{ color: C.dayAheadNode }} /> 日前节点电价</span>} extra={<Tag color="red">96点</Tag>}>
              {dayAheadNode.length > 0 ? (
                <>
                  <div ref={chart1Ref} style={{ height: 200 }} />
                  <Row style={{ marginTop: 8 }}>
                    {(['均值', '最高', '最低'] as const).map((label, i) => {
                      const key = (['avg', 'max', 'min'] as const)[i]
                      return <Col key={label} span={8}><Statistic title={label} value={calcStats(transform96to24(dayAheadNode))[key]} suffix="元" /></Col>
                    })}
                  </Row>
                </>
              ) : <Empty description="暂无数据" />}
            </Card>
          </Col>
          <Col span={12}>
            <Card title={<span><ThunderboltOutlined style={{ color: C.dayAheadDemand }} /> 日前用电侧负荷</span>} extra={<Tag color="blue">分时</Tag>}>
              {dayAheadDemand.length > 0 ? (
                <>
                  <div ref={chart2Ref} style={{ height: 200 }} />
                  <Row style={{ marginTop: 8 }}>
                    {(['均值', '最高', '最低'] as const).map((label, i) => {
                      const key = (['avg', 'max', 'min'] as const)[i]
                      return <Col key={label} span={8}><Statistic title={label} value={calcStats(transform48to24(dayAheadDemand))[key]} suffix="MW" /></Col>
                    })}
                  </Row>
                </>
              ) : <Empty description="暂无数据" />}
            </Card>
          </Col>
        </Row>

        {/* 行2：实时节点电价 + 实时用电侧负荷（叠加光伏预测） */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card title={<span><ClockCircleOutlined style={{ color: C.realtimeNode }} /> 实时节点电价</span>} extra={<Tag color="green">96点</Tag>}>
              {realtimeNode.length > 0 ? (
                <>
                  <div ref={chart3Ref} style={{ height: 200 }} />
                  <Row style={{ marginTop: 8 }}>
                    {(['均值', '最高', '最低'] as const).map((label, i) => {
                      const key = (['avg', 'max', 'min'] as const)[i]
                      return <Col key={label} span={8}><Statistic title={label} value={calcStats(transform96to24(realtimeNode))[key]} suffix="元" /></Col>
                    })}
                  </Row>
                </>
              ) : <Empty description="暂无实时数据" />}
            </Card>
          </Col>
          <Col span={12}>
            <Card
              title={<span><ThunderboltOutlined style={{ color: C.realtimeDemand }} /> 实时用电侧负荷</span>}
              extra={
                <span>
                  <Tag color="purple">负荷</Tag>
                  <Tag color="gold">光伏预测</Tag>
                </span>
              }
            >
              {demandSolar.length > 0 ? (
                <>
                  <div ref={chart4Ref} style={{ height: 200 }} />
                  <Row style={{ marginTop: 8 }}>
                    <Col span={8}><Statistic title="负荷均值" value={demandStats.avg} suffix="MW" valueStyle={{ color: C.realtimeDemand }} /></Col>
                    <Col span={8}><Statistic title="负荷峰值" value={demandStats.max} suffix="MW" valueStyle={{ color: C.realtimeDemand }} /></Col>
                    <Col span={8}><Statistic title="光伏预测峰值" value={solarPeak} suffix="MW" valueStyle={{ color: C.solar }} /></Col>
                  </Row>
                </>
              ) : <Empty description="暂无数据" />}
            </Card>
          </Col>
        </Row>

        {/* 行3：3天预测 vs 实时节点均价对比 */}
        <Card
          title={<span><RiseOutlined style={{ color: C.predicted }} /> 模型预测未来3天逐小时电价对比</span>}
          extra={<span><Tag color="gold">预测电价</Tag><Tag color="cyan">实时节点均价</Tag></span>}
        >
          {predHourly.length > 0 ? (
            <Row gutter={[16, 0]}>
              {predHourly.map((day, idx) => {
                const hasActual = day.actual.some(v => v !== null)
                const predStats = calcStats(day.predicted)
                return (
                  <Col key={idx} span={8} style={{ borderRight: idx < 2 ? '1px solid #303030' : undefined, paddingRight: idx < 2 ? 16 : 0, paddingLeft: idx > 0 ? 16 : 0 }}>
                    <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#fff', fontWeight: 600, fontSize: 14 }}>{day.date}</span>
                      {hasActual
                        ? <Badge status="success" text={<span style={{ color: C.actual, fontSize: 12 }}>有实时数据</span>} />
                        : <Badge status="warning" text={<span style={{ color: C.predicted, fontSize: 12 }}>待验证</span>} />}
                    </div>
                    <div ref={predChartRefs[idx]} style={{ height: 220 }} />
                    <Row gutter={8} style={{ marginTop: 8 }}>
                      <Col span={8}><Statistic title={<span style={{ fontSize: 11, color: '#999' }}>预测均值</span>} value={predStats.avg} suffix={<span style={{ fontSize: 11 }}>元</span>} valueStyle={{ color: C.predicted, fontSize: 16 }} /></Col>
                      <Col span={8}><Statistic title={<span style={{ fontSize: 11, color: '#999' }}>预测峰值</span>} value={predStats.max} suffix={<span style={{ fontSize: 11 }}>元</span>} valueStyle={{ color: '#f5222d', fontSize: 16 }} /></Col>
                      <Col span={8}><Statistic title={<span style={{ fontSize: 11, color: '#999' }}>预测谷值</span>} value={predStats.min} suffix={<span style={{ fontSize: 11 }}>元</span>} valueStyle={{ color: '#52c41a', fontSize: 16 }} /></Col>
                    </Row>
                  </Col>
                )
              })}
            </Row>
          ) : <Empty description="暂无预测数据" />}
        </Card>
      </Spin>
    </div>
  )
}
