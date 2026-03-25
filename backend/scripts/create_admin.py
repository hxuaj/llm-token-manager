#!/usr/bin/env python3
"""
创建管理员账号脚本

用法：
    python scripts/create_admin.py <username> <email> <password>
    python scripts/create_admin.py  # 交互式输入

或者提升现有用户为管理员：
    python scripts/create_admin.py --promote <username>
"""
import sys
import asyncio
import os

# 添加 backend 目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from database import async_session_maker, engine
from models.user import User, UserRole
from services.auth import hash_password


async def create_admin(username: str, email: str, password: str):
    """创建新的管理员账号"""
    async with async_session_maker() as session:
        # 检查用户名是否已存在
        result = await session.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none():
            print(f"错误：用户名 '{username}' 已存在")
            return False

        # 检查邮箱是否已存在
        result = await session.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            print(f"错误：邮箱 '{email}' 已存在")
            return False

        # 创建管理员
        admin = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            monthly_quota_usd=1000.00,  # 管理员给予较高额度
            rpm_limit=1000,
            max_keys=20,
            is_active=True,
        )
        session.add(admin)
        await session.commit()

        print(f"管理员创建成功：{username} ({email})")
        return True


async def promote_to_admin(username: str):
    """将现有用户提升为管理员"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if not user:
            print(f"错误：用户 '{username}' 不存在")
            return False

        if user.role == UserRole.ADMIN:
            print(f"用户 '{username}' 已经是管理员")
            return True

        user.role = UserRole.ADMIN
        await session.commit()

        print(f"已将用户 '{username}' 提升为管理员")
        return True


async def list_users():
    """列出所有用户"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).order_by(User.created_at)
        )
        users = result.scalars().all()

        print("\n当前用户列表：")
        print("-" * 50)
        for u in users:
            role_label = "[管理员]" if u.role == UserRole.ADMIN else "[普通用户]"
            status = "正常" if u.is_active else "禁用"
            print(f"  {u.username:20} {u.email:25} {role_label} {status}")
        print("-" * 50)


async def main():
    if len(sys.argv) == 1:
        # 交互式模式
        print("=== 创建管理员账号 ===\n")
        await list_users()
        print()

        choice = input("选择操作: [1] 创建新管理员  [2] 提升现有用户  [q] 退出: ").strip()

        if choice == "1":
            username = input("用户名: ").strip()
            email = input("邮箱: ").strip()
            password = input("密码: ").strip()

            if username and email and password:
                await create_admin(username, email, password)
            else:
                print("错误：所有字段都必须填写")

        elif choice == "2":
            username = input("要提升的用户名: ").strip()
            if username:
                await promote_to_admin(username)

    elif sys.argv[1] == "--promote":
        if len(sys.argv) < 3:
            print("用法: python scripts/create_admin.py --promote <username>")
            return
        await promote_to_admin(sys.argv[2])

    elif sys.argv[1] == "--list":
        await list_users()

    elif len(sys.argv) >= 4:
        # 命令行模式: create_admin.py <username> <email> <password>
        await create_admin(sys.argv[1], sys.argv[2], sys.argv[3])

    else:
        print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
