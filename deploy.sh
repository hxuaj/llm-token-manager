#!/bin/bash

# LLM Token Manager 生产环境部署脚本
# 使用方法: ./deploy.sh

set -e

echo "========================================"
echo "  LLM Token Manager 部署脚本"
echo "========================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 .env 文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}未找到 .env 文件，正在从 .env.example 创建...${NC}"
    cp .env.example .env
    echo -e "${RED}请先编辑 .env 文件，填写必要的配置：${NC}"
    echo "  - SECRET_KEY (JWT 签名密钥)"
    echo "  - ENCRYPTION_KEY (32字符加密密钥)"
    echo ""
    echo "可选配置："
    echo "  - LTM_PORT (服务端口，默认 8080)"
    echo "  - LTM_BASE_PATH (基础路径，默认 /ltm)"
    echo ""
    echo "编辑完成后，重新运行此脚本。"
    exit 1
fi

# 加载环境变量
source .env

# 设置默认值
export LTM_PORT=${LTM_PORT:-8080}
export LTM_BASE_PATH=${LTM_BASE_PATH:-/ltm}

# 检查必要的配置
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" == "your-secret-key-change-in-production" ]; then
    echo -e "${RED}错误: 请在 .env 中设置 SECRET_KEY${NC}"
    exit 1
fi

if [ -z "$ENCRYPTION_KEY" ] || [ "$ENCRYPTION_KEY" == "your-encryption-key-32-characters!!" ]; then
    echo -e "${RED}错误: 请在 .env 中设置 ENCRYPTION_KEY (必须32字符)${NC}"
    exit 1
fi

echo -e "${GREEN}配置检查通过${NC}"
echo ""
echo "部署配置:"
echo "  - 端口: ${LTM_PORT}"
echo "  - 基础路径: ${LTM_BASE_PATH}"
echo "  - 访问地址: http://<服务器IP>:${LTM_PORT}${LTM_BASE_PATH}/"

# 生成 nginx 配置
echo ""
echo "生成 nginx 配置..."
envsubst '${LTM_BASE_PATH}' < nginx.conf.tpl > nginx.conf

# 停止旧容器
echo ""
echo "停止旧容器..."
docker compose -f docker-compose.prod.yml down 2>/dev/null || true

# 清除旧的前端构建产物 volume
echo ""
echo "清除旧的前端构建产物..."
docker volume ls -q | grep "_frontend_dist$" | xargs -r docker volume rm

# 构建镜像
echo ""
echo "构建镜像..."
docker compose -f docker-compose.prod.yml build --pull

# 启动服务
echo ""
echo "启动服务..."
docker compose -f docker-compose.prod.yml up -d

# 等待数据库就绪
echo ""
echo "等待数据库就绪..."
sleep 5

# 运行数据库迁移
echo ""
echo "运行数据库迁移..."
docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head

# 显示状态
echo ""
echo "========================================"
echo -e "${GREEN}部署完成！${NC}"
echo "========================================"
echo ""
# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "服务器IP")
echo "服务地址:"
echo "  - 应用: http://${SERVER_IP}:${LTM_PORT}${LTM_BASE_PATH}/"
echo "  - API 文档: http://${SERVER_IP}:${LTM_PORT}${LTM_BASE_PATH}/docs"
echo ""
echo "常用命令:"
echo "  查看日志: docker compose -f docker-compose.prod.yml logs -f"
echo "  停止服务: docker compose -f docker-compose.prod.yml down"
echo "  重启服务: docker compose -f docker-compose.prod.yml restart"
echo ""
