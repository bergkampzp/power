import { useState } from 'react';
import { Card, Input, Button, message } from 'antd';

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [u, setU] = useState('');
  const [p, setP] = useState('');

  const submit = async () => {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p }),
    });
    if (r.ok) {
      message.success('登录成功，正在自动更新数据');
      onLogin();
    } else {
      message.error('账号或密码错误');
    }
  };

  return (
    <Card title="超级用户登录" style={{ maxWidth: 360, margin: '80px auto' }}>
      <Input
        placeholder="用户名"
        value={u}
        onChange={e => setU(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Input.Password
        placeholder="密码"
        value={p}
        onChange={e => setP(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Button type="primary" block onClick={submit}>
        登录
      </Button>
    </Card>
  );
}
