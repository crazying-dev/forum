import sys

sys.path.insert(0, '..')
from api.database import get_all_users

users = get_all_users()
print(f"Total users: {len(users)}")
print("=" * 80)
for i, user in enumerate(users, 1):
	print(f"\nUser #{i}")
	print(f"ID:         {user['id']}")
	print(f"Name:       {user['name']}")
	print(f"Avatar:     {user['avatar']}")
	# print(f"Email:      {user['email']}")
	print(f"Gender:     {user['gender']}")
	print(f"Age:        {user['age']}")
	print(f"Intro:      {user['intro']}")
	print(f"VIP:        {user['vip']}")
	print(f"Created at: {user['created_at']}")
	print(f"Last login: {user['last_login']}")
	print("-" * 60)
