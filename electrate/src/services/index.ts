/**
 * API 服务 - 电力交易系统
 */

const API_BASE = '/api'

// Dashboard 数据
export async function getDashboardData() {
  const res = await fetch(`${API_BASE}/dashboard`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 日均价
export async function getDailyPrice(params?: { start_date?: string; end_date?: string }) {
  const query = new URLSearchParams(params as any).toString()
  const res = await fetch(`${API_BASE}/price/daily?${query}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 实时电价
export async function getRealtimePrice() {
  const res = await fetch(`${API_BASE}/price/realtime`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 节点电价
export async function getNodePrice(nodeName: string) {
  const res = await fetch(`${API_BASE}/price/node/${nodeName}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 分时电价
export async function getHourlyPrice(date: string) {
  const res = await fetch(`${API_BASE}/price/hourly?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 电价预测
export async function predictPrice(data: { date: string; features?: any }) {
  const res = await fetch(`${API_BASE}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '预测失败')
  return json.prediction
}

// 周预测
export async function getWeeklyPrediction() {
  const res = await fetch(`${API_BASE}/predict/weekly`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 交易建议
export async function getTradingAdvice() {
  const res = await fetch(`${API_BASE}/advice`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 分时负荷
export async function getHourlyLoad(date: string) {
  const res = await fetch(`${API_BASE}/load/hourly?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 分时新能源出力
export async function getHourlyRenewable(date: string) {
  const res = await fetch(`${API_BASE}/renewable/hourly?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 节点列表
export async function getNodes() {
  const res = await fetch(`${API_BASE}/nodes`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 数据汇总
export async function getDataSummary() {
  const res = await fetch(`${API_BASE}/data/summary`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 数据导出
export async function exportData(params?: { start_date?: string; end_date?: string; format?: string }) {
  const query = new URLSearchParams(params as any).toString()
  window.open(`${API_BASE}/data/export?${query}`)
}

// ========== 5大核心电价 API ==========

// 日前节点电价（96点分时）
export async function getDayAheadNodePrice(date: string) {
  const res = await fetch(`${API_BASE}/price/day-ahead-node?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 日前用电侧电价（分时）
export async function getDayAheadDemandPrice(date: string) {
  const res = await fetch(`${API_BASE}/price/day-ahead-demand?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 实时节点电价（96点分时）
export async function getRealtimeNodePrice(date: string) {
  const res = await fetch(`${API_BASE}/price/realtime-node?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 实时用电侧电价（分时）
export async function getRealtimeDemandPrice(date: string) {
  const res = await fetch(`${API_BASE}/price/realtime-demand?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data
}

// 3天电价预测（日均）
export async function get3DayPrediction() {
  const res = await fetch(`${API_BASE}/price/prediction-3day`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.predictions
}

// 实时用电侧负荷 + 光伏预测出力
export async function getRealtimeDemandWithSolar(date: string) {
  const res = await fetch(`${API_BASE}/realtime-demand-with-solar?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.data as Array<{
    hour: number
    period: string
    demand: number | null
    solar_forecast: number | null
  }>
}

// 3天逐小时预测 vs 实时节点均价（基于指定日期）
export async function get3DayPredictionHourly(date: string) {
  const res = await fetch(`${API_BASE}/price/prediction-3day-hourly?date=${date}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error || '获取失败')
  return json.days as Array<{
    date: string
    predicted: number[]
    actual: (number | null)[]
  }>
}

// 导出统一服务对象
export const priceService = {
  getDashboardData,
  getDailyPrice,
  getRealtimePrice,
  getNodePrice,
  getHourlyPrice,
  predictPrice,
  getWeeklyPrediction,
  getTradingAdvice,
  getHourlyLoad,
  getHourlyRenewable,
  getNodes,
  getDataSummary,
  exportData,
  getDayAheadNodePrice,
  getDayAheadDemandPrice,
  getRealtimeNodePrice,
  getRealtimeDemandPrice,
  get3DayPrediction,
  get3DayPredictionHourly,
  getRealtimeDemandWithSolar,
}

export default priceService