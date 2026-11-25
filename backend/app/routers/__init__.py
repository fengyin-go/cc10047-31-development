"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import resource, chains, orphans

# 固定路径（如 /api/orphan-files）先注册，动态的 /api/{module} 留到最后，
# 避免把固定前缀当成模块名。
ROUTERS = [orphans, chains, resource]
