import { useState, useEffect } from 'react'
import { Card, Row, Col, List, Tag, Statistic, Spin, Empty, Alert } from 'antd'
import {
  CloudOutlined,
  WarningOutlined,
  LineChartOutlined,
  CalendarOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  UserOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { priceService } from '../src/services'

// 快捷操作配置
const quickActions = [
  { icon: <WarningOutlined />, title: '气象预警', color: '#ff4d4f', path: '/weather/alert' },
  { icon: <CloudOutlined />, title: '天气预报', color: '#1E88E5', path: '/weather/predict' },
  { icon: <LineChartOutlined />, title: '天气数值预测', color: '#52c41a', path: '/weather/nwp' },
  { icon: <CalendarOutlined />, title: '天气逐日预测', color: '#faad14', path: '/weather/daily-predict' },
  { icon: <ThunderboltOutlined />, title: '现货预测总览', color: '#722ed1', path: '/data-show' },
  { icon: <DatabaseOutlined />, title: '省级负荷预测', color: '#eb2f96', path: '/loadpower' },
  { icon: <DollarOutlined />, title: '省级电价预测', color: '#f5222d', path: '/loadprice' },
  { icon: <BarChartOutlined />, title: '现货数据统计', color: '#1890ff', path: '/spot-data' },
  { icon: <UserOutlined />, title: '个人中心', color: '#722ed1', path: '/user' },
]

// 天气数据
const weatherData = [
  { day: '今天', date: '03/12', high: 14, low: 2, weather: '晴' },
  { day: '明天', date: '03/13', high: 16, low: 4, weather: '多云' },
  { day: '周五', date: '03/14', high: 18, low: 6, weather: '晴' },
  { day: '周六', date: '03/15', high: 20, low: 8, weather: '晴' },
  { day: '周日', date: '03/16', high: 19, low: 7, weather: '多云' },
  { day: '周一', date: '03/17', high: 17, low: 5, weather: '阴' },
  { day: '周二', date: '03/18', high: 15, low: 3, weather: '小雨' },
]

// 预警数据
const alerts = [
  { time: '2026-03-12 08:30', content: '南京市发布大风蓝色预警', level: 'blue' },
  { time: '2026-03-11 16:45', content: '苏州市发布寒潮黄色预警', level: 'yellow' },
  { time: '2026-03-11 10:20', content: '无锡市发布霜冻蓝色预警', level: 'blue' },
  { time: '2026-03-10 14:15', content: '徐州市发布大雾橙色预警', level: 'orange' },
  { time: '2026-03-10 09:00', content: '常州市发布道路结冰黄色预警', level: 'yellow' },
]

const getAlertColor = (level: string) => {
  const colors: Record<string, string> = {
    blue: 'blue',
    yellow: 'gold',
    orange: 'orange',
    red: 'red',
  }
  return colors[level] || 'default'
}

export default function Home() {
  const navigate = useNavigate()
  
  // 数据状态
  const [dashboardData, setDashboardData] = useState<any>(null)
  const [dataSummary, setDataSummary] = useState<any>(null)
  const [tradingAdvice, setTradingAdvice] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 获取数据
  const fetchData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [dashboard, summary, advice] = await Promise.all([
        priceService.getDashboardData(),
        priceService.getDataSummary(),
        priceService.getTradingAdvice(),
      ])
      setDashboardData(dashboard)
      setDataSummary(summary)
      setTradingAdvice(advice)
    } catch (err: any) {
      setError(err.message || '获取数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // 跳转到页面
  const handleNavigate = (path: string) => {
    navigate(path)
  }

  return (
    <div>
      {error && (
        <Alert
          type="error"
          message="数据加载失败"
          description={error}
          closable
          action={<a onClick={fetchData}>重试</a>}
          style={{ marginBottom: 16 }}
        />
      )}
      
      <Row gutter={[16, 16]}>
        <Col span={4}>
          <Card title="功能导航" style={{ height: '100%' }}>
            <div style={{ color: '#999', textAlign: 'center', padding: '20px 0' }}>
              菜单导航区域
            </div>
          </Card>
        </Col>

        <Col span={14}>
          <Card 
            title="电价概览" 
            style={{ marginBottom: 16 }}
            extra={<ReloadOutlined onClick={fetchData} style={{ cursor: 'pointer' }} />}
          >
            <Spin spinning={loading}>
              <Row gutter={16}>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="最新电价"
                      value={dashboardData?.latest_price || '--'}
                      suffix="元/MWh"
                      prefix={<DollarOutlined />}
                      valueStyle={{ color: '#f5222d', fontSize: 24 }}
                    />
                    <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>
                      更新: {dashboardData?.latest_date || '--'}
                    </div>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="监测节点数"
                      value={dashboardData?.node_count || 0}
                      prefix={<ThunderboltOutlined />}
                      valueStyle={{ color: '#1E88E5', fontSize: 24 }}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="电价记录数"
                      value={dataSummary?.price?.records || 0}
                      valueStyle={{ color: '#52c41a', fontSize: 24 }}
                    />
                  </Card>
                </Col>
                <Col span={6}>
                  <Card>
                    <Statistic
                      title="负荷记录数"
                      value={dataSummary?.load?.records || 0}
                      valueStyle={{ color: '#faad14', fontSize: 24 }}
                    />
                  </Card>
                </Col>
              </Row>
              
              {dashboardData?.date_range && (
                <div style={{ marginTop: 16, padding: '12px 16px', background: '#2a2a2a', borderRadius: 8 }}>
                  <Row gutter={24}>
                    <Col>
                      <span style={{ color: '#999' }}>数据范围: </span>
                      <span style={{ color: '#fff' }}>
                        {dashboardData.date_range.start || '--'} ~ {dashboardData.date_range.end || '--'}
                      </span>
                    </Col>
                    <Col>
                      <span style={{ color: '#999' }}>数据天数: </span>
                      <span style={{ color: '#fff' }}>
                        {dataSummary?.price?.days || '--'} 天
                      </span>
                    </Col>
                  </Row>
                </div>
              )}
            </Spin>
          </Card>

          <Card title="交易建议" style={{ marginBottom: 16 }}>
            <Spin spinning={loading}>
              {tradingAdvice ? (
                <div>
                  <Row gutter={16}>
                    <Col span={8}>
                      <div style={{ textAlign: 'center', padding: 16, background: '#2a2a2a', borderRadius: 8 }}>
                        <div style={{ fontSize: 14, color: '#999', marginBottom: 8 }}>建议</div>
                        <div style={{ fontSize: 20, fontWeight: 'bold', color: '#1E88E5' }}>
                          {tradingAdvice.recommendation || '暂无建议'}
                        </div>
                      </div>
                    </Col>
                    <Col span={8}>
                      <div style={{ textAlign: 'center', padding: 16, background: '#2a2a2a', borderRadius: 8 }}>
                        <div style={{ fontSize: 14, color: '#999', marginBottom: 8 }}>风险等级</div>
                        <div style={{ fontSize: 20, fontWeight: 'bold', color: '#faad14' }}>
                          {tradingAdvice.risk_level || '--'}
                        </div>
                      </div>
                    </Col>
                    <Col span={8}>
                      <div style={{ textAlign: 'center', padding: 16, background: '#2a2a2a', borderRadius: 8 }}>
                        <div style={{ fontSize: 14, color: '#999', marginBottom: 8 }}>预期收益</div>
                        <div style={{ fontSize: 20, fontWeight: 'bold', color: '#52c41a' }}>
                          {tradingAdvice.expected_return || '--'}
                        </div>
                      </div>
                    </Col>
                  </Row>
                  {tradingAdvice.reason && (
                    <div style={{ marginTop: 16, padding: '12px 16px', background: '#1f1f1f', borderRadius: 8, borderLeft: '3px solid #1E88E5' }}>
                      <div style={{ color: '#999', fontSize: 12, marginBottom: 4 }}>建议理由</div>
                      <div style={{ color: '#fff' }}>{tradingAdvice.reason}</div>
                    </div>
                  )}
                  {tradingAdvice.suggested_actions?.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ color: '#999', fontSize: 12, marginBottom: 8 }}>建议操作</div>
                      <List
                        size="small"
                        dataSource={tradingAdvice.suggested_actions}
                        renderItem={(item: string) => (
                          <List.Item style={{ padding: '4px 0', color: '#fff' }}>
                            • {item}
                          </List.Item>
                        )}
                      />
                    </div>
                  )}
                </div>
              ) : (
                <Empty description="暂无交易建议" />
              )}
            </Spin>
          </Card>

          <Card title="近期天气" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 48, marginRight: 16 }}>🌤️</div>
              <div>
                <div style={{ fontSize: 24, fontWeight: 'bold' }}>江苏</div>
                <div style={{ fontSize: 32, fontWeight: 'bold' }}>15°C</div>
                <div style={{ color: '#999' }}>多云</div>
              </div>
            </div>
            <Row gutter={8}>
              {weatherData.map((item, index) => (
                <Col span={3} key={index}>
                  <div
                    style={{
                      textAlign: 'center',
                      padding: '12px 8px',
                      background: index === 0 ? '#1E88E5' : 'transparent',
                      borderRadius: 8,
                    }}
                  >
                    <div style={{ fontSize: 12, color: '#999' }}>{item.day}</div>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 8 }}>{item.date}</div>
                    <div style={{ fontSize: 20, marginBottom: 8 }}>
                      {item.weather === '晴' ? '☀️' : item.weather === '多云' ? '⛅' : item.weather === '阴' ? '☁️' : '🌧️'}
                    </div>
                    <div style={{ fontSize: 12 }}>
                      <span style={{ color: '#ff4d4f' }}>{item.high}°</span>
                      <span style={{ color: '#666', margin: '0 4px' }}>/</span>
                      <span style={{ color: '#52c41a' }}>{item.low}°</span>
                    </div>
                  </div>
                </Col>
              ))}
            </Row>
          </Card>

          <Card title="快捷操作">
            <Row gutter={[16, 16]}>
              {quickActions.map((item, index) => (
                <Col span={8} key={index}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: 16,
                      background: '#2a2a2a',
                      borderRadius: 8,
                      cursor: 'pointer',
                      transition: 'all 0.3s',
                    }}
                    onClick={() => handleNavigate(item.path)}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = '#333'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = '#2a2a2a'
                    }}
                  >
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: 8,
                        background: `${item.color}20`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginRight: 12,
                        color: item.color,
                        fontSize: 20,
                      }}
                    >
                      {item.icon}
                    </div>
                    <span style={{ color: '#fff', fontSize: 14 }}>{item.title}</span>
                  </div>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>

        <Col span={6}>
          <Card title="气象预警" style={{ height: '100%' }}>
            <List
              dataSource={alerts}
              renderItem={(item) => (
                <List.Item style={{ padding: '12px 0', borderBottom: '1px solid #303030' }}>
                  <div>
                    <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>{item.time}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Tag color={getAlertColor(item.level)}>{item.level.toUpperCase()}</Tag>
                      <span style={{ color: '#fff' }}>{item.content}</span>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
