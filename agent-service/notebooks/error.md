# Docker 部署慢 —— 排查与纠错记录

> 项目：`/usr/local/robot`（FastAPI + uv + MySQL + Nginx）
> 记录时间：2026-11-19

---

## 一、一句话结论

**不是机器慢，也不是 Docker 慢。**

真实原因：构建流程被一个拉不动的外部镜像（`ghcr.io/astral-sh/uv`）整个堵死，
后面还有一个缺失的 `uv.lock` 挡着。两个问题叠加，表现为"部署特别慢"，
实际是"卡住 + 重试"。

**这件事分两个战场：**

1. **构建阶段**——被 `ghcr.io` 和一个缺失的锁文件堵住（第三、四、五节）
2. **运行阶段**——nginx 容器无限重启，根因是浮动 tag 指向了一个和老内核不兼容的镜像（第十一节）

两件事看起来都像"部署慢/部署失败"，但完全无关，需要分开处理。

---

## 二、关键数据对比

| 阶段 | 修复前 | 修复后 |
|---|---|---|
| 拉 `ghcr.io/astral-sh/uv` | **570 秒仍未完成**（19.6MB 只下到 8.39MB） | 不再拉取，0 秒 |
| `pip install uv` | — | **9.0 秒** |
| 整体构建 | 10 分钟以上，且最终失败 | 1 分钟以内，二次构建全命中缓存 |

从 570 秒到 9 秒，差的不是优化，是**换了一条路**。

---

## 三、错误一：`ghcr.io` 镜像拉不下来（元凶）

### 现象

```
[+] Building 571.5s (6/12)
=> [backend] FROM ghcr.io/astral-sh/uv@sha256:d3b601f0c7b118bc...   567.0s
=> => resolve ghcr.io/astral-sh/uv:latest@sha256:d3b601f0...        567.0s
=> => sha256:6194b0176b3040f6...  8.39MB / 19.60MB                  567.0s
```

一个 19.6MB 的层，9 分半只下到 8.39MB，约 **15 KB/s**。

### 判断依据

`resolve` 这一步就吃满了 567 秒——连 manifest 都解析不下来。
这不是带宽问题，是 **TCP/TLS 层在建连阶段反复超时重试**。

同一份日志里 `python:3.12-slim` 的元数据是 `0.0s`，因为本地早有缓存。
所以不是"Docker 整体慢"，是**某一个特定 registry 不通**。

### 根本原因

`ghcr.io`（GitHub Container Registry）在国内访问极不稳定，重试无意义。

### 解法

不要用 `COPY --from=外部镜像` 的方式引入 uv，改成用 pip 装：

```dockerfile
# 原来（卡 10 分钟）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 改成（9 秒）
RUN pip install --no-cache-dir uv
```

走 PyPI 清华源，完全绕开 ghcr.io。

### 附带结论

`daemon.json` 里的 `registry-mirrors` **只管 Docker Hub，管不到 ghcr.io**。
所以这类问题没法靠"配个加速器"解决，必须在 Dockerfile 层面换掉依赖来源。

---

## 四、错误二：`uv.lock` 不存在

### 现象

```
failed to compute cache key: ... "/uv.lock": not found
```

### 原因

Dockerfile 里写了 `COPY pyproject.toml uv.lock ./`，但项目里只有 `pyproject.toml`。
**COPY 指令里只要有一个源文件缺失，整条指令就失败**，后面的 RUN 根本不会执行。

### 解法

在 `backend/` 目录下生成锁文件。服务器上没有 uv，用容器生成最干净：

```bash
cd /usr/local/robot/backend
docker run --rm -v "$PWD":/w -w /w python:3.12-slim \
  sh -c "pip install -q uv -i https://pypi.tuna.tsinghua.edu.cn/simple && uv lock && ls -lh uv.lock"
```

> CentOS 的 SELinux 如果拦权限，把 `-v "$PWD":/w` 改成 `-v "$PWD":/w:z`。

**注意位置**：`uv.lock` 必须放在 `backend/` 下，不是项目根目录。
因为 compose 里 `build: ./backend`，build context 是 `backend/`，
Dockerfile 里的 `COPY` 是相对 context 解析的。

### 临时绕过（不推荐长期用）

删掉 `uv.lock`，同时删掉两处 `--locked`。只删一处没用——
`--locked` 要求锁文件存在且最新，没有就报 `Unable to find lockfile`。
代价：每次构建重新解析依赖，版本可能漂移。

---

## 五、错误三：Dockerfile 本身的结构问题

原始版本：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY src/ ./src/
EXPOSE 8000
ENTRYPOINT ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

四处问题：

| 位置 | 问题 | 后果 |
|---|---|---|
| `COPY --from=ghcr.io/...` | 国内拉不动 | 卡 570 秒 |
| `COPY pyproject.toml ./` | 漏了 `uv.lock` | 每次重新解析依赖，版本漂移，且慢 |
| `RUN uv sync --no-dev` | 此时 `src/` 还没拷进去 | 若是 package 项目会构建失败；且改代码就全量重装 |
| `ENTRYPOINT ["uv", "run", ...]` | 启动时自动检查并同步环境 | 容器起来会卡一下，断网直接起不来 |

---

## 六、最终可用版本

```dockerfile
FROM python:3.12-slim

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 装 uv：走 pip，彻底不碰 ghcr.io
RUN pip install --no-cache-dir uv

# 依赖层：只认锁文件，改代码不触发重装
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# 代码层
COPY src/ ./src/

EXPOSE 8000
ENTRYPOINT ["uv", "run", "--no-sync", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 三个关键设计

**1. 依赖层与代码层分离**

`COPY pyproject.toml uv.lock` 在 `COPY src/` 之前。
只要依赖没变，改任何业务代码都不会触发重装，直接命中缓存。

**2. `UV_PYTHON_DOWNLOADS=never`**

uv 默认会自动去 GitHub 下载 Python 解释器（`python-build-standalone`）。
只要 `requires-python` 和镜像版本有一点对不上，它就静默开始下载——
**又是一条通不过的路**，而且日志里表现为莫名卡住。
本项目 `requires-python = ">=3.10"`，镜像是 3.12，满足，所以禁用下载没有副作用。

**3. `--no-sync`**

`uv run` 默认在启动时检查环境是否需要同步，可能联网。
加 `--no-sync` 让容器启动不再做这件事，避免冷启动卡顿和无网失败。

### 关于 ENV 的清理

`pyproject.toml` 里已经配了索引：

```toml
[[tool.uv.index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

所以 Dockerfile 里**不需要**再设 `UV_DEFAULT_INDEX` / `UV_INDEX_URL`，
重复设置会让 uv 报"默认索引被指定了两次"。
只保留 `PIP_INDEX_URL`（这是给 `pip install uv` 用的，两回事）。

---

## 七、配置核查（docker-compose.yml）

构建通过后能不能跑起来，取决于这几个连通性点。逐项核对结果：

| 检查项 | 结果 |
|---|---|
| `MYSQL_HOST=mysql` | 正确，指向服务名而非 `localhost`（`localhost` 是最常见的坑） |
| `proxy_pass http://backend:8000` | 正确，同样是服务名 |
| `env_file: .env.prod` 的 9 个变量 | 与 `config.py` 里 `os.getenv` 的键名逐字对应 |
| `frontend/nginx.conf`、`frontend/public/` | 挂载源都存在（缺任意一个，Docker 会建空目录挂进去，nginx 起不来） |
| `load_dotenv()` 在容器内找不到 `.env` | 无影响，变量由 `env_file` 注入 |

另外 `proxy_buffering off` + `proxy_read_timeout 300s` 是给 SSE 流式输出配的，正确。

---

## 八、下次遇到"部署慢"的排查顺序

不要一上来就猜机器性能或网络。按这个顺序走：

**第 1 步：让耗时显形**

```bash
DOCKER_BUILDKIT=1 docker build --progress=plain -t 镜像名 . 2>&1 | tee build.log
```

默认输出会把耗时藏起来。加上 `--progress=plain` 才能看到每步的 `DONE 12.3s` 或 `CACHED`。

**第 2 步：看是"某一步慢"还是"整体慢"**

- 某一步几百秒不动 → 外部依赖（registry、软件源、DNS）
- 每步都慢但都在动 → 真的受限于磁盘 IO 或网络带宽
- 本该 `CACHED` 的步骤在重跑 → 缓存被打穿，COPY 顺序有问题

**第 3 步：看是哪个域名**

日志里的 `resolve` / `metadata` 行会带出 registry 地址。
`ghcr.io`、`registry.k8s.io`、`quay.io` 在国内基本都要绕。
`docker.io` 可以靠 `registry-mirrors` 加速，其他 registry 不行。

**第 4 步：确认容器内的包管理器源**

`pip` / `npm` / `apt` / `maven` 在容器里默认全走境外。
这一项单独就能差出 10 倍，而且很容易被漏掉——因为它发生在 `RUN` 里面，
不在 Docker 的网络层。

**第 5 步：查 context 大小**

```
=> => transferring context: 47.86kB
```

这个数字如果到几百 MB，说明 `.dockerignore` 没写，`node_modules` / `.venv` / `.git` 全被传进去了。

---

## 九、遗留风险（还没发生但会发生的）

**1. `mysql:8.0` 约 170MB，走 Docker Hub**

这是下一个最可能卡住的地方。建议单独先拉，观察速度：

```bash
docker pull mysql:8.0
```

如果低于 1 MB/s，先去阿里云容器镜像服务拿专属加速地址写进 `daemon.json`，
`systemctl restart docker` 后再拉。这一步做与不做，差的是半小时和两分钟。

**2. `mysql_data` 卷的密码固化问题**

MySQL 官方镜像只在**数据目录为空时**读取 `MYSQL_ROOT_PASSWORD`。
如果这个卷以前用别的密码初始化过，改 `.env.prod` 里的密码不会生效，
backend 会认证失败。真遇到就是 `docker compose down -v` 清卷重来（会丢数据）。

**3. `backend/` 里有 `.env` 和 `.env.prod`**

现在 `COPY src/` 只拷源码，密钥不会进镜像，这是对的。
但建议补 `.dockerignore`，防止以后有人改成 `COPY . .` 把密钥打进镜像：

```
.env
.env.*
__pycache__
*.pyc
```

---

## 十、一条可复用的经验

> **"慢"和"卡"是两种完全不同的故障，但对用户来说长得一样。**

判断方法：看进度条。

- 数字在涨、速度很低（十几 KB/s）→ 网络带宽或线路质量问题
- 小时钟在转、数字不动 → 连接建不起来，在反复重试，重试多少次都不会成功

今晚这个案例里，`19.60MB` 只下到 `8.39MB` 却耗了 `567` 秒，
而且 `resolve` 阶段就占满全部时间——**属于后者**。
这种情况下"多试几次"和"换个时间再部署"都是无效的，必须换源或换方案。

---

## 十一、第二个战场：nginx 反复重启（Restarting）

构建修好之后，backend 和 mysql 都正常 `Up`，只有 frontend 一直在
`Restarting (1)` 里循环——退出码 1，起来就死。

### 错误

```
nginx: [crit] 1#1: open() "/run/nginx.pid" failed (1: Operation not permitted)
```

### 一条重要的错误码区分

| 错误码 | 含义 | 说明 |
|---|---|---|
| `EACCES` (13) `Permission denied` | 文件权限不足 | 身份或权限位的问题 |
| `EPERM` (1) `Operation not permitted` | **内核安全策略拒绝** | 权限位是对的、身份也是 root，但更高层在拦 |

看到 `EPERM` 就不要往 `chmod` / `chown` 方向查了，方向是错的。

### 排除过程（每一步都排掉了一种可能）

| 验证 | 结果 | 排除了 |
|---|---|---|
| `ls -la frontend/` | `nginx.conf` 是 571 字节普通文件 | 挂载缺失（Docker 把它建成目录） |
| `docker inspect ... Readonly=false User=[] Tmpfs=null SecOpt=null` | 全部正常 | 只读 rootfs、降权、自定义安全选项 |
| `compose run --entrypoint sh frontend -c "touch /run/test"` | `WRITE_OK` | 文件系统不可写 |
| `tmpfs: - /run` | 多撑了一会，仍然挂 | 单纯 pid 路径问题 |

**关键困惑**：root 用户、可写目录、无任何安全选项，为什么 `sh` 能写而 `nginx` 不能？

### 真正的原因：浮动的镜像 tag

`nginx:alpine` 是**浮动 tag**，同一个名字每天指向不同镜像。

```
本次拉到的：  nginx 1.31.9，Alpine，gcc 15.2.0（2026 年的新镜像）
内核版本：    3.10.0-1160.el7.x86_64（CentOS 7，2020 年 EOL）
```

新版 Alpine 的 musl 会调用上游内核才有的系统调用（如 `clone3`，5.3 才引入），
在 3.10 这种老内核上只能靠 fallback 勉强存活。写 pid 文件是它第一个撞墙的地方——
`tmpfs` 绕过了这一处，后面还有 `/var/cache/nginx/client_temp` 之类的目录在等着。

**老师那边能跑，不是配置更好，是他几周前拉的是更老的 nginx 版本。**

### 解法

```yaml
  frontend:
    image: nginx:1.27-alpine    # 原来是 nginx:alpine
```

```bash
docker compose down && docker compose up -d
```

改完立刻 `Up`，问题消失。

### 三条经验

**1. 浮动 tag 等于不可复现**

`latest`、`alpine`、`slim`、`8.0` 这类 tag 会随时指向新镜像。
同一个 compose 文件，两个人跑出两种结果，往往就是这个原因。
生产环境应钉死到具体版本号。

**2. "同样的代码别人能跑我不能" → 先怀疑版本，再怀疑配置**

代码、配置、挂载都一样的时候，剩下的变量只有镜像版本和宿主环境。
先去比对 `docker images` 的创建时间和镜像 ID，比逐行读 compose 快得多。

**3. 排查顺序应该是"从外到内"**

先确认现象（`docker compose ps`），再看日志（`docker logs --tail=60`），
再做对照实验（手动 `docker run` 同一个镜像），最后才动配置。
本次真正的转折点是发现 `compose run` 的容器能写而 `up` 的不能——
这个矛盾把方向从"文件权限"推到了"进程与镜像"。

---

## 十二、最终状态

| 服务 | 状态 |
|---|---|
| chatbot-backend | Up，`uv run --no-sync uvicorn`，8000 端口 |
| chatbot-mysql | Up (healthy)，mysql:8.0 |
| chatbot-frontend | Up，nginx:1.27-alpine，80 端口 |

从"构建 10 分钟卡死"到"三个容器稳定运行"，一共改了三处：

1. Dockerfile：`ghcr.io` 镜像 → `pip install uv`
2. `backend/uv.lock`：补上锁文件
3. compose：`nginx:alpine` → `nginx:1.27-alpine`

### 建议顺手做的事

`backend` 的基础镜像 `python:3.12-slim` 也是浮动 tag。虽然 `3.12` 只更新补丁、
不会跳大版本，但如果想彻底可复现，可以钉死到具体版本：

```dockerfile
FROM python:3.12.7-slim    # 具体小版本，而不是 python:3.12-slim
```

`mysql:8.0` 同理，可以写成 `mysql:8.0.40` 这类完整版本号。

---

## 十三、容器 healthy 但外部端口全部 timeout（2026-11-20）

> 项目：Day03 环境准备（安心保）—— milvus / postgres / minio / etcd / attu
> 环境：Windows + VMware / CentOS 7 虚拟机 `heima` (192.168.150.101) / Docker Compose

### 一句话结论

**不是 PostgreSQL 的问题，也不是 Docker 没启动。**

真实原因：`systemctl stop firewalld` 把 Docker 写进 filter 表的放行规则连带清掉了。
nat 表的 DNAT 规则还在，包被改写目标地址后进入 `FORWARD`，撞上默认策略 `-P FORWARD DROP`，被静默丢弃。

**破案的唯一线索是：22 端口通，所有 Docker 发布的端口不通。**

### 症状（极具迷惑性）

```
hm-postgres   postgres:16   Up 13 minutes (healthy)   0.0.0.0:5432->5432/tcp
hm-milvus     milvus:v3.0.0 Up (healthy)              9091, 19530
hm-minio      minio         Up (healthy)              9000-9001
```

```bash
ss -lntp | grep 5432
LISTEN  *:5432      users:(("docker-proxy",pid=58436,fd=4))
LISTEN  [::]:5432   users:(("docker-proxy",pid=58448,fd=4))
```

容器 healthy、端口映射存在、`docker-proxy` 在监听、`ss` 显示正常——
**这四样全都对，但 DBeaver 连 192.168.150.101:5432 就是 timeout。**

### 判断依据：三层测试把范围压到唯一位置

| 层 | 测试 | 结果 | 排除 / 指向 |
|---|---|---|---|
| 连通性 | `ping 192.168.150.101` | 通，TTL=64，<1ms | 网络物理层没问题 |
| TCP | `Test-NetConnection ... -Port 5432` | `PingSucceeded: True` / `TcpTestSucceeded: False` | **ICMP 能过、TCP 不能过 → 转发层** |
| 服务 | `docker exec hm-postgres pg_isready` | `accepting connections` | PG 进程正常 |
| 监听 | `ss -lntp \| grep 5432` | `*:5432 LISTEN` | 不是绑定问题 |
| 防火墙 | `systemctl is-active firewalld` | `inactive` / `disabled` | **看起来排除了，实际是陷阱入口** |
| 入站规则 | `iptables -S INPUT` | `-P INPUT ACCEPT`，无任何规则 | INPUT 是干净的 |
| 本机自连 | `/dev/tcp/192.168.150.101/5432` | **OK** | Docker 整条链正常，问题在「从外部进来之后」 |
| 端口对比 | Windows 测 22 / 5432 / 3000 / 9000 / 19530 / 9091 | **22 OPEN，其余全 TIMEOUT** | **所有 Docker 端口都不通，非 Docker 端口通** |

最后一行是决定性的：

```
port 22    -> OPEN       ← sshd，宿主机原生进程，走 INPUT
port 5432  -> TIMEOUT    ← docker 发布，走 PREROUTING DNAT + FORWARD
port 3000  -> TIMEOUT    ← attu
port 9000  -> TIMEOUT    ← minio
port 19530 -> TIMEOUT    ← milvus
port 9091  -> TIMEOUT    ← milvus metrics
```

### 根因：数据包实际走的路径

Docker 发布端口时做两件事：

1. **nat 表** `DOCKER` 链写 DNAT：`0.0.0.0:5432 → 172.21.0.4:5432`
2. **filter 表** `DOCKER` 链写放行规则，让 DNAT 之后的包能通过 `FORWARD`

`systemctl stop firewalld` 把第 2 步的规则清掉了，第 1 步的 DNAT 留着。于是：

```
外部 SYN 到达 ens33:5432
       ↓
PREROUTING 命中 DNAT  →  目标改写为 172.21.0.4:5432
       ↓
进入 FORWARD 链
       ↓
DOCKER 链里没有对应的 ACCEPT
       ↓
落到默认策略 -P FORWARD DROP
       ↓
包被静默丢弃  →  客户端表现为 timeout（不是 refused）
```

当时 `iptables -S FORWARD` 的输出印证了这一点：

```
-P FORWARD DROP                                        ← 关键
-A FORWARD -j DOCKER-USER
-A FORWARD -j DOCKER-ISOLATION-STAGE-1
-A FORWARD -o br-549ea2cc284d -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A FORWARD -o br-549ea2cc284d -j DOCKER                 ← 跳过去，但 DOCKER 链里没有放行
```

### 三个「为什么」（最容易想不通的地方）

**问：虚拟机自己连 `192.168.150.101:5432` 为什么通？**

环回流量走 `lo`，不经过 `FORWARD`，也不被 DNAT 改写。所以「本机自测一切正常」是个假象。

**问：22 端口为什么通？**

sshd 是宿主机原生进程，绑定在本机协议栈上。包走 `INPUT` 链（`-P INPUT ACCEPT`），根本不经 DNAT 和 `FORWARD`。

**问：`docker-proxy` 明明在监听，为什么没起作用？**

DNAT 在 `PREROUTING` 阶段就把包截走改写了目标地址，`docker-proxy` 这个用户态代理根本没机会处理这些连接。它在监听是真的，只是接不到活。

**这件事说明：`INPUT ACCEPT` 只能证明「本机进程能收到包」，不能证明「流量通路是通的」。**
容器流量的数据面在 `FORWARD`，第 4 条经验值得单独记住。

### 解法

**临时（本次实际用的）**：重启 VMware，连带重启虚拟机，Docker 服务随之重启并重建 iptables 规则。

**推荐（快得多，不用重启虚拟机）**：

```bash
systemctl restart docker
sleep 8
docker ps
```

验证：

```powershell
Test-NetConnection 192.168.150.101 -Port 5432
# TcpTestSucceeded: True
```

六个端口全部恢复 OPEN。

**应急绕过（不修也能干活）**：22 端口在整个过程中一直是通的，SSH 隧道可以直接绕开断掉的 `FORWARD`：

```bash
ssh -L 5432:127.0.0.1:5432 root@192.168.150.101 -N
```

本地客户端连 `127.0.0.1:5432` 即可。DBeaver 也内置了这个功能（连接设置 → SSH 标签页 → 使用 SSH 隧道）。

### 以后放行端口用这条，不要停火墙

```bash
firewall-cmd --permanent --add-port=5432/tcp && firewall-cmd --reload
```

CentOS 7 上 firewalld 和 Docker 共用 iptables，**停火墙是把自己坑了的经典操作**：PORT 映射看着全对，实际一条都进不来。

### 四条经验

**1. timeout 和 refused 是两个方向**

`refused` = 端口没人接（服务没起、绑错地址）；`timeout` = 包被丢了（防火墙 DROP、路由不通、转发链断了）。看到 timeout 就别再查「服务起没起」了。

**2. 容器 healthy ≠ 端口对外可达**

`healthy` 只说明容器内服务活着；`docker ps` 的端口映射只说明「配置层面声明了」；`ss` 的 LISTEN 只说明「有人在这个端口上等」。这三者都属于配置层面，`FORWARD` 链才是数据面。

**3. 「ping 通 + 端口超时」直接往转发/防火墙想**

ICMP 和 TCP 走不同的过滤路径，能 ping 通只证明链路层没断。这个组合几乎排除了网络不通、IP 填错、服务没起所有选项。

**4. 找一个「能通的同类」做对比，比逐项检查快十倍**

本次真正的转折点是拿 22 端口做了对照：非 Docker 端口通、Docker 端口全不通 →
范围瞬间收缩到「Docker 特有的那条路径」，也就是 DNAT + FORWARD。

