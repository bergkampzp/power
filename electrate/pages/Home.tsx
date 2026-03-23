import { Card, Row, Col, List, Tag } from 'antd'
import {
  CloudOutlined,
  WarningOutlined,
  LineChartOutlined,
  CalendarOutlined,
  ThunderboltOutlined,
  WindowsOutlined,
  SunOutlined,
  DollarOutlined,
  DatabaseOutlined,
  BarChartOutlined,
  UserOutlined,
} from '@ant-design/icons'

const quickActions = [
  { icon: <WarningOutlined />, title: '气象预警', color: '#ff4d4f' },
  { icon: <CloudOutlined />, title: '天气预报', color: '#1E88E5' },
  { icon: <LineChartOutlined />, title: '天气数值预测', color: '#52c41a' },
  { icon: <CalendarOutlined />, title: '天气逐日预测', color: '#faad14' },
  { icon: <ThunderboltOutlined />, title: '现货预测总览', color: '#722ed1' },
  { icon: <WindowsOutlined />, title: '省级风电预测', color: '#13c2c2' },
  { icon: <SunOutlined />, title: '省级光伏预测', color: '#fa8c16' },
  { icon: <DatabaseOutlined />, title: '省级负荷预测', color: '#eb2f96' },
  { icon: <DollarOutlined />, title: '省级电价预测', color: '#f5222d' },
  { icon: <BarChartOutlined />, title: '现货数据统计', color: '#1890ff' },
  { icon: <LineChartOutlined />, title: '现货数据逐小时分析', color: '#52c41a' },
  { icon: <CalendarOutlined />, title: '现货数据逐日分析', color: '#faad14' },
  { icon: <UserOutlined />, title: '个人中心', color: '#722ed1' },
]

const weatherData = [
  { day: '今天', date: '03/12', high: 14, low: 2, weather: '晴' },
  { day: '明天', date: '03/13', high: 16, low: 4, weather: '多云' },
  { day: '周五', date: '03/14', high: 18, low: 6, weather: '晴' },
  { day: '周六', date: '03/15', high: 20, low: 8, weather: '晴' },
  { day: '周日', date: '03/16', high: 19, low: 7, weather: '多云' },
  { day: '周一', date: '03/17', high: 17, low: 5, weather: '阴' },
  { day: '周二', date: '03/18', high: 15, low: 3, weather: '小雨' },
]

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
  return (
    <div>
      <Row gutter={[16, 16]}>
        {/* 左侧菜单树占位 */}
        <Col span={4}>
          <Card title="功能导航" style={{ height: '100%' }}>
            <div style={{ color: '#999', textAlign: 'center', padding: '20px 0' }}>
              菜单导航区域
            </div>
          </Card>
        </Col>

        {/* 中间内容 */}
        <Col span={14}>
          {/* 天气卡片 */}
          <Card title="近期天气" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontSize: 48, marginRight: 16 }}>🌤️</div>
              <div>
                <div style={{ fontSize: 24, fontWeight: 'bold' }}>北京</div>
                <div style={{ fontSize: 32, fontWeight: 'bold' }}>8°C</div>
                <div style={{ color: '#999' }}>晴</div>
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

          {/* 快捷操作 */}
          <Card title="快捷操作">
            <Row gutter={[16, 16]}>
              {quickActions.map((item, index) => (
                <Col span={6} key={index}>
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

        {/* 右侧气象预警 */}
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
