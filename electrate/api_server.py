"""
水电站电价预测系统 - Flask API 服务
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'power-data', 'power_market_v2.db')


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        
        # 获取最近30天的数据
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
        } for row in reversed(rows)]
        
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
                AVG(rt_price) as avg_price,
                MIN(rt_price) as min_price,
                MAX(rt_price) as max_price
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
                    AVG(rt_price) as avg_price,
                    MIN(rt_price) as min_price,
                    MAX(rt_price) as max_price
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


if __name__ == '__main__':
    print("=" * 50)
    print("水电站电价预测系统 - API 服务")
    print("=" * 50)
    print(f"数据库路径: {DB_PATH}")
    print(f"服务地址: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
