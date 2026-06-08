# Veridrop 开发环境启动说明

本文档用于本地开发启动。当前项目默认使用 MongoDB 持久化检测报告，真实配置文件 `mongodb_config.yaml` 已加入 `.gitignore`，请从示例文件复制生成。

## 1. 准备配置

复制 MongoDB 配置示例：

```powershell
Copy-Item mongodb_config.example.yaml mongodb_config.yaml
```

默认本机开发配置为：

```yaml
mongodb:
  connection_string: "mongodb://localhost:27018/"
  database_name: "WcVeridrop"
```

首次启动时，如果 MongoDB 的 `admins` 集合为空，会使用配置中的 `admin.initial_username` 和 `admin.initial_password` 创建管理员账号。生产环境不要使用示例密码。

## 2. 方式一：Docker Compose 启动全栈

这是最简单的开发启动方式，会同时启动 Web 服务和 MongoDB：

```powershell
docker compose up -d --build
```

访问：

```text
http://localhost:8000
http://localhost:8000/login
```

默认启用登录保护。未登录访问 `http://localhost:8000` 会自动跳转到登录页。

查看日志：

```powershell
docker compose logs -f app
```

停止服务：

```powershell
docker compose down
```

如果要同时删除 MongoDB 数据卷：

```powershell
docker compose down -v
```

## 3. 方式二：本机 venv 启动应用

先启动 MongoDB。可以用 Docker 单独启动 MongoDB：

```powershell
docker run -d --name veridrop-mongo `
  -p 27018:27017 `
  -v veridrop_mongo:/data/db `
  mongo:7
```

安装依赖：

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[web]"
```

本地开发默认不需要设置环境变量。服务会自动读取项目根目录的 `mongodb_config.yaml`，并使用开发环境默认 Session 密钥。

启动 Web 服务：

```powershell
.\venv\Scripts\python.exe -m uvicorn web.server:app --host 127.0.0.1 --port 8000 --workers 1
```

如果 `8000` 被占用，换一个端口：

```powershell
.\venv\Scripts\python.exe -m uvicorn web.server:app --host 127.0.0.1 --port 8001 --workers 1
```

## 4. 常用检查命令

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/healthz -UseBasicParsing
```

运行测试：

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

仅检查 Docker Compose 配置：

```powershell
docker compose config
```

## 5. 关键环境变量

| 变量 | 说明 |
| --- | --- |
| `VERIDROP_MONGODB_CONFIG` | MongoDB YAML 配置文件路径，默认 `mongodb_config.yaml` |
| `VERIDROP_MONGODB_URI` | 覆盖 YAML 中的 MongoDB 连接字符串 |
| `VERIDROP_MONGODB_DATABASE` | 覆盖 YAML 中的数据库名 |
| `VERIDROP_SESSION_SECRET` | Session 签名密钥，生产环境必须设置强随机值 |
| `VERIDROP_ADMIN_USERNAME` | 首次初始化管理员用户名 |
| `VERIDROP_ADMIN_PASSWORD` | 首次初始化管理员密码 |
| `VERIDROP_IMAGE_CACHE_DIR` | JPG 报告图片缓存目录 |
| `VERIDROP_REQUIRE_LOGIN` | 是否启用登录保护，默认 `1`；可信内网纯 API 场景可设为 `0` |

本地开发通常不需要设置这些变量；它们主要用于 Docker Compose、生产部署或临时覆盖本地配置。

## 6. 登录说明

默认登录页：

```text
http://localhost:8000/login
```

首页、检测页面和报告页面默认都需要登录。`/api/*` 默认需要管理员登录 Session 或系统 API Token；未认证访问 API 会返回 `401`。

外部程序调用模型检测接口时，先登录 `/admin`，在“系统 API Token”区域点击创建或重置。明文 token 只显示一次，请立即保存。调用 API 时携带：

```http
Authorization: Bearer <token>
```

管理员账号只会在 `admins` 集合为空时初始化一次。后续修改 `mongodb_config.yaml` 里的初始账号密码，不会覆盖数据库中已经存在的管理员账号。
