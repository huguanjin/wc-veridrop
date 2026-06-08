# Veridrop HTTP API 接口文档

本文档面向需要在其他项目中调用 Veridrop 检测能力的后端服务。Veridrop 的 Web 服务基于 FastAPI，检测任务采用异步提交、轮询状态、获取报告的调用模式。

## 基本信息

- 默认服务入口: `http://localhost:8000`
- 请求格式: `multipart/form-data`
- 返回格式: `application/json`
- 检测结果格式: JSON 报告、HTML 报告页、JPG 报告图
- 健康检查: `GET /healthz`

生产部署时建议通过反向代理或 API 网关暴露服务，并在网关层增加鉴权、限流和访问控制。

## 调用流程

1. 调用对应协议的检测接口提交任务。
2. 服务返回 `job_id` 和 `status_url`。
3. 调用 `GET /api/status/{job_id}` 轮询任务状态。
4. 当状态为 `done` 时，读取 `json_url` 获取结构化检测报告。
5. 如需展示给用户，也可以使用 `result_url` 或 `image_url`。

## 协议与接口

| 协议 | 提交接口 | 典型模型 |
| --- | --- | --- |
| Claude / Anthropic | `POST /api/detect/claude` | `claude-haiku-4-5` |
| OpenAI Chat Completions | `POST /api/detect/openai` | `gpt-4o-mini` |
| Gemini OpenAI 兼容协议 | `POST /api/detect/gemini` | `gemini-2.5-flash` |

兼容入口 `POST /api/detect` 仍然存在，但推荐新集成直接使用明确协议的接口。

## 提交检测任务

### `POST /api/detect/claude`

提交 Claude / Anthropic 协议检测任务。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `base_url` | string | 是 | 无 | 中转站 API 根地址，必须以 `http://` 或 `https://` 开头 |
| `api_key` | string | 是 | 无 | 用于访问中转站的 API key，长度至少 8 位 |
| `model` | string | 是 | 无 | 要检测的模型名称 |
| `mode` | string | 否 | `full` | 检测模式: `quick`、`standard`、`full` |
| `include_long_context` | boolean | 否 | `false` | 是否启用标准长上下文检测 |
| `include_long_context_extreme` | boolean | 否 | `false` | 是否启用极限长上下文检测 |
| `force` | boolean | 否 | `false` | 跳过提交前模型可用性预检 |

#### 示例

```bash
curl -X POST http://localhost:8000/api/detect/claude \
  -F "base_url=https://relay.example.com" \
  -F "api_key=sk-xxx" \
  -F "model=claude-haiku-4-5" \
  -F "mode=full"
```

### `POST /api/detect/openai`

提交 OpenAI Chat Completions 协议检测任务。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `base_url` | string | 是 | 无 | 中转站 API 根地址，通常是 `/v1` 根地址 |
| `api_key` | string | 是 | 无 | 用于访问中转站的 API key |
| `model` | string | 是 | 无 | 要检测的模型名称 |
| `mode` | string | 否 | `standard` | 检测模式: `quick`、`standard`、`full` |
| `include_long_context` | boolean | 否 | `false` | 是否启用标准长上下文检测 |
| `include_long_context_extreme` | boolean | 否 | `false` | 是否启用极限长上下文检测 |
| `force` | boolean | 否 | `false` | 跳过提交前模型可用性预检 |

#### 示例

```bash
curl -X POST http://localhost:8000/api/detect/openai \
  -F "base_url=https://relay.example.com/v1" \
  -F "api_key=sk-xxx" \
  -F "model=gpt-4o-mini" \
  -F "mode=standard"
```

### `POST /api/detect/gemini`

提交 Gemini OpenAI 兼容协议检测任务。

#### 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `base_url` | string | 是 | 无 | Gemini OpenAI 兼容 API 根地址 |
| `api_key` | string | 是 | 无 | 用于访问中转站的 API key |
| `model` | string | 是 | 无 | 要检测的模型名称 |
| `mode` | string | 否 | `standard` | 检测模式: `quick`、`standard`、`full` |
| `force` | boolean | 否 | `false` | 跳过提交前模型可用性预检 |

#### 示例

```bash
curl -X POST http://localhost:8000/api/detect/gemini \
  -F "base_url=https://relay.example.com/v1beta/openai" \
  -F "api_key=sk-xxx" \
  -F "model=gemini-2.5-flash" \
  -F "mode=standard"
```

## 提交成功响应

所有检测提交接口成功后返回同一种结构。

```json
{
  "job_id": "abc123xx",
  "status_url": "/api/status/abc123xx"
}
```

字段说明:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_id` | string | 检测任务 ID |
| `status_url` | string | 任务状态轮询地址 |

注意: 服务不会在响应中回显 `api_key`。

## 查询任务状态

### `GET /api/status/{job_id}`

查询检测任务的执行状态。

#### 示例

```bash
curl http://localhost:8000/api/status/abc123xx
```

#### 排队或运行中

```json
{
  "job_id": "abc123xx",
  "protocol": "openai",
  "status": "running",
  "base_url": "https://relay.example.com/v1",
  "target_model": "gpt-4o-mini",
  "mode": "standard",
  "created_at": 1780900000.0,
  "started_at": 1780900001.0,
  "finished_at": null
}
```

#### 已完成

```json
{
  "job_id": "abc123xx",
  "protocol": "openai",
  "status": "done",
  "base_url": "https://relay.example.com/v1",
  "target_model": "gpt-4o-mini",
  "mode": "standard",
  "created_at": 1780900000.0,
  "started_at": 1780900001.0,
  "finished_at": 1780900042.0,
  "result_url": "/r/abc123xx",
  "image_url": "/r/abc123xx.jpg",
  "json_url": "/api/result/abc123xx.json"
}
```

#### 执行失败

```json
{
  "job_id": "abc123xx",
  "protocol": "openai",
  "status": "error",
  "base_url": "https://relay.example.com/v1",
  "target_model": "gpt-4o-mini",
  "mode": "standard",
  "created_at": 1780900000.0,
  "started_at": 1780900001.0,
  "finished_at": 1780900008.0,
  "error": "RuntimeError: upstream error"
}
```

状态枚举:

| 状态 | 说明 |
| --- | --- |
| `queued` | 已入队，等待执行 |
| `running` | 正在执行检测 |
| `done` | 检测完成 |
| `error` | 检测执行异常 |

## 获取 JSON 报告

### `GET /api/result/{job_id}.json`

获取结构化检测报告。建议其他系统优先消费这个接口。

#### 示例

```bash
curl http://localhost:8000/api/result/abc123xx.json
```

#### 报告主要字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `protocol` | string | 检测协议: `anthropic`、`openai`、`gemini` |
| `tier` | string | 验证等级 |
| `tier_title` | string | 验证等级标题 |
| `tier_message` | string | 验证等级说明 |
| `base_url` | string | 被检测中转站地址 |
| `api_key_masked` | string | 脱敏后的 API key |
| `target_model` | string | 被检测模型 |
| `mode` | string | 检测模式 |
| `timestamp` | string | 报告生成时间 |
| `total_score` | number | 总分，0 到 100 |
| `verdict` | string | 结论: `passed`、`marginal`、`failed` |
| `summary` | string | 检测摘要 |
| `results` | array | 各检测项结果 |
| `performance` | object | 性能统计 |
| `run_error` | string/null | 致命执行错误 |
| `self_reported_identity` | string/null | 模型自报身份 |
| `detected_non_anthropic_brands` | array | Claude 检测中识别出的非 Anthropic 品牌痕迹 |

#### 单项检测结果结构

`results` 数组中的每个元素通常包含:

```json
{
  "name": "structured_output",
  "status": "pass",
  "score": 100.0,
  "summary": "ok",
  "details": {}
}
```

常见字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 检测项名称 |
| `status` | string | 检测状态: `pass`、`fail`、`skip`、`error` |
| `score` | number | 该项得分 |
| `summary` | string | 该项摘要 |
| `details` | object | 该项详细证据 |

## 获取 HTML 报告页

### `GET /r/{job_id}`

返回适合浏览器展示的 HTML 报告页。

```text
http://localhost:8000/r/abc123xx
```

如果任务仍在运行，该页面会返回运行中页面。

## 获取 JPG 报告图

### `GET /r/{job_id}.jpg`

返回报告 JPG 图片，适合分享到聊天工具、论坛或工单系统。

```text
http://localhost:8000/r/abc123xx.jpg
```

报告图首次请求时生成，之后会从磁盘缓存读取。

## 探测中转站模型列表

### `POST /api/probe`

该接口用于预先探测中转站的 `/models` 或 `/v1/models`，判断 API key 是否有效，并按协议归类模型。这个接口不是正式检测，只是提交前的辅助检查。

#### 请求参数

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `base_url` | string | 是 | 中转站 API 根地址 |
| `api_key` | string | 是 | 用于访问中转站的 API key |

#### 示例

```bash
curl -X POST http://localhost:8000/api/probe \
  -F "base_url=https://relay.example.com/v1" \
  -F "api_key=sk-xxx"
```

#### 响应示例

```json
{
  "ok": true,
  "auth_ok": true,
  "models_endpoint_supported": true,
  "raw_count": 12,
  "all_models": ["gpt-4o-mini", "claude-haiku-4-5", "gemini-2.5-flash"],
  "by_protocol": {
    "anthropic": ["claude-haiku-4-5"],
    "openai": ["gpt-4o-mini"],
    "gemini": ["gemini-2.5-flash"]
  },
  "best_by_protocol": {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash"
  },
  "status": 200,
  "error": null,
  "note": null
}
```

`/api/probe` 有独立的 IP 频率限制。触发限制时返回 `429`，并带有 `Retry-After` 响应头。

## 健康检查

### `GET /healthz`

用于负载均衡器、容器编排或监控系统探活。

#### 响应示例

```json
{
  "ok": true,
  "ts": 1780900000.0
}
```

## 错误响应

### 参数错误

```json
{
  "detail": "base_url must start with http(s)://"
}
```

常见状态码:

| 状态码 | 场景 |
| --- | --- |
| `400` | 参数格式错误，例如 `base_url`、`api_key`、`model` 或 `mode` 不合法 |
| `404` | 任务不存在，或报告尚未生成 |
| `422` | 提交前模型可用性预检失败 |
| `429` | `/api/probe` 调用过于频繁 |
| `500` | 服务内部异常 |

### 模型不可用

提交检测时，服务会默认发起一次轻量级模型可用性预检。如果中转站列出了模型但实际不可调用，会返回 `422`。

```json
{
  "detail": {
    "code": "model_not_alive",
    "message": "模型 gpt-4o-mini 在该中转站实际不可用。",
    "model": "gpt-4o-mini",
    "protocol": "openai",
    "upstream_error": "HTTP 404: model_not_found"
  }
}
```

如果调用方确认预检误判，可以在提交任务时增加:

```text
force=1
```

## 外部项目集成示例

下面示例展示一个后端服务如何提交 OpenAI 协议检测任务，并轮询获取 JSON 报告。

```js
async function submitDetection() {
  const fd = new FormData();
  fd.set("base_url", "https://relay.example.com/v1");
  fd.set("api_key", "sk-xxx");
  fd.set("model", "gpt-4o-mini");
  fd.set("mode", "standard");

  const submitResp = await fetch("http://localhost:8000/api/detect/openai", {
    method: "POST",
    body: fd
  });
  if (!submitResp.ok) {
    throw new Error(await submitResp.text());
  }

  const { job_id } = await submitResp.json();

  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 2000));

    const statusResp = await fetch(`http://localhost:8000/api/status/${job_id}`);
    const status = await statusResp.json();

    if (status.status === "error") {
      throw new Error(status.error || "detection failed");
    }

    if (status.status === "done") {
      const reportResp = await fetch(`http://localhost:8000${status.json_url}`);
      return await reportResp.json();
    }
  }
}
```

服务端集成建议设置总超时时间。普通检测通常几十秒完成；启用长上下文检测后可能需要数分钟。

## 检测模式

| 模式 | 说明 | 适用场景 |
| --- | --- | --- |
| `quick` | 快速核心检测 | 表单预检、低成本快速判断 |
| `standard` | 标准检测 | 默认推荐，覆盖主要能力和协议检查 |
| `full` | 完整检测 | 需要更完整报告或用于基线对比 |

长上下文检测为可选项，可能显著增加耗时和上游 token 成本。

## 部署与运行注意事项

### Uvicorn 启动

容器或服务器中可使用:

```bash
python -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --workers 1
```

### 工作进程数量

当前任务队列是进程内队列，完成后的报告会落盘。建议使用:

```text
--workers 1
```

如果使用多个 worker 或多个容器副本，提交任务和查询状态可能落到不同进程，导致运行中的任务无法被查询。需要水平扩展时，应先引入共享队列和共享状态存储。

### 持久化目录

报告默认写入:

```text
/opt/veridrop/web_data/jobs
```

可以通过环境变量覆盖:

```text
VERIDROP_JOBS_DIR=/app/web_data/jobs
```

Docker 部署时建议将该目录挂载为持久化 volume，否则容器重建后历史报告会丢失。

### API key 安全

检测任务中的原始 `api_key` 只在任务运行期间保存在内存中。报告落盘时只保存脱敏后的 `api_key_masked`。

但是报告 URL 是可分享链接，知道 `job_id` 的人可以访问对应报告。如果报告内容敏感，建议将服务部署在内网，或在反向代理层增加访问鉴权。

### 跨域调用

如果另一个项目的后端服务调用 Veridrop，不需要 CORS。

如果另一个项目的浏览器前端直接调用 Veridrop，并且域名不同，当前服务没有配置 CORS。推荐让前端调用自己的后端，再由后端调用 Veridrop。

### 访问控制

`/api/detect/*` 当前没有内置 API 鉴权。公开部署时建议至少增加以下外层保护:

- API 网关鉴权
- IP 白名单
- 反向代理限流
- 内网访问或 VPN
- 请求体大小限制
- 容器 CPU、内存和并发限制

## Docker 化建议

当前项目可直接打包为 Python Web 服务镜像。镜像中需要:

1. 安装 Python 3.10 或更高版本。
2. 安装项目依赖: `pip install -e ".[web]"`。
3. 暴露 Web 端口，例如 `8000`。
4. 设置 `VERIDROP_JOBS_DIR` 并挂载持久化目录。
5. 使用单 worker 启动 Uvicorn。

该文档只描述现有接口和集成方式，不要求修改业务代码。
