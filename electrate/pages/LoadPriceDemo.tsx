/**
 * 电价分析页面 - 数据接入示例
 * 展示如何使用 API 服务获取真实数据
 */
import { useState, useMemo } from 'react'
import { Card, Row, Col, Spin, Empty, Alert, Statistic } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { SingleDatePicker } from '../src/components/DatePicker'
import { useHourlyPrice } from '../src/hooks/usePriceData'

export default function LoadPriceDemo() {
  // 选择日期
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  
  // 使用 Hook 获取数据
  const { data: hourlyData, loading, error, refetch } = useHourlyPrice(selectedDate)
  
  // 转换图表数据
  const chartData = useMemo(() => {
    if (!hourlyData || hourlyData.length === 0) return null
    
    return {
      hours: hourlyData.map(d => `${d.hour}:00`),
      avg: hourlyData.map(d => d.avg),
      min: hourlyData.map(d => d.min),
      max: hourlyData.map(d => d.max),
    }
  }, [hourlyData])
  
  // 计算统计数据
  const stats = useMemo(() => {
    if (!hourlyData || hourlyData.length === 0) return null
    
    const prices = hourlyData.map(d => d.avg).filter(Boolean)
    const maxPrice = Math.max(...prices)
    const minPrice = Math.min(...prices)
    const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length
    
    return { maxPrice, minPrice, avgPrice }
  }, [hourlyData])
  
  // 图表配置
  const chartOption = useMemo(() => {
    if (!chartData) return {}
    
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#2a2a2a',
        borderColor: '#434343',
        textStyle: { color: '#fff' }
      },
      legend: {
        data: ['平均价格', '最高价格', '最低价格'],
        textStyle: { color: '#999' }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: chartData.hours,
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' }
      },
      yAxis: {
        type: 'value',
        name: '电价 (元/MWh)',
        axisLine: { lineStyle: { color: '#434343' } },
        axisLabel: { color: '#999' },
        splitLine: { lineStyle: { color: '#303030' } }
      },
      series: [
        {
          name: '平均价格',
          type: 'line',
          data: chartData.avg,
          smooth: true,
          itemStyle: { color: '#1E88E5' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(30, 136, 229, 0.3)' },
                { offset: 1, color: 'rgba(30, 136, 229, 0.05)' }
              ]
            }
          }
        },
        {
          name: '最高价格',
          type: 'line',
          data: chartData.max,
          smooth: true,
          lineStyle: { type: 'dashed' },
          itemStyle: { color: '#f5222d' }
        },
        {
          name: '最低价格',
          type: 'line',
          data: chartData.min,
          smooth: true,
          lineStyle: { type: 'dashed' },
          itemStyle: { color: '#52c41a' }
        }
      ]
    }
  }, [chartData])
  
  return (
    <div style={{ padding: 16 }}>
      {/* 页面标题和日期选择 */}
      <Card style={{ marginBottom: 16 }}>
        <Row align="middle" gutter={16}>
          <Col>
            <h2 style={{ margin: 0, color: '#fff' }}>电价分析</h2>
          </Col>
          <Col flex="auto" />
          <Col>
            <SingleDatePicker 
              value={selectedDate} 
              onChange={setSelectedDate} 
            />
          </Col>
        </Row>
      </Card>
      
      {/* 错误提示 */}
      {error && (
        <Alert
          type="error"
          message="数据加载失败"
          description={error}
          closable
          style={{ marginBottom: 16 }}
        />
      )}
      
      {/* 统计卡片 */}
      {stats && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={8}>
            <Card>
              <Statistic
                title="最高电价"
                value={stats.maxPrice}
                suffix="元/MWh"
                valueStyle={{ color: '#f5222d' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card>
              <Statistic
                title="平均电价"
                value={stats.avgPrice.toFixed(2)}
                suffix="元/MWh"
                valueStyle={{ color: '#1E88E5' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={8}>
            <Card>
              <Statistic
                title="最低电价"
                value={stats.minPrice}
                suffix="元/MWh"
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
        </Row>
      )}
      
      {/* 图表区域 */}
      <Card>
        <Spin spinning={loading}>
          {chartData ? (
            <ReactECharts
              option={chartOption}
              style={{ height: 400 }}
              notMerge
              lazyUpdate
            />
          ) : (
            <Empty description={loading ? '加载中...' : '暂无数据'} />
          )}
        </Spin>
      </Card>
      
      {/* 数据说明 */}
      <Card style={{ marginTop: 16 }}>
        <p style={{ color: '#999', margin: 0 }}>
          数据来源：日前节点电价 | 更新时间：{dayjs().format('YYYY-MM-DD HH:mm:ss')}
        </p>
      </Card>
    </div>
  )
}
