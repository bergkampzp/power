import { useEffect, useState } from 'react';
import { Alert } from 'antd';

export default function SyncStatusBar() {
  const [s, setS] = useState<any>(null);

  useEffect(() => {
    const poll = () =>
      fetch('/api/sync/status')
        .then(r => r.json())
        .then(setS)
        .catch(() => {});
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, []);

  if (!s) return null;
  if (s.in_progress) return <Alert type="info" message="数据更新中…" banner />;
  if (!s.cookie_valid)
    return (
      <Alert
        type="warning"
        message="平台 cookie 失效，请在用户中心重新录入"
        banner
      />
    );
  return (
    <Alert
      type="success"
      message={`数据已更新 (${s.last_run || ''})`}
      banner
    />
  );
}
