import { useState } from 'react'
import { Layout as AntLayout, Menu, Avatar, Dropdown, Tabs, Button } from 'antd'
import {
  HomeOutlined,
  CloudOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  UserOutlined,
  SettingOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  DownOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DatabaseOutlined,
  ShopOutlined,
  SunOutlined,
  PieChartOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Header, Sider, Content } = AntLayout

const menuItems = [
  {
    key: '/',
    icon: <HomeOutlined />,
    label: '首页',
  },
  {
    key: 'weather',
    icon: <CloudOutlined />,
    label: '气象预测',
    children: [
      { key: '/weather/alert', label: '气象预警' },
      { key: '/weather/predict', label: '天气预报' },
      { key: '/weather/nwp', label: '数值预测' },
      { key: '/weather/daily-predict', label: '逐日预测' },
    ],
  },
  {
    key: 'spot',
    icon: <ThunderboltOutlined />,
    label: '现货预测',
    children: [
      { key: '/data-show', label: '现货预测总览' },
      { key: '/windpower', label: '省级风电预测' },
      { key: '/solarpower', label: '省级光伏预测' },
      { key: '/loadpower', label: '省级负荷预测' },
      { key: '/loadprice', label: '省级电价预测' },
    ],
  },
  {
    key: 'data',
    icon: <DatabaseOutlined />,
    label: '现货数据',
    children: [
      { key: '/spot-data', label: '现货历史数据' },
    ],
  },
  {
    key: 'sales',
    icon: <ShopOutlined />,
    label: '售电业务',
  },
  {
    key: 'generation',
    icon: <ThunderboltOutlined />,
    label: '发电管理',
  },
  {
    key: 'users',
    icon: <UserOutlined />,
    label: '电力用户',
  },
  {
    key: 'decision',
    icon: <PieChartOutlined />,
    label: '售电决策',
    children: [
      { key: '/sales-decision', label: '售电辅助决策' },
      { key: '/scroll-decision', label: '滚撮辅助决策' },
    ],
  },
  {
    key: 'storage',
    icon: <ThunderboltOutlined />,
    label: '储能管理',
  },
  {
    key: 'solar',
    icon: <SunOutlined />,
    label: '光伏管理',
  },
  {
    key: 'analysis',
    icon: <BarChartOutlined />,
    label: '管理与分析',
  },
  {
    key: '/user',
    icon: <SettingOutlined />,
    label: '个人中心',
  },
]

const topNavItems = [
  { key: '/', label: '首页' },
  { key: '/weather/predict', label: '气象预测' },
  { key: '/weather/alert', label: '气象预警' },
  { key: '/weather/nwp', label: '数值预测' },
  { key: '/weather/daily-predict', label: '逐日预测' },
  { key: '/windpower', label: '场站预测' },
  { key: '/data-show', label: '现货预测总览' },
  { key: '/loadprice', label: '省级电价预测' },
]

const userMenuItems = [
  { key: 'profile', label: '个人资料' },
  { key: 'settings', label: '系统设置' },
  { key: 'logout', label: '退出登录' },
]

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={200}
        style={{
          background: '#1f1f1f',
          borderRight: '1px solid #303030',
        }}
      >
        <div style={{ padding: '16px', textAlign: 'center' }}>
          <div
            style={{
              width: 40,
              height: 40,
              background: 'linear-gradient(135deg, #1E88E5 0%, #42A5F5 100%)',
              borderRadius: 8,
              margin: '0 auto',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ThunderboltOutlined style={{ fontSize: 24, color: '#fff' }} />
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={handleMenuClick}
          style={{
            background: '#1f1f1f',
            borderRight: 'none',
          }}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: '#1f1f1f',
            borderBottom: '1px solid #303030',
            display: 'flex',
            alignItems: 'center',
            padding: '0 16px',
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            style={{ color: '#fff', marginRight: 16 }}
          />
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <Tabs
              activeKey={location.pathname}
              items={topNavItems}
              onChange={(key) => navigate(key)}
              style={{ color: '#fff' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Button
              type="text"
              icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
              style={{ color: '#999' }}
            />
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} style={{ background: '#1E88E5' }} />
                <span style={{ color: '#fff' }}>江苏测试</span>
                <DownOutlined style={{ color: '#999', fontSize: 12 }} />
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ padding: 16, background: '#141414' }}>
          <Outlet />
        </Content>
        <div
          style={{
            textAlign: 'right',
            padding: '8px 16px',
            background: '#1f1f1f',
            borderTop: '1px solid #303030',
            color: '#666',
            fontSize: 12,
          }}
        >
          Build: 2026-03-06 20:16:22
        </div>
      </AntLayout>
    </AntLayout>
  )
}
