#!/bin/bash
#
# 数据库迁移管理脚本
#
# 使用方法:
#   ./migrate.sh <command> [args]
#
# 命令:
#   status          - 查看当前迁移状态
#   upgrade         - 升级到最新版本
#   downgrade       - 回退一个版本
#   generate <msg>  - 生成新的迁移脚本（在修改模型后使用）
#   history         - 查看迁移历史
#   reset           - 重置数据库（危险！删除所有数据）
#
# 什么时候需要运行迁移？
# ----------------------
# 1. 修改了 models/ 目录下的任何模型（添加/删除/修改字段）
# 2. 拉取了包含模型变更的代码
# 3. 在新环境部署时
#

set -e

# 切换到 backend 目录
cd "$(dirname "$0")"

# 激活虚拟环境（如果存在）
if [ -d "../venv" ]; then
    source ../venv/bin/activate
elif [ -n "$CONDA_PREFIX" ]; then
    # conda 环境已激活
    :
elif [ -f "/Users/hxuaj/miniconda3/envs/llm-token-manager/bin/python" ]; then
    export PATH="/Users/hxuaj/miniconda3/envs/llm-token-manager/bin:$PATH"
fi

case "$1" in
    status)
        echo "📊 当前迁移状态:"
        echo "-------------------"
        alembic current
        echo ""
        echo "📋 待应用的迁移:"
        alembic show head 2>/dev/null || echo "无"
        ;;

    upgrade)
        echo "⬆️  升级数据库..."
        alembic upgrade head
        echo "✅ 数据库已升级到最新版本"
        ;;

    downgrade)
        echo "⬇️  回退一个版本..."
        alembic downgrade -1
        echo "✅ 数据库已回退"
        ;;

    generate)
        if [ -z "$2" ]; then
            echo "❌ 错误: 请提供迁移描述"
            echo "用法: ./migrate.sh generate \"描述信息\""
            exit 1
        fi
        echo "📝 生成迁移脚本: $2"
        alembic revision --autogenerate -m "$2"
        echo ""
        echo "⚠️  请检查生成的脚本: alembic/versions/"
        echo "   确认无误后运行: ./migrate.sh upgrade"
        ;;

    history)
        echo "📜 迁移历史:"
        alembic history
        ;;

    reset)
        echo "⚠️  警告: 这将删除所有数据!"
        read -p "确定要继续吗? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            rm -f llm_manager.db
            rm -f test_llm_manager.db
            alembic upgrade head
            echo "✅ 数据库已重置"
        else
            echo "已取消"
        fi
        ;;

    *)
        echo "LLM Token Manager - 数据库迁移工具"
        echo ""
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  status          查看当前迁移状态"
        echo "  upgrade         升级到最新版本"
        echo "  downgrade       回退一个版本"
        echo "  generate <msg>  生成新的迁移脚本"
        echo "  history         查看迁移历史"
        echo "  reset           重置数据库（危险！）"
        echo ""
        echo "示例:"
        echo "  $0 status"
        echo "  $0 generate \"添加 api_format 字段\""
        echo "  $0 upgrade"
        ;;
esac
