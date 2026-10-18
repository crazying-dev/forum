# 认证 / ALTCHA / 黑名单

## 登录

`POST /ov2/api/auth/login`
```json
{ "name": "用户名或邮箱", "password": "...", "remember": true, "altcha": "<base64>", "grant": "<可选>" }
```
成功：`{ "success": true, "id": "RL..." }`，并写 `forum_session`（HttpOnly）与 `user_id`。

## 注册

`POST /ov2/api/auth/register`
```json
{ "name": "...", "email": "...", "password": "至少8位含字母数字", "code": "6位邮箱码", "altcha": "<base64>" }
```
成功 201；邮箱黑名单命中 400 `邮箱异样`。

## 发注册码 / 忘记密码

- `POST /auth/register/code` body `{email, altcha|grant}`
- `POST /auth/password/reset/link` body `{email, altcha|grant}`
- `GET /auth/password/reset/validate?token=`
- `POST /auth/password/reset/confirm` body `{token,password,altcha|grant}`

## ALTCHA

- `GET /captcha/config` → `{success,enabled,algorithm,cost}`
- `GET /captcha/challenge` → 官方 Challenge JSON（未启用 404）
- `POST /captcha/verify` body `{altcha}` → `{success,grant,expires_in:300}`

## 账号安全

- 改密：`PATCH /users/me` body `{password,current_password}`；成功吊销其他会话并签发新会话。
- 邮箱换绑：`/users/me/email-change/*` 两阶段。
- 注销：`POST /users/me/delete`。

## 错误

| 状态 | message | 场景 |
|---|---|---|
| 400 | `CAPTCHA_REQUIRED` | ALTCHA 未完成/无效 |
| 400 | `邮箱异样` | 黑名单命中 |
| 400 | `验证码错误或已过期` | 邮箱码无效 |
| 401 | `用户名或密码错误` | 登录失败 |
| 429 | `请求过于频繁` | 限流 |
