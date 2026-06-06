"""
水电站电价预测系统 - Flask API 服务
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import os
import random

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'power-data', 'power_market_v2.db')


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Auto data-pull: super-user auth + sync routes ──────────────────────────
import sys as _sys, functools
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'power-data'))
from flask import session
from data_pull.schema import ensure_schema as _ensure_schema
from data_pull import auth as _auth, cookie_store as _cookie_store, orchestrator as _orchestrator

app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret-change-me')

def _dpconn():
    return sqlite3.connect(DB_PATH)

# Initialise schema on startup (idempotent)
with _dpconn() as _c:
    _ensure_schema(_c)

def require_super(fn):
    @functools.wraps(fn)
    def _w(*a, **k):
        if not session.get('is_super'):
            return jsonify({"error": "unauthorized"}), 401
        return fn(*a, **k)
    return _w

@app.route('/api/login', methods=['POST'])
def api_login():
    body = request.get_json(force=True) or {}
    with _dpconn() as c:
        if _auth.verify(c, body.get('username', ''), body.get('password', '')):
            session['is_super'] = True
            _orchestrator.trigger_sync(DB_PATH)
            return jsonify({"ok": True, "sync": "started"})
    return jsonify({"error": "bad_credentials"}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route('/api/admin/cookie', methods=['POST'])
@require_super
def api_set_cookie():
    with _dpconn() as c:
        _cookie_store.set_cookie(c, (request.get_json(force=True) or {}).get('cookie', ''))
    _orchestrator.trigger_sync(DB_PATH)
    return jsonify({"ok": True})

@app.route('/api/admin/sync', methods=['POST'])
@require_super
def api_manual_sync():
    return jsonify(_orchestrator.trigger_sync(DB_PATH))

@app.route('/api/sync/status', methods=['GET'])
def api_sync_status():
    with _dpconn() as c:
        return jsonify(_orchestrator.get_status(c))

from data_pull import pairing as _pairing

@app.route('/api/admin/pairing-token', methods=['POST'])
@require_super
def api_pairing_token():
    with _dpconn() as c:
        return jsonify({"token": _pairing.generate_token(c)})

@app.route('/api/extension/cookie', methods=['POST'])
def api_extension_cookie():
    body = request.get_json(force=True) or {}
    token = body.get('token', '')
    cookie = body.get('cookie', '')
    with _dpconn() as c:
        if not _pairing.verify_token(c, token):
            return jsonify({"error": "bad_token"}), 401
        if 'CAMSID' not in cookie:
            return jsonify({"error": "expect_camsid"}), 400
        _cookie_store.set_cookie(c, cookie)
    _orchestrator.trigger_sync(DB_PATH)
    return jsonify({"ok": True})
# ── end auto data-pull routes ───────────────────────────────────────────────


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': '水电站电价预测系统 API'
    })


@app.route('/api/price/daily', methods=['GET'])
def get_daily_price():
    """获取日均价数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取查询参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # 构建查询
        if start_date and end_date:
            cursor.execute('''
                SELECT trade_date, AVG(avg_price) as price
                FROM day_ahead_node_price
                WHERE trade_date >= ? AND trade_date <= ?
                GROUP BY trade_date
                ORDER BY trade_date ASC
            ''', (start_date, end_date))
        else:
            # 默认最近30天
            cursor.execute('''
                SELECT trade_date, AVG(avg_price) as price
                FROM day_ahead_node_price
                GROUP BY trade_date
                ORDER BY trade_date DESC
                LIMIT 30
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'date': row['trade_date'],
            'price': round(row['price'], 2)
        } for row in (reversed(rows) if not (start_date and end_date) else rows)]
        
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/price/realtime', methods=['GET'])
def get_realtime_price():
    """获取实时电价数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT trade_date, node_name, avg_price, min_price, max_price
            FROM realtime_node_price
            ORDER BY trade_date DESC
            LIMIT 100
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'date': row['trade_date'],
            'node': row['node_name'],
            'avg': row['avg_price'],
            'min': row['min_price'],
            'max': row['max_price']
        } for row in rows]
        
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/price/node/<node_name>', methods=['GET'])
def get_node_price(node_name):
    """获取指定节点的电价数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT trade_date, avg_price, min_price, max_price
            FROM day_ahead_node_price
            WHERE node_name = ?
            ORDER BY trade_date DESC
            LIMIT 30
        ''', (node_name,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'date': row['trade_date'],
            'avg': row['avg_price'],
            'min': row['min_price'],
            'max': row['max_price']
        } for row in reversed(rows)]
        
        return jsonify({
            'success': True,
            'node': node_name,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/predict', methods=['POST'])
def predict_price():
    """电价预测接口"""
    try:
        data = request.get_json()
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        # 这里可以调用实际的预测模型
        # 目前返回模拟数据
        prediction = {
            'date': date,
            'price': 258.3,
            'confidence': 0.85,
            'range': [245.0, 271.6],
            'reason': '基于历史数据和负荷预测'
        }
        
        return jsonify({
            'success': True,
            'prediction': prediction
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/predict/weekly', methods=['GET'])
def get_weekly_prediction():
    """获取周预测数据"""
    try:
        predictions = []
        base_price = 250.0
        
        for i in range(7):
            date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            predictions.append({
                'date': date,
                'price': round(base_price + (i * 5) + (i % 3) * 10, 2),
                'confidence': 0.85 - (i * 0.05)
            })
        
        return jsonify({
            'success': True,
            'predictions': predictions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/data/export', methods=['GET'])
def export_data():
    """数据导出接口"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取所有节点电价数据
        cursor.execute('''
            SELECT * FROM day_ahead_node_price
            ORDER BY trade_date DESC
            LIMIT 1000
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [dict(row) for row in rows]
        
        return jsonify({
            'success': True,
            'count': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/advice', methods=['GET'])
def get_trading_advice():
    """获取交易建议"""
    try:
        advice = {
            'recommendation': '建议持观望态度',
            'reason': '近期电价波动较大，建议等待更明确的市场信号',
            'risk_level': '中等',
            'expected_return': '2-5%',
            'suggested_actions': [
                '密切关注负荷变化',
                '监控新能源出力',
                '设置价格预警'
            ]
        }
        
        return jsonify({
            'success': True,
            'advice': advice
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    """获取首页仪表盘数据"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取最新电价
        cursor.execute('''
            SELECT trade_date, AVG(avg_price) as avg_price
            FROM day_ahead_node_price
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 1
        ''')
        latest = cursor.fetchone()
        
        # 获取节点数量
        cursor.execute('''
            SELECT COUNT(DISTINCT node_name) as count
            FROM day_ahead_node_price
        ''')
        node_count = cursor.fetchone()
        
        # 获取数据日期范围
        cursor.execute('''
            SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date
            FROM day_ahead_node_price
        ''')
        date_range = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'latest_price': round(latest['avg_price'], 2) if latest else None,
                'latest_date': latest['trade_date'] if latest else None,
                'node_count': node_count['count'] if node_count else 0,
                'date_range': {
                    'start': date_range['min_date'] if date_range else None,
                    'end': date_range['max_date'] if date_range else None
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/price/hourly', methods=['GET'])
def get_hourly_price():
    """获取分时电价数据（24小时）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        # 转换日期格式: 2026-03-10 -> 20260310
        date_key = date.replace('-', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询实时电价（96点转24点，从realtime_hourly_price表）
        cursor.execute('''
            SELECT 
                hour + 1 as hour,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
            FROM realtime_hourly_price
            WHERE date_key = ?
            GROUP BY hour
            ORDER BY hour
        ''', (date_key,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 如果realtime_hourly_price没有数据，尝试从96点表获取
        if not rows:
            conn = get_db_connection()
            cursor = conn.cursor()
            # 96点电价转24点
            cursor.execute('''
                SELECT 
                    CAST((CAST(period AS INTEGER) - 1) / 4 + 1 AS INTEGER) as hour,
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price
                FROM realtime_node_price_96
                WHERE date_key = ?
                GROUP BY hour
                ORDER BY hour
            ''', (date_key,))
            rows = cursor.fetchall()
            conn.close()
        
        data = [{
            'hour': row['hour'],
            'avg': round(row['avg_price'], 2) if row['avg_price'] else None,
            'min': round(row['min_price'], 2) if row['min_price'] else None,
            'max': round(row['max_price'], 2) if row['max_price'] else None
        } for row in rows]
        
        return jsonify({
            'success': True,
            'date': date,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/load/hourly', methods=['GET'])
def get_hourly_load():
    """获取分时负荷数据"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                CAST((CAST(period AS INTEGER) - 1) / 4 + 1 AS INTEGER) as hour,
                AVG(forecast_load) as forecast_load,
                AVG(actual_load) as actual_load
            FROM load_forecast
            WHERE trade_date = ?
            GROUP BY hour
            ORDER BY hour
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'hour': row['hour'],
            'forecast': round(row['forecast_load'], 2) if row['forecast_load'] else None,
            'actual': round(row['actual_load'], 2) if row['actual_load'] else None
        } for row in rows]
        
        return jsonify({
            'success': True,
            'date': date,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/renewable/hourly', methods=['GET'])
def get_hourly_renewable():
    """获取新能源分时出力数据"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                CAST((CAST(period AS INTEGER) - 1) / 4 + 1 AS INTEGER) as hour,
                AVG(solar_output) as solar,
                AVG(wind_output) as wind
            FROM renewable_output
            WHERE trade_date = ?
            GROUP BY hour
            ORDER BY hour
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'hour': row['hour'],
            'solar': round(row['solar'], 2) if row['solar'] else 0,
            'wind': round(row['wind'], 2) if row['wind'] else 0
        } for row in rows]
        
        return jsonify({
            'success': True,
            'date': date,
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/nodes', methods=['GET'])
def get_nodes():
    """获取所有节点列表"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT node_name, region
            FROM day_ahead_node_price
            ORDER BY region, node_name
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        nodes = [{
            'name': row['node_name'],
            'region': row['region']
        } for row in rows]
        
        return jsonify({
            'success': True,
            'count': len(nodes),
            'data': nodes
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/data/summary', methods=['GET'])
def get_data_summary():
    """获取数据汇总信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        summary = {}
        
        # 电价数据汇总
        cursor.execute('''
            SELECT 
                COUNT(*) as count,
                COUNT(DISTINCT trade_date) as days,
                MIN(trade_date) as start_date,
                MAX(trade_date) as end_date
            FROM day_ahead_node_price
        ''')
        row = cursor.fetchone()
        summary['price'] = {
            'records': row['count'],
            'days': row['days'],
            'date_range': [row['start_date'], row['end_date']]
        }
        
        # 负荷数据汇总
        cursor.execute('''
            SELECT 
                COUNT(*) as count,
                COUNT(DISTINCT trade_date) as days,
                MIN(trade_date) as start_date,
                MAX(trade_date) as end_date
            FROM load_forecast
        ''')
        row = cursor.fetchone()
        summary['load'] = {
            'records': row['count'],
            'days': row['days'],
            'date_range': [row['start_date'], row['end_date']]
        }
        
        # 新能源数据汇总
        cursor.execute('''
            SELECT 
                COUNT(*) as count,
                COUNT(DISTINCT trade_date) as days,
                MIN(trade_date) as start_date,
                MAX(trade_date) as end_date
            FROM renewable_output
        ''')
        row = cursor.fetchone()
        summary['renewable'] = {
            'records': row['count'],
            'days': row['days'],
            'date_range': [row['start_date'], row['end_date']]
        }
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': summary
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ========== 5大核心电价数据 API ==========

@app.route('/api/price/day-ahead-node', methods=['GET'])
def get_day_ahead_node_price():
    """日前节点电价（96点分时）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 从96点表获取
        cursor.execute('''
            SELECT 
                period,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
            FROM day_ahead_node_price_96
            WHERE trade_date = ?
            GROUP BY period
            ORDER BY CAST(period AS INTEGER)
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'period': row['period'],
            'avg': round(row['avg_price'], 2),
            'min': round(row['min_price'], 2),
            'max': round(row['max_price'], 2)
        } for row in rows]
        
        return jsonify({'success': True, 'date': date, 'type': '日前节点电价', 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/price/day-ahead-demand', methods=['GET'])
def get_day_ahead_demand_price():
    """日前用电侧电价（分时）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT period, demand, price
            FROM day_ahead_demand
            WHERE trade_date = ?
            ORDER BY CAST(period AS INTEGER)
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'period': row['period'],
            'demand': row['demand'],
            'price': row['price']
        } for row in rows]
        
        return jsonify({'success': True, 'date': date, 'type': '日前用电侧电价', 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/price/realtime-node', methods=['GET'])
def get_realtime_node_price():
    """实时节点电价（96点分时）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                period,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price
            FROM realtime_node_price_96
            WHERE trade_date = ?
            GROUP BY period
            ORDER BY period
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'period': row['period'],
            'avg': round(row['avg_price'], 2),
            'min': round(row['min_price'], 2),
            'max': round(row['max_price'], 2)
        } for row in rows]
        
        return jsonify({'success': True, 'date': date, 'type': '实时节点电价', 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/price/realtime-demand', methods=['GET'])
def get_realtime_demand_price():
    """实时用电侧电价（分时）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT period, demand, price
            FROM realtime_demand
            WHERE trade_date = ?
            ORDER BY CAST(period AS INTEGER)
        ''', (date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'period': row['period'],
            'demand': row['demand'],
            'price': row['price']
        } for row in rows]
        
        return jsonify({'success': True, 'date': date, 'type': '实时用电侧电价', 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/realtime-demand-with-solar', methods=['GET'])
def get_realtime_demand_with_solar():
    """实时用电侧负荷 + 光伏预测出力（按小时聚合）"""
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        date_key = date.replace('-', '')

        conn = get_db_connection()
        cursor = conn.cursor()

        # 实时用电侧负荷（24点，demand字段）
        cursor.execute('''
            SELECT CAST(substr(period, 1, 2) AS INTEGER) as hour,
                   AVG(demand) as demand
            FROM realtime_demand
            WHERE trade_date = ?
            GROUP BY hour ORDER BY hour
        ''', (date,))
        demand_rows = cursor.fetchall()

        # 光伏预测出力（renewable_forecast, category='光伏'，forecast_date=date_key）
        cursor.execute('''
            SELECT CAST(substr(period, 1, 2) AS INTEGER) as hour,
                   AVG(forecast_mw) as solar_forecast
            FROM renewable_forecast
            WHERE forecast_date = ? AND category = '光伏'
            GROUP BY hour ORDER BY hour
        ''', (date_key,))
        solar_rows = cursor.fetchall()

        conn.close()

        # 组装为按小时的列表
        demand_map = {r['hour']: round(r['demand'], 2) for r in demand_rows if r['demand'] is not None}
        solar_map = {r['hour']: round(r['solar_forecast'], 2) for r in solar_rows if r['solar_forecast'] is not None}

        data = []
        for h in range(24):
            data.append({
                'hour': h,
                'period': f'{str(h).zfill(2)}:00',
                'demand': demand_map.get(h),
                'solar_forecast': solar_map.get(h),
            })

        return jsonify({'success': True, 'date': date, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 气象数据 API ==========

YUNNAN_CITIES = ['昆明', '曲靖', '玉溪', '保山', '昭通', '丽江', '普洱', '临沧',
                 '楚雄', '红河', '文山', '西双版纳', '大理', '德宏', '怒江', '迪庆']


@app.route('/api/weather/daily', methods=['GET'])
def get_weather_daily():
    """云南各地州每日气象数据"""
    try:
        start = request.args.get('start_date', '')
        end = request.args.get('end_date', '')
        cities_param = request.args.get('cities', '')
        cities = [c for c in cities_param.split(',') if c] if cities_param else YUNNAN_CITIES

        # date 字段格式为 20260315，转为查询格式
        start_key = start.replace('-', '') if start else ''
        end_key = end.replace('-', '') if end else ''

        conn = get_db_connection()
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(cities))
        params = list(cities)
        sql = f'''
            SELECT city, date, temp_max, temp_min, humidity, precip,
                   wind_speed_max, wind_dir, cloud, uv_index, vis, sunrise, sunset
            FROM weather_daily
            WHERE city IN ({placeholders})
        '''
        if start_key:
            sql += ' AND date >= ?'
            params.append(start_key)
        if end_key:
            sql += ' AND date <= ?'
            params.append(end_key)
        sql += ' ORDER BY date, city'

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        data = [{
            'city': r['city'],
            'date': f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}",
            'temp_max': r['temp_max'],
            'temp_min': r['temp_min'],
            'humidity': r['humidity'],
            'precip': r['precip'],
            'wind_speed_max': r['wind_speed_max'],
            'wind_dir': r['wind_dir'],
            'cloud': r['cloud'],
            'uv_index': r['uv_index'],
            'vis': r['vis'],
            'sunrise': r['sunrise'],
            'sunset': r['sunset'],
        } for r in rows]

        return jsonify({'success': True, 'count': len(data), 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/weather/hourly', methods=['GET'])
def get_weather_hourly():
    """云南各地州逐小时气象数据"""
    try:
        date = request.args.get('date', '')
        cities_param = request.args.get('cities', '')
        cities = [c for c in cities_param.split(',') if c] if cities_param else YUNNAN_CITIES
        date_key = date.replace('-', '') if date else ''

        conn = get_db_connection()
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(cities))
        params = list(cities)
        sql = f'''
            SELECT city, date, hour, temp, humidity, precip,
                   wind_speed, wind_360, cloud
            FROM weather_hourly
            WHERE city IN ({placeholders})
        '''
        if date_key:
            sql += ' AND date = ?'
            params.append(date_key)
        sql += ' ORDER BY date, hour, city'

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        data = [{
            'city': r['city'],
            'date': f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:]}",
            'hour': r['hour'],
            'temp': round(r['temp'], 1) if r['temp'] is not None else None,
            'humidity': r['humidity'],
            'precip': r['precip'],
            'wind_speed': round(r['wind_speed'], 2) if r['wind_speed'] is not None else None,
            'wind_360': r['wind_360'],
            'cloud': r['cloud'],
        } for r in rows]

        return jsonify({'success': True, 'count': len(data), 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/weather/cities', methods=['GET'])
def get_weather_cities():
    """云南地州城市列表"""
    return jsonify({'success': True, 'cities': YUNNAN_CITIES})




@app.route('/api/price/prediction-3day-hourly', methods=['GET'])
def get_3day_prediction_hourly():
    """未来3天逐小时预测电价 vs 实时节点均价对比（基于指定日期）"""
    try:
        # 以请求日期为基准，预测其后3天
        base_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        base_dt = datetime.strptime(base_date, '%Y-%m-%d')

        conn = get_db_connection()
        cursor = conn.cursor()

        # 取基准日期前7天的 day_ahead_node_price_96 逐小时均价作为历史参考
        ref_start = (base_dt - timedelta(days=7)).strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT trade_date,
                   CAST(substr(period, 1, 2) AS INTEGER) as hour,
                   AVG(price) as avg_price
            FROM day_ahead_node_price_96
            WHERE trade_date >= ? AND trade_date <= ?
            GROUP BY trade_date, hour
            ORDER BY trade_date, hour
        ''', (ref_start, base_date))
        rows = cursor.fetchall()

        from collections import defaultdict
        import random as _rand

        daily_da = defaultdict(dict)
        for r in rows:
            daily_da[r['trade_date']][r['hour']] = r['avg_price']

        sorted_dates = sorted(daily_da.keys())
        ref_dates = sorted_dates[-5:] if len(sorted_dates) >= 5 else sorted_dates

        # 每小时历史均值
        hour_history = defaultdict(list)
        for d in ref_dates:
            for h in range(24):
                if h in daily_da[d]:
                    hour_history[h].append(daily_da[d][h])

        # 日均价线性趋势
        recent_daily_avg = []
        for d in sorted_dates[-5:]:
            vals = list(daily_da[d].values())
            if vals:
                recent_daily_avg.append(sum(vals) / len(vals))
        daily_trend = 0.0
        if len(recent_daily_avg) >= 2:
            daily_trend = (recent_daily_avg[-1] - recent_daily_avg[0]) / max(len(recent_daily_avg) - 1, 1)

        # 查询未来3天的实时节点均价（真实值）
        pred_dates = [(base_dt + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 4)]
        cursor.execute('''
            SELECT trade_date,
                   CAST(substr(period, 1, 2) AS INTEGER) as hour,
                   AVG(price) as avg_price
            FROM realtime_node_price_96
            WHERE trade_date IN (?, ?, ?)
            GROUP BY trade_date, hour
            ORDER BY trade_date, hour
        ''', pred_dates)
        rt_rows = cursor.fetchall()

        daily_rt = defaultdict(dict)
        for r in rt_rows:
            daily_rt[r['trade_date']][r['hour']] = r['avg_price']

        result = []
        for day_offset, pred_date in enumerate(pred_dates, start=1):
            hourly_pred = []
            hourly_real = []

            for h in range(24):
                hist = hour_history.get(h, [])
                base_val = sum(hist) / len(hist) if hist else 200.0
                _rand.seed(hash(pred_date + str(h)))
                pred_val = base_val + daily_trend * day_offset + (_rand.random() - 0.5) * 15
                hourly_pred.append(round(pred_val, 2))

                real_val = daily_rt.get(pred_date, {}).get(h)
                hourly_real.append(round(real_val, 2) if real_val is not None else None)

            result.append({
                'date': pred_date,
                'predicted': hourly_pred,
                'actual': hourly_real
            })

        conn.close()
        return jsonify({'success': True, 'days': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/price/prediction-3day', methods=['GET'])
def get_3day_prediction():
    """模型预测的未来3天电价"""
    try:
        # 获取最近的实际电价作为参考
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询最近3天的日均价
        cursor.execute('''
            SELECT trade_date, AVG(avg_price) as price
            FROM day_ahead_node_price
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 3
        ''')
        
        historical = cursor.fetchall()
        
        # 简单的预测算法：基于历史趋势外推
        predictions = []
        if len(historical) >= 2:
            # 计算趋势
            prices = [row['price'] for row in reversed(historical)]
            avg_price = sum(prices) / len(prices)
            trend = (prices[-1] - prices[0]) / len(prices) if len(prices) > 1 else 0
            
            # 未来3天预测
            base_date = datetime.strptime(historical[-1]['trade_date'], '%Y-%m-%d')
            for i in range(1, 4):
                pred_date = base_date + timedelta(days=i)
                pred_price = avg_price + trend * i + (random.random() - 0.5) * 20  # 加点随机波动
                predictions.append({
                    'date': pred_date.strftime('%Y-%m-%d'),
                    'price': round(pred_price, 2),
                    'confidence': 0.75 - i * 0.05  # 置信度递减
                })
        
        conn.close()
        
        return jsonify({'success': True, 'predictions': predictions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("水电站电价预测系统 - API 服务")
    print("=" * 50)
    print(f"数据库路径: {DB_PATH}")
    print(f"服务地址: http://localhost:5001")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)
