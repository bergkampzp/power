/**
 * API 测试页面 - 用于诊断问题
 */
import { useState, useEffect } from 'react'
import { Card, Button, List, Tag, Alert } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { priceService } from '../src/services'

export default function ApiTest() {
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const runTests = async () => {
    setLoading(true)
    setResults([])
    const tests = []

    // 测试 1: Dashboard
    try {
      const dash = await priceService.getDashboardData()
      tests.push({ name: 'Dashboard', status: 'success', data: dash })
    } catch (err: any) {
      tests.push({ name: 'Dashboard', status: 'error', error: err.message })
    }

    // 测试 2: 日均价
    try {
      const daily = await priceService.getDailyPrice({
        start_date: '2026-02-01',
        end_date: '2026-03-10'
      })
      tests.push({ name: '日均价', status: 'success', data: daily, count: daily?.length })
    } catch (err: any) {
      tests.push({ name: '日均价', status: 'error', error: err.message })
    }

    // 测试 3: 分时电价
    try {
      const hourly = await priceService.getHourlyPrice('2026-03-10')
      tests.push({ name: '分时电价', status: 'success', data: hourly, count: hourly?.length })
    } catch (err: any) {
      tests.push({ name: '分时电价', status: 'error', error: err.message })
    }

    // 测试 4: 预测
    try {
      const pred = await priceService.predictPrice({ date: '2026-03-15' })
      tests.push({ name: '预测', status: 'success', data: pred })
    } catch (err: any) {
      tests.push({ name: '预测', status: 'error', error: err.message })
    }

    setResults(tests)
    setLoading(false)
  }

  useEffect(() => {
    runTests()
  }, [])

  return (
    <div style={{ padding: 24 }}>
      <Card 
        title="API 连接测试" 
        extra={<Button icon={<ReloadOutlined />} onClick={runTests} loading={loading}>重新测试</Button>}
      >
        <Alert
          type="info"
          message="测试页面用于诊断 API 连接问题"
          description="检查每个 API 接口是否正常返回数据"
          style={{ marginBottom: 16 }}
        />
        
        <List
          dataSource={results}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <span>
                    {item.name}
                    <Tag color={item.status === 'success' ? 'green' : 'red'} style={{ marginLeft: 8 }}>
                      {item.status === 'success' ? '成功' : '失败'}
                    </Tag>
                  </span>
                }
                description={
                  <div>
                    {item.status === 'success' ? (
                      <pre style={{ fontSize: 12, color: '#52c41a', maxHeight: 100, overflow: 'auto' }}>
                        {JSON.stringify(item.data, null, 2)?.slice(0, 200)}...
                        {item.count !== undefined && ` (共 ${item.count} 条)`}
                      </pre>
                    ) : (
                      <span style={{ color: '#f5222d' }}>{item.error}</span>
                    )}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
