#!/bin/bash
#
# PostgreSQL 兼容性测试脚本
# 自动启动临时 PostgreSQL 容器，运行测试，然后清理
#
# 用法:
#   ./scripts/test-pg-compat.sh              # 运行所有兼容性测试
#   ./scripts/test-pg-compat.sh -v           # 详细输出
#   ./scripts/test-pg-compat.sh --keep       # 测试后保留容器
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
CONTAINER_NAME="ltm-test-pg"
POSTGRES_PORT=5433
POSTGRES_PASSWORD="test"
KEEP_CONTAINER=false

# 解析参数
PYTEST_ARGS=""
for arg in "$@"; do
    if [ "$arg" == "--keep" ]; then
        KEEP_CONTAINER=true
    else
        PYTEST_ARGS="$PYTEST_ARGS $arg"
    fi
done

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  PostgreSQL 兼容性测试${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}错误: Docker 未运行，请先启动 Docker${NC}"
    exit 1
fi

# 清理可能存在的旧容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}清理旧容器...${NC}"
    docker rm -f ${CONTAINER_NAME} > /dev/null 2>&1 || true
fi

# 启动 PostgreSQL 容器
echo -e "${GREEN}启动临时 PostgreSQL 容器...${NC}"
docker run -d \
    --name ${CONTAINER_NAME} \
    -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} \
    -p ${POSTGRES_PORT}:5432 \
    postgres:15-alpine > /dev/null

# 等待数据库就绪
echo -e "${GREEN}等待数据库就绪...${NC}"
max_retries=30
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if docker exec ${CONTAINER_NAME} pg_isready -U postgres > /dev/null 2>&1; then
        break
    fi
    retry_count=$((retry_count + 1))
    sleep 1
done

if [ $retry_count -eq $max_retries ]; then
    echo -e "${RED}错误: 数据库启动超时${NC}"
    docker rm -f ${CONTAINER_NAME} > /dev/null 2>&1 || true
    exit 1
fi

echo -e "${GREEN}数据库就绪${NC}"
echo ""

# 设置 PostgreSQL 测试 URL
export POSTGRES_TEST_URL="postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/postgres"

# 切换到 backend 目录
cd "$(dirname "$0")/../backend"

# 运行兼容性测试
echo -e "${GREEN}运行兼容性测试...${NC}"
echo ""

set +e
/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python -m pytest tests/test_postgres_compat.py -v $PYTEST_ARGS
TEST_RESULT=$?
set -e

echo ""

# 清理
if [ "$KEEP_CONTAINER" = true ]; then
    echo -e "${YELLOW}保留容器 ${CONTAINER_NAME} (端口 ${POSTGRES_PORT})${NC}"
    echo "手动清理: docker rm -f ${CONTAINER_NAME}"
else
    echo -e "${GREEN}清理容器...${NC}"
    docker rm -f ${CONTAINER_NAME} > /dev/null 2>&1 || true
fi

echo ""
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  PostgreSQL 兼容性测试通过 ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  PostgreSQL 兼容性测试失败 ✗${NC}"
    echo -e "${RED}========================================${NC}"
fi

exit $TEST_RESULT
