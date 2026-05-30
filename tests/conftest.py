"""全局测试配置：禁用数据库域拆分，避免测试创建真实域文件。

测试环境使用单文件模式（与拆分前行为一致），防止因权限差异
导致生产环境出现 'attempt to write a readonly database' 错误。
"""

import os

os.environ.setdefault("DB_SPLIT_ENABLED", "0")
