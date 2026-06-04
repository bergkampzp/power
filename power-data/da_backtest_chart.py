"""
DA Price Backtest Visualization
================================
生成7天回测对比图: 预测 vs 实际 日前电价 24h曲线
数据源: PostgreSQL v_da_backtest_7day 视图

输出:
  1. da_backtest_7day.html  - 交互式 ECharts 图表 (可浏览器打开)
  2. 终端打印 Metabase SQL 配置指引
"""

import psycopg2
import json
import os

PG_CONN = dict(host="localhost", port=5433, user="postgres",
               password="postgres", dbname="warehouse")

def decimal_default(obj):
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def fetch_data():
    conn = psycopg2.connect(**PG_CONN)
    cur = conn.cursor()
    cur.execute("""
        SELECT date_key, trade_date, hour, actual_price, predicted_price, abs_error
        FROM v_da_backtest_7day
        ORDER BY date_key, hour
    """)
    rows = cur.fetchall()

    # Also fetch daily summary
    cur.execute("SELECT * FROM v_da_backtest_daily ORDER BY date_key DESC LIMIT 7")
    daily_cols = [d[0] for d in cur.description]
    daily_rows = cur.fetchall()

    conn.close()
    return rows, daily_rows, daily_cols


def build_html(rows, daily_rows, daily_cols):
    # Group by date
    dates = {}
    for dk, td, h, actual, pred, err in rows:
        if td not in dates:
            dates[td] = {"actual": [None]*24, "predicted": [None]*24, "error": [None]*24, "date_key": dk}
        dates[td]["actual"][h] = round(actual, 2) if actual else 0
        dates[td]["predicted"][h] = round(pred, 2) if pred else 0
        dates[td]["error"][h] = round(err, 2) if err else 0

    sorted_dates = sorted(dates.keys())
    hours = [f"{h:02d}:00" for h in range(24)]

    # Daily summary for the table
    daily_summary = []
    for r in daily_rows:
        d = dict(zip(daily_cols, r))
        daily_summary.append(d)
    daily_summary.reverse()

    # Build chart options for each day
    chart_configs = []
    for td in sorted_dates:
        d = dates[td]
        mae = sum(e for e in d["error"] if e) / max(sum(1 for e in d["error"] if e), 1)
        chart_configs.append({
            "date": td,
            "date_key": d["date_key"],
            "actual": d["actual"],
            "predicted": d["predicted"],
            "error": d["error"],
            "mae": round(mae, 1),
        })

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>日前电价回测对比 - 7天</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: #0f1923; color: #e0e0e0; padding: 20px;
  }}
  .header {{
    text-align: center; margin-bottom: 20px; padding: 15px;
    background: linear-gradient(135deg, #1a2a3a, #0d1b2a);
    border-radius: 8px; border: 1px solid #2a3a4a;
  }}
  .header h1 {{ font-size: 22px; color: #4fc3f7; margin-bottom: 5px; }}
  .header p {{ font-size: 13px; color: #90a4ae; }}
  .summary-bar {{
    display: flex; gap: 12px; margin-bottom: 20px; overflow-x: auto;
    padding-bottom: 5px;
  }}
  .summary-card {{
    flex: 1; min-width: 120px; padding: 12px 15px;
    background: #1a2a3a; border-radius: 8px; text-align: center;
    border: 1px solid #2a3a4a; cursor: pointer; transition: all 0.2s;
  }}
  .summary-card:hover, .summary-card.active {{
    border-color: #4fc3f7; background: #1e3a4a;
  }}
  .summary-card .date {{ font-size: 14px; font-weight: bold; color: #fff; }}
  .summary-card .mae {{ font-size: 20px; margin: 4px 0; }}
  .summary-card .mae.excellent {{ color: #4caf50; }}
  .summary-card .mae.good {{ color: #ff9800; }}
  .summary-card .mae.poor {{ color: #f44336; }}
  .summary-card .label {{ font-size: 11px; color: #78909c; }}
  .charts-container {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 15px;
  }}
  @media (max-width: 1200px) {{ .charts-container {{ grid-template-columns: 1fr; }} }}
  .chart-wrapper {{
    background: #1a2a3a; border-radius: 8px; padding: 15px;
    border: 1px solid #2a3a4a;
  }}
  .chart-wrapper .chart-title {{
    font-size: 14px; color: #b0bec5; margin-bottom: 8px;
    display: flex; justify-content: space-between; align-items: center;
  }}
  .chart-wrapper .chart-title .badge {{
    font-size: 12px; padding: 2px 8px; border-radius: 4px;
  }}
  .badge.excellent {{ background: #1b5e20; color: #4caf50; }}
  .badge.good {{ background: #e65100; color: #ff9800; }}
  .badge.poor {{ background: #b71c1c; color: #f44336; }}
  .chart {{ width: 100%; height: 280px; }}

  .overview-chart {{ width: 100%; height: 400px; margin-bottom: 20px; }}
  .table-section {{
    margin-top: 20px; background: #1a2a3a; border-radius: 8px;
    padding: 15px; border: 1px solid #2a3a4a;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #0d1b2a; padding: 8px; text-align: center; color: #4fc3f7; }}
  td {{ padding: 6px 8px; text-align: center; border-bottom: 1px solid #2a3a4a; }}
  tr:hover td {{ background: #1e3a4a; }}
</style>
</head>
<body>

<div class="header">
  <h1>日前电价预测回测对比</h1>
  <p>模型: P4_DA (GBR + LightGBM + XGBoost 混合) | 节点: 漫湾厂.500kV | 回测: 最近7天</p>
</div>

<!-- Summary cards -->
<div class="summary-bar" id="summaryBar">
</div>

<!-- Overview: all 7 days overlaid -->
<div class="chart-wrapper">
  <div class="chart-title">
    <span>7天总览 - 每日MAE趋势</span>
  </div>
  <div class="overview-chart" id="overviewChart"></div>
</div>

<!-- Individual day charts (2x grid) -->
<div class="charts-container" id="chartsContainer">
</div>

<!-- Daily metrics table -->
<div class="table-section">
  <h3 style="color: #4fc3f7; margin-bottom: 10px;">逐日精度指标</h3>
  <table>
    <thead>
      <tr>
        <th>日期</th>
        <th>小时数</th>
        <th>MAE (元/MWh)</th>
        <th>RMSE</th>
        <th>实际均价</th>
        <th>预测均价</th>
        <th>偏差</th>
        <th>最大误差</th>
        <th>等级</th>
      </tr>
    </thead>
    <tbody id="metricsTable"></tbody>
  </table>
</div>

<script>
const chartData = {json.dumps(chart_configs, ensure_ascii=False, default=decimal_default)};
const hours = {json.dumps(hours)};

// Render summary cards
const summaryBar = document.getElementById('summaryBar');
chartData.forEach((d, i) => {{
  const grade = d.mae < 40 ? 'excellent' : (d.mae < 80 ? 'good' : 'poor');
  const gradeLabel = d.mae < 40 ? '优秀' : (d.mae < 80 ? '一般' : '较差');
  summaryBar.innerHTML += `
    <div class="summary-card ${{i === chartData.length-1 ? 'active' : ''}}" onclick="highlightDay(${{i}})">
      <div class="date">${{d.date}}</div>
      <div class="mae ${{grade}}">${{d.mae}}</div>
      <div class="label">MAE · ${{gradeLabel}}</div>
    </div>`;
}});

// Overview chart: MAE bar + actual/predicted avg lines
const overviewChart = echarts.init(document.getElementById('overviewChart'));
overviewChart.setOption({{
  backgroundColor: 'transparent',
  tooltip: {{ trigger: 'axis' }},
  legend: {{
    data: ['MAE', '实际均价', '预测均价'],
    textStyle: {{ color: '#b0bec5' }},
    top: 5
  }},
  grid: {{ left: 60, right: 60, top: 45, bottom: 30 }},
  xAxis: {{
    type: 'category',
    data: chartData.map(d => d.date),
    axisLabel: {{ color: '#78909c' }},
    axisLine: {{ lineStyle: {{ color: '#2a3a4a' }} }}
  }},
  yAxis: [
    {{
      type: 'value', name: 'MAE', nameTextStyle: {{ color: '#78909c' }},
      axisLabel: {{ color: '#78909c' }},
      splitLine: {{ lineStyle: {{ color: '#1e3040' }} }}
    }},
    {{
      type: 'value', name: '均价 (元/MWh)', nameTextStyle: {{ color: '#78909c' }},
      axisLabel: {{ color: '#78909c' }},
      splitLine: {{ show: false }}
    }}
  ],
  series: [
    {{
      name: 'MAE', type: 'bar', barWidth: 30,
      data: chartData.map(d => ({{
        value: d.mae,
        itemStyle: {{ color: d.mae < 40 ? '#4caf50' : (d.mae < 80 ? '#ff9800' : '#f44336') }}
      }})),
      label: {{ show: true, position: 'top', color: '#e0e0e0', fontSize: 11 }}
    }},
    {{
      name: '实际均价', type: 'line', yAxisIndex: 1,
      data: chartData.map(d => Math.round(d.actual.reduce((a,b) => a + (b||0), 0) / 24)),
      lineStyle: {{ color: '#4fc3f7', width: 2 }},
      itemStyle: {{ color: '#4fc3f7' }}
    }},
    {{
      name: '预测均价', type: 'line', yAxisIndex: 1,
      data: chartData.map(d => Math.round(d.predicted.reduce((a,b) => a + (b||0), 0) / 24)),
      lineStyle: {{ color: '#ff7043', width: 2, type: 'dashed' }},
      itemStyle: {{ color: '#ff7043' }}
    }}
  ]
}});

// Individual day charts
const container = document.getElementById('chartsContainer');
chartData.forEach((d, i) => {{
  const grade = d.mae < 40 ? 'excellent' : (d.mae < 80 ? 'good' : 'poor');
  const gradeLabel = d.mae < 40 ? '优秀' : (d.mae < 80 ? '一般' : '较差');
  container.innerHTML += `
    <div class="chart-wrapper" id="dayWrapper${{i}}">
      <div class="chart-title">
        <span>${{d.date}} 24小时电价曲线</span>
        <span class="badge ${{grade}}">MAE ${{d.mae}} · ${{gradeLabel}}</span>
      </div>
      <div class="chart" id="dayChart${{i}}"></div>
    </div>`;
}});

// Render each day chart
chartData.forEach((d, i) => {{
  const chart = echarts.init(document.getElementById(`dayChart${{i}}`));
  chart.setOption({{
    backgroundColor: 'transparent',
    tooltip: {{
      trigger: 'axis',
      formatter: function(params) {{
        let html = `<b>${{d.date}} ${{params[0].axisValue}}</b><br/>`;
        params.forEach(p => {{
          html += `${{p.marker}} ${{p.seriesName}}: <b>${{p.value}}</b> 元/MWh<br/>`;
        }});
        if (params.length >= 2) {{
          const err = Math.abs(params[0].value - params[1].value).toFixed(1);
          html += `误差: <b>${{err}}</b> 元/MWh`;
        }}
        return html;
      }}
    }},
    legend: {{
      data: ['实际电价', '预测电价'],
      textStyle: {{ color: '#b0bec5', fontSize: 11 }},
      top: 0, right: 10
    }},
    grid: {{ left: 45, right: 15, top: 30, bottom: 25 }},
    xAxis: {{
      type: 'category', data: hours,
      axisLabel: {{ color: '#78909c', fontSize: 10, interval: 3 }},
      axisLine: {{ lineStyle: {{ color: '#2a3a4a' }} }}
    }},
    yAxis: {{
      type: 'value', name: '元/MWh', nameTextStyle: {{ color: '#78909c', fontSize: 10 }},
      axisLabel: {{ color: '#78909c', fontSize: 10 }},
      splitLine: {{ lineStyle: {{ color: '#1e3040' }} }}
    }},
    series: [
      {{
        name: '实际电价', type: 'line',
        data: d.actual, smooth: true,
        lineStyle: {{ color: '#4fc3f7', width: 2.5 }},
        itemStyle: {{ color: '#4fc3f7' }},
        areaStyle: {{ color: 'rgba(79,195,247,0.08)' }}
      }},
      {{
        name: '预测电价', type: 'line',
        data: d.predicted, smooth: true,
        lineStyle: {{ color: '#ff7043', width: 2, type: 'dashed' }},
        itemStyle: {{ color: '#ff7043' }}
      }}
    ]
  }});
}});

// Metrics table
const tbody = document.getElementById('metricsTable');
const dailySummary = {json.dumps([dict(zip(daily_cols, r)) for r in daily_summary], ensure_ascii=False, default=str)};
dailySummary.forEach(d => {{
  const gradeColor = d.grade === '优秀' ? '#4caf50' : (d.grade === '良好' ? '#ff9800' : (d.grade === '一般' ? '#ffc107' : '#f44336'));
  tbody.innerHTML += `
    <tr>
      <td>${{d.trade_date}}</td>
      <td>${{d.n_hours}}</td>
      <td style="color: ${{gradeColor}}; font-weight: bold">${{d.mae}}</td>
      <td>${{d.rmse}}</td>
      <td>${{d.avg_actual}}</td>
      <td>${{d.avg_predicted}}</td>
      <td style="color: ${{d.bias > 0 ? '#ff7043' : '#4fc3f7'}}">${{d.bias > 0 ? '+' : ''}}${{d.bias}}</td>
      <td>${{d.max_error}}</td>
      <td style="color: ${{gradeColor}}">${{d.grade}}</td>
    </tr>`;
}});

function highlightDay(idx) {{
  document.querySelectorAll('.summary-card').forEach((c, i) => {{
    c.classList.toggle('active', i === idx);
  }});
  const el = document.getElementById(`dayWrapper${{idx}}`);
  if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
}}

window.addEventListener('resize', () => {{
  overviewChart.resize();
  chartData.forEach((_, i) => {{
    echarts.getInstanceByDom(document.getElementById(`dayChart${{i}}`))?.resize();
  }});
}});
</script>
</body>
</html>"""
    return html


def main():
    print("Fetching backtest data from PostgreSQL...")
    rows, daily_rows, daily_cols = fetch_data()
    print(f"  {len(rows)} hourly records, {len(daily_rows)} daily summaries")

    html = build_html(rows, daily_rows, daily_cols)
    out_path = os.path.join(os.path.dirname(__file__), "da_backtest_7day.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved: {out_path}")

    # Print Metabase SQL guide
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                   Metabase 配置指南                              ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1. 登录 Metabase: http://localhost:3000                        ║
║                                                                  ║
║  2. 新建问题 → 原生查询 (Native Query)                          ║
║     选择数据库: warehouse                                        ║
║                                                                  ║
║  3. 粘贴以下 SQL (7天24h曲线对比):                               ║
║                                                                  ║
║     SELECT trade_date, hour, series, price                      ║
║     FROM v_da_backtest_chart                                     ║
║     WHERE date_key >= '20260316'                                ║
║     ORDER BY date_key, hour, series                              ║
║                                                                  ║
║  4. 可视化设置:                                                  ║
║     · 图表类型: 折线图 (Line)                                    ║
║     · X轴: hour                                                 ║
║     · Y轴: price                                                ║
║     · 系列: series (实际电价 / 预测电价)                         ║
║     · 分面 (Breakout): trade_date (按日期分7张子图)              ║
║                                                                  ║
║  5. 每日MAE汇总表:                                               ║
║                                                                  ║
║     SELECT * FROM v_da_backtest_daily                            ║
║     ORDER BY date_key DESC LIMIT 7                               ║
║                                                                  ║
║  6. 保存到 Dashboard: "DA电价预测回测"                           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
