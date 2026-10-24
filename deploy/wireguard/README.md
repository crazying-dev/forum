# WireGuard 互联（Host A ↔ Host B）

> 生产为两台独立公网机：Host A = ouo + SeaweedFS，Host B = admin。
> 通过 WireGuard 组成点对点内网 `10.8.0.0/24`，S3（8333）与指标（9327）**只**在该内网提供。

## 1. 地址与端口规划

| 项 | Host A | Host B |
|---|---|---|
| 角色 | 论坛本体 + SeaweedFS | 管理后台 |
| wg0 地址 | `10.8.0.1/24` | `10.8.0.2/24` |
| WireGuard 监听 | `51820/udp` | `51820/udp` |
| 需要互访 | 被 B 访问 `8333`、`9327` | 被 A 访问 `8080`（历史 `/guild-img`、`/guide-img` 反代，已退役，可不再放行） |
| 公网开放 | 仅 `51820/udp`、`80/tcp`、`443/tcp` | 仅 `51820/udp`、`80/tcp`、`443/tcp` |

> `AllowedIPs` 一律用 `/32` 精确到对端地址，**不要**用 `0.0.0.0/0`（避免把默认路由劫持进隧道）。
> 纯点对点，不需要 `net.ipv4.ip_forward=1`。

## 2. 安装

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y wireguard wireguard-tools
# RHEL 系（先启用 EPEL / CRB）
sudo dnf install -y wireguard-tools
```

## 3. 生成密钥（两台分别执行）

```bash
umask 077
wg genkey | sudo tee /etc/wireguard/private.key >/dev/null
sudo cat /etc/wireguard/private.key | wg pubkey | sudo tee /etc/wireguard/public.key
sudo chmod 600 /etc/wireguard/private.key
sudo cat /etc/wireguard/public.key          # 把公钥填到对端配置
sudo shred -u /etc/wireguard/private.key.bak 2>/dev/null || true
```

- Host A 的私钥 → `wg0-host-a.conf.example` 的 `<HOST_A_PRIVATE_KEY>`；
- Host B 的私钥 → `wg0-host-b.conf.example` 的 `<HOST_B_PRIVATE_KEY>`；
- 两边互填对方公钥；`<HOST_B_PUBLIC_IP>` 为 Host B 的公网 IP/域名（如果 Host B 也在 NAT 后，可由 A 作为服务端只配公钥、由 B 主动连 A）。

## 4. 配置与启动

```bash
# 两台都把对应示例复制为 /etc/wireguard/wg0.conf（替换 <> 占位）
sudo install -m 0600 wg0-host-a.conf.example /etc/wireguard/wg0.conf   # 在 Host A
sudo install -m 0600 wg0-host-b.conf.example /etc/wireguard/wg0.conf   # 在 Host B

sudo systemctl enable --now wg-quick@wg0
sudo systemctl status wg-quick@wg0 --no-pager
sudo wg show
```

> `seaweedfs.service` 声明了 `Requires=wg-quick@wg0.service`，所以 Host A 必须先有可用的 `wg0`，否则 SeaweedFS 不会被启动。

## 5. 防火墙（两种写法择一）

### 5.1 nftables

Host A：

```nft
# /etc/nftables.conf（先备份原文件；不要直接照抄覆盖其他表）
table inet yj {
    chain input {
        type filter hook input priority filter; policy drop;
        ct state established,related accept
        iif lo accept

        # 公网只开 SSH / HTTP / HTTPS / WireGuard
        tcp dport { 22, 80, 443 } accept
        udp dport 51820 accept
        icmp type echo-request accept

        # 只允许 Host B 经 wg0 访问 S3 与指标
        iifname "wg0" ip saddr 10.8.0.2 tcp dport { 8333, 9327 } accept

        # 显式忽略公网 S3/指标（policy drop 已覆盖，写出来便于审计）
        tcp dport { 8333, 9327 } drop
    }
}
```

Host B：

```nft
table inet yj {
    chain input {
        type filter hook input priority filter; policy drop;
        ct state established,related accept
        iif lo accept

        tcp dport { 22, 80, 443 } accept
        udp dport 51820 accept
        icmp type echo-request accept

        # 历史：只允许 Host A 经 wg0 访问 admin 后端（/guild-img、/guide-img 反代，已退役）
        # 若 admin 后台不需要 Host A 直连，可删除本行与下一行
        iifname "wg0" ip saddr 10.8.0.1 tcp dport 8080 accept
        tcp dport 8080 drop
    }
}
```

```bash
sudo nft -f /etc/nftables.conf
sudo nft list ruleset | head -50
sudo systemctl enable nftables
```

### 5.2 ufw

Host A：

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80,443/tcp
sudo ufw allow 51820/udp
sudo ufw allow in on wg0 to 10.8.0.1 port 8333 proto tcp
sudo ufw allow in on wg0 to 10.8.0.1 port 9327 proto tcp
sudo ufw deny 8333/tcp
sudo ufw deny 9327/tcp
sudo ufw enable
sudo ufw status verbose
```

Host B：

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80,443/tcp
sudo ufw allow 51820/udp
sudo ufw allow in on wg0 from 10.8.0.1 to 10.8.0.2 port 8080 proto tcp
sudo ufw deny 8080/tcp
sudo ufw enable
sudo ufw status verbose
```

> 规则顺序重要：先放行 `in on wg0`，再 `deny` 公网端口。云厂商安全组需同步：只放行 `51820/udp` 与 `80/443`，**不要**放行 `8333/9327/8080`。

## 6. 验证

```bash
# 两台分别看握手
sudo wg show
# Host A → Host B
ping -c 3 10.8.0.2
# Host B → Host A 的 S3（403/200 说明可达）
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.1:8333/
# Host A → Host B 的 admin 后端
curl -s -o /dev/null -w '%{http_code}\n' http://10.8.0.2:8080/ping
```

预期：`wg show` 有 `latest handshake`（几秒内）；ping 通；S3 返回 403/200；`/ping` 返回 200。

## 7. 排障

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `wg show` 无 handshake | 公网 UDP 51820 未放行 / Endpoint 错 / 对端未启动 | 云安全组 + 防火墙双向放行；`wg show` 看 transfer 是否为 0 |
| handshake 有、ping 不通 | 地址掩码不对 / 防火墙拦 icmp | `ip addr show wg0` 应为 `/24`；临时 `ufw allow in on wg0` 验证 |
| A 访问 B:8080 不通 | admin 只监听了 127.0.0.1 / 防火墙未放行 wg0 | admin 需监听 `0.0.0.0:8080`（或 `10.8.0.2:8080`）+ 防火墙仅对 wg0 放行 |
| B 访问 A:8333 不通 | seaweedfs 未启动 / 未绑 10.8.0.1 | `ss -ltnp \| grep 8333` 应为 `10.8.0.1:8333` |
| 频繁断连 | NAT 超时 | 两端保留 `PersistentKeepalive = 25` |
| MTU 导致的奇怪超时 | 隧道 MTU 偏大 | 在 `[Interface]` 设 `MTU = 1420`（默认通常也可） |

## 8. 安全注意

- 私钥只存在于各自 `/etc/wireguard/private.key` 或 `wg0.conf`（0600，root），不进 Git；
- 本目录的 `.example` 不含任何真实密钥；
- `AllowedIPs` 只用 `/32`，不转发、不做出口网关；
- 公网端口仅 `51820/udp` + `80/443`（+ SSH）；S3/指标/8080 一律只走 wg0。
