# 业务逻辑目录
# 不依赖 HTTP 层的纯业务逻辑：
# - proxy.py           # 请求转发核心逻辑
# - user_key_service.py # Key 生成/验证/吊销
# - quota.py           # 额度检查与更新
# - key_manager.py     # 供应商 Key 加解密与轮转
# - billing.py         # 计费逻辑
# - providers/         # 各供应商适配器
