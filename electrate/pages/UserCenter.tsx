import { useState } from 'react'
import { Card, Row, Col, Button, Tag, Input, message } from 'antd'
import { UserOutlined, SettingOutlined, ShopOutlined } from '@ant-design/icons'

const userCards = [
  { title: '售电公司', subtitle: '江苏电力交易中心', status: 'active' },
  { title: '售电公司', subtitle: '备用账户', status: 'inactive' },
  { title: '售电公司', subtitle: '测试账户', status: 'inactive' },
]

function CookiePanel() {
  const [c, setC] = useState('');

  const save = async () => {
    const r = await fetch('/api/admin/cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cookie: c }),
    });
    if (r.ok) {
      message.success('已保存并触发更新');
    } else {
      message.error('保存失败（需超级用户登录）');
    }
  };

  const refresh = async () => {
    await fetch('/api/admin/sync', { method: 'POST' });
    message.info('已触发刷新');
  };

  return (
    <div style={{ marginTop: 24, padding: 16, background: '#f9f9f9', borderRadius: 8 }}>
      <p style={{ fontWeight: 600, marginBottom: 8 }}>数据同步（超级用户专用）</p>
      <p style={{ color: '#666', marginBottom: 8 }}>
        平台会话 Cookie — 从浏览器登录 spot.poweremarket.com 后，
        打开开发者工具复制 CAMSID 的值粘贴到此处：
      </p>
      <Input.TextArea
        rows={2}
        value={c}
        onChange={e => setC(e.target.value)}
        placeholder="CAMSID=..."
      />
      <Button type="primary" onClick={save} style={{ marginTop: 8, marginRight: 8 }}>
        保存 Cookie
      </Button>
      <Button onClick={refresh} style={{ marginTop: 8 }}>
        立即刷新
      </Button>
    </div>
  );
}

export default function UserCenter() {
  return (
    <div>
      <h2 style={{ color: '#fff', marginBottom: 24 }}>个人中心</h2>
      
      {/* 用户信息卡片 */}
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <div
            style={{
              width: 120,
              height: 120,
              background: 'linear-gradient(135deg, #1E88E5 0%, #42A5F5 100%)',
              borderRadius: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <UserOutlined style={{ fontSize: 64, color: '#fff' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
              <h2 style={{ color: '#fff', margin: 0 }}>江苏测试</h2>
              <Tag color="blue">江苏</Tag>
            </div>
            <div style={{ color: '#999', marginBottom: 8 }}>用户机构：江苏电力交易中心</div>
            <div style={{ color: '#999', marginBottom: 8 }}>邮箱：test_jiangsu@163.com</div>
            <div style={{ color: '#999' }}>角色：售电公司管理员</div>
          </div>
          <Button icon={<SettingOutlined />}>设置</Button>
        </div>
      </Card>

      {/* 用户卡片网格 */}
      <Row gutter={[16, 16]}>
        {userCards.map((card, index) => (
          <Col span={8} key={index}>
            <Card
              hoverable
              style={{
                background: card.status === 'active' ? '#1E88E520' : '#1f1f1f',
                borderColor: card.status === 'active' ? '#1E88E5' : '#303030',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div
                  style={{
                    width: 56,
                    height: 56,
                    background: card.status === 'active' ? '#1E88E5' : '#434343',
                    borderRadius: 8,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <ShopOutlined style={{ fontSize: 28, color: '#fff' }} />
                </div>
                <div>
                  <div style={{ color: '#fff', fontSize: 16, fontWeight: 500, marginBottom: 4 }}>
                    {card.title}
                  </div>
                  <div style={{ color: '#999', fontSize: 14 }}>{card.subtitle}</div>
                  {card.status === 'active' && (
                    <Tag color="success" style={{ marginTop: 8 }}>当前使用</Tag>
                  )}
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 数据同步面板 */}
      <CookiePanel />

      {/* 功能模块 */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col span={12}>
          <Card title="账户安全">
            <div style={{ color: '#999', padding: '20px 0' }}>
              <div style={{ marginBottom: 16 }}>
                <span style={{ color: '#fff' }}>登录密码</span>
                <span style={{ float: 'right', color: '#52c41a' }}>已设置</span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <span style={{ color: '#fff' }}>手机绑定</span>
                <span style={{ float: 'right', color: '#52c41a' }}>已绑定</span>
              </div>
              <div>
                <span style={{ color: '#fff' }}>邮箱绑定</span>
                <span style={{ float: 'right', color: '#52c41a' }}>已绑定</span>
              </div>
            </div>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="系统设置">
            <div style={{ color: '#999', padding: '20px 0' }}>
              <div style={{ marginBottom: 16 }}>
                <span style={{ color: '#fff' }}>主题设置</span>
                <span style={{ float: 'right' }}>深色模式</span>
              </div>
              <div style={{ marginBottom: 16 }}>
                <span style={{ color: '#fff' }}>语言设置</span>
                <span style={{ float: 'right' }}>简体中文</span>
              </div>
              <div>
                <span style={{ color: '#fff' }}>通知设置</span>
                <span style={{ float: 'right', color: '#52c41a' }}>已开启</span>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
