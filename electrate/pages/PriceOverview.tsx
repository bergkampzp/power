/**
 * 电价总览页面
 * 整合展示：24小时分时电价、日前节点电价、预测电价
 */
import { useState, useEffect } from 'react'
import { Card, Row, Col, DatePicker, Statistic, Spin, Alert, Empty, Button, Tag } from 'antd'
import { ReloadOutlined, LineChartOutlined, DollarOutlined, ThunderboltOutlined, RiseOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { priceService } from '../src/services'

const { RangePicker } = DatePicker

export default function PriceOverview() {
  // 日期范围
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2026-02-01'),
    dayjs('2026-03-10')
  ])
  
  // 数据状态
  const [dailyPrices, setDailyPrices] = useState<any[]>([])
  const [hourlyPrices, setHourlyPrices] = useState<any[]>([])
  const [prediction, setPrediction] = useState<any>(null)
  const [dashboard, setDashboard] = useState<any>(null)
  
  // 加载状态
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 获取数据
  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [daily, pred, dash] = await Promise.all([
        priceService.getDailyPrice({
          start_date: dateRange[0].format('YYYY-MM-DD'),
          end_date: dateRange[1].format('YYYY-MM-DD')
        }),
        priceService.predictPrice({
          date: dayjs().add(1, 'day').format('YYYY-MM-DD')
        }),
        priceService.getDashboardData(),
      ])
      setDailyPrices(daily || [])
      setPrediction(pred)
      setDashboard(dash)
      
      // 获取分时数据（最新一天）
      const hourly = await priceService.getHourlyPrice(dateRange[1].format('YYYY-MM-DD'))
      setHourlyPrices(hourly || [])
    } catch (err: any) {
      setError(err.message || '获取数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [dateRange])

  // 日均价趋势图配置
  const dailyTrendOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['日均价'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dailyPrices.map(d => d.date),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999', rotate: 45 }
    },
    yAxis: {
      type: 'value',
      name: '电价(元/MWh)',
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [{
      name: '日均价',
      type: 'line',
      data: dailyPrices.map(d => d.price),
      smooth: true,
      itemStyle: { color: '#f5222d' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(245, 34, 45, 0.3)' },
            { offset: 1, color: 'rgba(245, 34, 45, 0.05)' }
          ]
        }
      },
      markLine: {
        silent: true,
        lineStyle: { color: '#52c41a', type: 'dashed' },
        data: [{
          type: 'average',
          name: '平均'
        }]
      }
    }]
  }

  // 24小时分时电价图配置
  const hourlyChartOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: ['实时电价', '均价'],
      textStyle: { color: '#999' },
      top: 10
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: hourlyPrices.map(h => `${h.hour}:00`),
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '电价(元/MWh)',
      min: 0,
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [
      {
        name: '实时电价',
        type: 'line',
        data: hourlyPrices.map(h => h.avg),
        smooth: true,
        itemStyle: { color: '#1890ff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(24, 144, 255, 0.3)' },
              { offset: 1, color: 'rgba(24, 144, 255, 0.05)' }
            ]
          }
        }
      },
      {
        name: '均价',
        type: 'line',
        data: hourlyPrices.map(h => h.avg),
        smooth: true,
        lineStyle: { type: 'dashed', color: '#52c41a' },
        itemStyle: { color: '#52c41a' }
      }
    ]
  }

  // 预测电价柱状图
  const predictionBarOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#2a2a2a',
      borderColor: '#434343',
      textStyle: { color: '#fff' },
      formatter: (params: any) => {
        const data = params[0]
        return `${data.name}<br/>预测电价: <span style="color:#f5222d">${data.value} 元/MWh</span>`
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: prediction ? [prediction.date] : [],
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' }
    },
    yAxis: {
      type: 'value',
      name: '预测电价(元/MWh)',
      axisLine: { lineStyle: { color: '#434343' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#303030' } }
    },
    series: [{
      name: '预测电价',
      type: 'bar',
      data: prediction ? [prediction.price] : [],
      itemStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: '#f5222d' },
            { offset: 1, color: '#ff7875' }
          ]
        },
        borderRadius: [8, 8, 0, 0]
      },
      barWidth: '50%'
    }]
  }

  return (
    <div>
      {error && (
        <Alert
          type="error"
          message="数据加载失败"
          description={error}
          closable
          action={<Button size="small" onClick={fetchData}>重试</Button>}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 顶部统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="最新日均价"
              value={dashboard?.latest_price || '--'}
              suffix="元/MWh"
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#f5222d' }}
            />
            <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
              {dashboard?.latest_date || '--'}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="监测节点数"
              value={dashboard?.node_count || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="预测电价"
              value={prediction?.price || '--'}
              suffix="元/MWh"
              prefix={<RiseOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
            <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
              置信度: {prediction?.confidence ? `${(prediction.confidence * 100).toFixed(0)}%` : '--'}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="电价区间"
              value={prediction?.range ? `${prediction.range[0]}~${prediction.range[1]}` : '--'}
              suffix="元/MWh"
              valueStyle={{ color: '#faad14', fontSize: 18 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 工具栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col>
            <span style={{ color: '#999', marginRight: 8 }}>日期范围:</span>
            <RangePicker
              value={dateRange}
              onChange={(dates) => dates && setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs])}
              format="YYYY-MM-DD"
            />
          </Col>
          <Col>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={fetchData}
              loading={loading}
            >
              刷新数据
            </Button>
          </Col>
          <Col flex="auto">
            <Tag color="blue">
              数据范围: {dateRange[0].format('MM-DD')} ~ {dateRange[1].format('MM-DD')}
            </Tag>
          </Col>
          <Col>
            <span style={{ color: '#52c41a' }}>● 数据已更新</span>
          </Col>
        </Row>
      </Card>

      {/* 主内容区 */}
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          {/* 左上：日前节点电价趋势 */}
          <Col span={16}>
            <Card 
              title={
                <span>
                  <LineChartOutlined style={{ marginRight: 8 }} />
                  日前节点电价趋势
                </span>
              }
              extra={<Tag color="red">日均价</Tag>}
            >
              {dailyPrices.length > 0 ? (
                <ReactECharts option={dailyTrendOption} style={{ height: 350 }} />
              ) : (
                <Empty description="暂无数据" />
              )}
            </Card>
          </Col>

          {/* 右上：预测电价 */}
          <Col span={8}>
            <Card 
              title={
                <span>
                  <RiseOutlined style={{ marginRight: 8 }} />
                  电价预测
                </span>
              }
              extra={<Tag color="green">次日预测</Tag>}
            >
              {prediction ? (
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  <div style={{ fontSize: 48, fontWeight: 'bold', color: '#f5222d' }}>
                    {prediction.price}
                  </div>
                  <div style={{ fontSize: 16, color: '#999', marginBottom: 16 }}>
                    元/MWh
                  </div>
                  <Row gutter={16}>
                    <Col span={12}>
                      <div style={{ background: '#2a2a2a', padding: 12, borderRadius: 8 }}>
                        <div style={{ fontSize: 12, color: '#999' }}>置信区间</div>
                        <div style={{ fontSize: 16, color: '#fff' }}>
                          {prediction.range?.[0]} ~ {prediction.range?.[1]}
                        </div>
                      </div>
                    </Col>
                    <Col span={12}>
                      <div style={{ background: '#2a2a2a', padding: 12, borderRadius: 8 }}>
                        <div style={{ fontSize: 12, color: '#999' }}>置信度</div>
                        <div style={{ fontSize: 16, color: '#52c41a' }}>
                          {(prediction.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                    </Col>
                  </Row>
                  {prediction.reason && (
                    <div style={{ marginTop: 16, padding: 12, background: '#1f1f1f', borderRadius: 8, textAlign: 'left' }}>
                      <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>预测依据</div>
                      <div style={{ fontSize: 14, color: '#fff' }}>{prediction.reason}</div>
                    </div>
                  )}
                  <ReactECharts option={predictionBarOption} style={{ height: 150 }} />
                </div>
              ) : (
                <Empty description="暂无预测数据" />
              )}
            </Card>
          </Col>

          {/* 下方：24小时分时电价 */}
          <Col span={24}>
            <Card 
              title={
                <span>
                  <ThunderboltOutlined style={{ marginRight: 8 }} />
                  24小时分时电价
                </span>
              }
              extra={
                <span style={{ color: '#999' }}>
                  {dateRange[1].format('YYYY-MM-DD')} 实时数据
                </span>
              }
            >
              {hourlyPrices.length > 0 ? (
                <ReactECharts option={hourlyChartOption} style={{ height: 300 }} />
              ) : (
                <Empty description="暂无分时数据" />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
