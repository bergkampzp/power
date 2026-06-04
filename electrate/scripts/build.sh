#!/bin/bash
# ==================================================
# 水电站电价预测系统 - 打包脚本
# ==================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ELECTRATE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$ELECTRATE_DIR")"
DATA_DIR="$PROJECT_ROOT/power-data"

# 输出目录
OUTPUT_DIR="$SCRIPT_DIR/dist"
PACKAGE_NAME="electrate-$(date +%Y%m%d-%H%M%S)"
PACKAGE_DIR="$OUTPUT_DIR/$PACKAGE_NAME"

echo -e "${GREEN}=================================================="
echo "水电站电价预测系统 - 打包工具"
echo "==================================================${NC}"

# 清理旧的输出目录
echo -e "${YELLOW}[1/6] 清理构建目录...${NC}"
rm -rf "$OUTPUT_DIR"
mkdir -p "$PACKAGE_DIR"

# 编译前端
echo -e "${YELLOW}[2/6] 编译前端项目...${NC}"
cd "$ELECTRATE_DIR"
npm run build

if [ ! -d "dist" ]; then
    echo -e "${RED}错误: 前端编译失败，dist 目录不存在${NC}"
    exit 1
fi

# 复制前端编译产物
echo -e "${YELLOW}[3/6] 复制前端文件...${NC}"
cp -r "$ELECTRATE_DIR/dist" "$PACKAGE_DIR/frontend"

# 复制后端文件
echo -e "${YELLOW}[4/6] 复制后端文件...${NC}"
mkdir -p "$PACKAGE_DIR/backend"
cp "$ELECTRATE_DIR/api_server.py" "$PACKAGE_DIR/backend/"

# 复制数据库
echo -e "${YELLOW}[5/6] 复制数据库文件...${NC}"
mkdir -p "$PACKAGE_DIR/data"
if [ -f "$DATA_DIR/power_market_v2.db" ]; then
    cp "$DATA_DIR/power_market_v2.db" "$PACKAGE_DIR/data/"
    echo "  - 数据库文件已复制"
else
    echo -e "${RED}警告: 数据库文件不存在: $DATA_DIR/power_market_v2.db${NC}"
fi

# 复制部署脚本和配置文件
echo -e "${YELLOW}[6/6] 创建部署配置...${NC}"

# 创建 nginx 配置
cat > "$PACKAGE_DIR/nginx.conf" << 'EOF'
server {
    listen 80;
    server_name _;

    # 前端静态文件
    location / {
        root /opt/electrate/frontend;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_min_length 1000;
}
EOF

# 创建 systemd 服务配置
cat > "$PACKAGE_DIR/electrate-api.service" << 'EOF'
[Unit]
Description=Electrate API Server
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/electrate/backend
Environment="DB_PATH=/opt/electrate/data/power_market_v2.db"
ExecStart=/usr/bin/python3 /opt/electrate/backend/api_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 创建部署脚本
cat > "$PACKAGE_DIR/deploy.sh" << 'DEPLOY_EOF'
#!/bin/bash
# ==================================================
# 水电站电价预测系统 - 部署脚本
# ==================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/electrate"

# 默认端口配置（可通过环境变量覆盖）
WEB_PORT=${WEB_PORT:-8888}
API_PORT=${API_PORT:-15001}

echo -e "${GREEN}=================================================="
echo "水电站电价预测系统 - 部署工具"
echo "==================================================${NC}"
echo ""
echo "配置信息:"
echo "  - Web 端口: $WEB_PORT"
echo "  - API 端口: $API_PORT"
echo "  - 访问路径: /electrate/"
echo "  - 安装目录: $INSTALL_DIR"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    echo "用法: sudo WEB_PORT=8888 API_PORT=15001 ./deploy.sh"
    exit 1
fi

# 检查端口是否被占用
check_port() {
    if lsof -i :$1 > /dev/null 2>&1; then
        echo -e "${RED}错误: 端口 $1 已被占用${NC}"
        lsof -i :$1
        exit 1
    fi
}

echo -e "${YELLOW}[1/7] 检查端口...${NC}"
check_port $WEB_PORT
check_port $API_PORT

# 更新系统
echo -e "${YELLOW}[2/7] 更新系统包...${NC}"
apt-get update -qq

# 安装依赖
echo -e "${YELLOW}[3/7] 安装依赖...${NC}"
apt-get install -y -qq python3 python3-pip nginx lsof

# 安装 Python 依赖
echo -e "${YELLOW}[4/7] 安装 Python 依赖...${NC}"
pip3 install flask flask-cors --break-system-packages --ignore-installed blinker -q

# 创建安装目录
echo -e "${YELLOW}[5/7] 安装应用文件...${NC}"
mkdir -p "$INSTALL_DIR"

# 复制文件
cp -r frontend "$INSTALL_DIR/"
cp -r backend "$INSTALL_DIR/"
cp -r data "$INSTALL_DIR/"

# 修改 API 服务端口配置
sed -i "s/port=5001/port=$API_PORT/g" "$INSTALL_DIR/backend/api_server.py"

# 设置权限
chown -R www-data:www-data "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

# 配置 nginx
echo -e "${YELLOW}[6/7] 配置 Nginx (端口: $WEB_PORT)...${NC}"
cat > /etc/nginx/sites-available/electrate << NGINX_EOF
server {
    listen $WEB_PORT;
    server_name _;

    # 前端静态文件
    location /electrate/ {
        alias /opt/electrate/frontend/;
        index index.html;
        try_files \$uri \$uri/ /electrate/index.html;
    }

    # 根路径重定向
    location = / {
        return 301 /electrate/;
    }

    # API 代理
    location /electrate/api {
        rewrite ^/electrate/api(.*)\$ \$1 break;
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    gzip_min_length 1000;
}
NGINX_EOF

# 禁用默认站点（如果需要保留其他站点，注释掉下面这行）
# rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/electrate /etc/nginx/sites-enabled/electrate

# 测试并重载 nginx
nginx -t && systemctl reload nginx

# 配置 systemd 服务
echo -e "${YELLOW}[7/7] 配置系统服务 (API端口: $API_PORT)...${NC}"
cat > /etc/systemd/system/electrate-api.service << SERVICE_EOF
[Unit]
Description=Electrate API Server
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/electrate/backend
Environment="DB_PATH=/opt/electrate/data/power_market_v2.db"
ExecStart=/usr/bin/python3 /opt/electrate/backend/api_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable electrate-api
systemctl restart electrate-api

# 检查服务状态
sleep 2
if systemctl is-active --quiet electrate-api; then
    SERVER_IP=$(hostname -I | awk '{print $1}')
    echo -e "${GREEN}=================================================="
    echo "部署成功!"
    echo "==================================================${NC}"
    echo ""
    echo "访问地址: http://$SERVER_IP:$WEB_PORT/electrate/"
    echo ""
    echo "端口配置:"
    echo "  - Web 端口: $WEB_PORT"
    echo "  - API 端口: $API_PORT (内部)"
    echo ""
    echo "常用命令:"
    echo "  查看API状态: sudo systemctl status electrate-api"
    echo "  重启API服务: sudo systemctl restart electrate-api"
    echo "  查看API日志: sudo journalctl -u electrate-api -f"
    echo "  重启Nginx:   sudo systemctl reload nginx"
    echo ""
    echo "配置文件位置:"
    echo "  Nginx配置:   /etc/nginx/sites-available/electrate"
    echo "  API配置:     /opt/electrate/backend/api_server.py"
else
    echo -e "${RED}API 服务启动失败，请检查日志${NC}"
    journalctl -u electrate-api --no-pager -n 20
    exit 1
fi
DEPLOY_EOF

chmod +x "$PACKAGE_DIR/deploy.sh"

# 创建版本信息
cat > "$PACKAGE_DIR/VERSION" << EOF
版本: $(date +%Y%m%d-%H%M%S)
构建时间: $(date)
前端: React + Vite
后端: Flask + Python3
EOF

# 创建使用说明
cat > "$PACKAGE_DIR/README.txt" << 'EOF'
水电站电价预测系统 - 部署说明
================================

【快速部署】

1. 上传压缩包到服务器
   scp electrate-*.tar.gz user@server:/tmp/

2. 解压并运行部署脚本
   cd /tmp
   tar -xzf electrate-*.tar.gz
   cd electrate-*
   sudo ./deploy.sh

3. 访问系统
   浏览器打开 http://服务器IP:8888/electrate/

【自定义端口部署】

使用环境变量自定义端口：

  sudo WEB_PORT=9999 API_PORT=16001 ./deploy.sh

默认配置:
  - Web 端口: 8888
  - API 端口: 15001 (内部)
  - 访问路径: /electrate/

【目录结构】

/opt/electrate/
├── frontend/     # 前端静态文件
├── backend/      # 后端 API 服务
└── data/         # 数据库文件

【常用命令】

查看API状态: sudo systemctl status electrate-api
重启API服务: sudo systemctl restart electrate-api
查看API日志: sudo journalctl -u electrate-api -f
重载Nginx:   sudo systemctl reload nginx

【修改端口】

1. 修改 Web 端口:
   编辑 /etc/nginx/sites-available/electrate
   修改 listen 端口号
   执行: sudo systemctl reload nginx

2. 修改 API 端口:
   编辑 /opt/electrate/backend/api_server.py
   修改最后一行的 port 参数
   执行: sudo systemctl restart electrate-api

【与其他服务共存】

本部署方案使用独立的 Nginx 配置文件，不会影响服务器上已有的其他服务。
只需确保配置的端口未被占用即可。
EOF

# 打包
echo -e "${YELLOW}创建压缩包...${NC}"
cd "$OUTPUT_DIR"
tar -czf "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

# 计算文件大小
PACKAGE_SIZE=$(du -h "$PACKAGE_NAME.tar.gz" | cut -f1)

echo -e "${GREEN}=================================================="
echo "打包完成!"
echo "==================================================${NC}"
echo "输出文件: $OUTPUT_DIR/$PACKAGE_NAME.tar.gz"
echo "文件大小: $PACKAGE_SIZE"
echo ""
echo "包含内容:"
echo "  - frontend/     前端编译文件"
echo "  - backend/      后端 API 服务"
echo "  - data/         数据库文件"
echo "  - deploy.sh     部署脚本"
echo "  - nginx.conf    Nginx 配置"
echo "  - electrate-api.service  系统服务配置"
