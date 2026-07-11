#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from api.database import execute_query

results = execute_query(
    "SELECT id, name, vip, type(vip) FROM users",
    (),
    fetch_all=True
)

print("用户列表:")
for r in results:
    print(f"ID: {r[0]}, 名称: {r[1]}, VIP: '{r[2]}', 类型: {r[3]}")
