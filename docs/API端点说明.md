# IndexTTS API 端点完整说明

## 概述

IndexTTS API 提供了两个版本的 TTS 生成服务：
- **V1.5**: 基础版本，简单稳定
- **V2.0**: 增强版本，支持丰富的情感控制

---

## 🔐 认证说明

### Bearer Token 认证

所有 API 端点都需要 **Bearer Token 认证**（如果在 `config.yaml` 中配置了 token）。

#### 配置 Token

编辑 `config.yaml`:
```yaml
api:
  token: "your-secret-token-here"
```

**开发模式**: 留空 `token: ""` 则跳过认证  
**生产模式**: 必须设置强密码 token

#### 使用 Token

**Python 示例**:
```python
import requests

headers = {
    "Authorization": "Bearer your-secret-token-here"
}

response = requests.post(
    "http://localhost:8000/v2.0/generate",
    headers=headers,
    json={"text": "测试", "spk_audio_prompt": "speaker.wav"}
)
```

**cURL 示例**:
```bash
curl -X POST "http://localhost:8000/v2.0/generate" \
  -H "Authorization: Bearer your-secret-token-here" \
  -H "Content-Type: application/json" \
  -d '{"text": "测试", "spk_audio_prompt": "speaker.wav"}'
```

**JavaScript/Fetch 示例**:
```javascript
fetch("http://localhost:8000/v2.0/generate", {
    method: "POST",
    headers: {
        "Authorization": "Bearer your-secret-token-here",
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        text: "测试",
        spk_audio_prompt: "speaker.wav"
    })
})
```

#### 认证错误处理

**401 Unauthorized - Token 无效或缺失**:
```json
{
    "detail": "Invalid or missing token"
}
```

**解决方法**:
1. 检查 Token 是否正确
2. 确保使用 `Bearer` 前缀
3. 检查 `config.yaml` 中的 token 配置

📚 **详细配置指南**: 参见 [Token认证配置指南.md](./Token认证配置指南.md)

---

## 受保护的端点

以下端点需要 Token 认证：
- ✅ `GET /` - 根路径（API 信息）
- ✅ `POST /v1.5/generate` - V1.5 生成
- ✅ `POST /v2.0/generate` - V2.0 生成（纯参数）
- ✅ `POST /v2.0/emo_mode/generate` - V2.0 生成（emotion_mode）
- ✅ `GET /status/{task_id}` - 任务状态查询

公开端点（无需认证）：
- ✅ `GET /docs` - API 文档
- ✅ `GET /openapi.json` - OpenAPI 规范

---

## V1.5 端点

### `/v1.5/generate` - V1.5 生成

**特点**:
- ✅ 简单稳定，无情感控制
- ✅ 参数少，易于使用
- ✅ 适合基础 TTS 需求

**请求示例**:
```python
import requests

response = requests.post("http://localhost:8000/v1.5/generate", json={
    "text": "这是要合成的文本",
    "spk_audio_prompt": "voices/speaker.wav",
    "output_path": "output/result.wav",
    # 可选的生成控制参数
    "top_k": 30,
    "temperature": 1.0,
    "max_mel_tokens": 600
})

print(response.json())
# {"task_id": "xxx-xxx-xxx"}
```

**核心参数**:
- `text` (str, 必填): 要合成的文本
- `spk_audio_prompt` (str, 必填): 参考音频路径
- `output_path` (str, 可选): 输出文件路径

**生成控制参数** (可选):
- `top_k` (int, 默认30): Top-K 采样
- `temperature` (float, 默认1.0): 温度参数
- `repetition_penalty` (float, 默认10.0): 重复惩罚
- `max_mel_tokens` (int, 默认600): 最大生成长度

---

## 任务状态查询端点

### `GET /status/{task_id}` - 查询任务状态

**特点**:
- ✅ 通用端点，支持所有版本的任务查询
- ✅ 返回详细的任务状态和队列位置信息
- ✅ 实时更新，可用于轮询

**请求示例**:
```python
import requests

headers = {"Authorization": "Bearer your-token"}

response = requests.get(
    "http://localhost:8000/status/xxx-xxx-xxx",
    headers=headers
)

print(response.json())
```

**返回示例**:

**1. 排队中**:
```json
{
    "task_id": "abc-123-def",
    "status": "pending",
    "created_at": "2024-12-23 16:30:15",
    "details": {
        "error": null,
        "queue_position": 3,
        "queue_size": 5,
        "created_timestamp": 1703318415.0,
        "download_url": null,
        "file_url": null
    }
}
```
**说明**: 前面还有 3 个任务，队列中共有 5 个任务

**2. 正在执行**:
```json
{
    "task_id": "abc-123-def",
    "status": "processing",
    "created_at": "2024-12-23 16:30:15",
    "details": {
        "error": null,
        "queue_position": 0,
        "queue_size": 4,
        "created_timestamp": 1703318415.0,
        "download_url": null,
        "file_url": null
    }
}
```
**说明**: 正在执行（位置 0），队列中还有 4 个任务等待

**3. 已完成**:
```json
{
    "task_id": "abc-123-def",
    "status": "completed",
    "created_at": "2024-12-23 16:30:15",
    "details": {
        "error": null,
        "queue_position": null,
        "queue_size": 0,
        "created_timestamp": 1703318415.0,
        "download_url": "/download/abc-123-def",
        "file_url": "/files/abc-123-def"
    }
}
```
**说明**: 任务完成，使用 `details.download_url`（推荐）或 `details.file_url` 下载文件

**4. 执行失败**:
```json
{
    "task_id": "abc-123-def",
    "status": "failed",
    "created_at": "2024-12-23 16:30:15",
    "details": {
        "error": "Model loading failed: CUDA out of memory",
        "queue_position": null,
        "queue_size": 0,
        "created_timestamp": 1703318415.0,
        "download_url": null,
        "file_url": null
    }
}
```
**说明**: 任务失败，查看 `details.error` 字段了解失败原因

### 返回字段详解

**顶层字段**（基础信息）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务唯一标识符 |
| `status` | string | 任务状态：`pending`/`processing`/`completed`/`failed` |
| `created_at` | string | 任务创建时间（人类可读格式，如 "2024-12-23 16:30:15"） |
| `details` | object | 详细信息对象（见下表） |

**details 字段**（详细信息）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `error` | string/null | 错误信息（仅 `failed` 状态） |
| `queue_position` | int/null | 队列位置（见下表） |
| `queue_size` | int | 当前队列总大小 |
| `created_timestamp` | float | 原始Unix时间戳（用于程序处理） |
| `download_url` | string/null | 流式下载链接（仅 `completed` 状态，推荐使用） |
| `file_url` | string/null | 静态文件链接（仅 `completed` 状态，支持多次下载） |

### 队列位置说明

| queue_position | 含义 | 说明 |
|----------------|------|------|
| `0` | 正在执行 | 任务正在生成中 |
| `1` | 排队第1位 | 前面还有 1 个任务 |
| `2` | 排队第2位 | 前面还有 2 个任务 |
| `n` | 排队第n位 | 前面还有 n 个任务 |
| `null` | 已结束 | 任务已完成或失败 |

### status 与字段关系

不同的 `status` 状态下，`details` 中的字段值有不同的含义：

| status | error | queue_position | download_url | file_url | 说明 |
|--------|-------|----------------|--------------|----------|------|
| `pending` | `null` | `1+` | `null` | `null` | 排队中，等待执行 |
| `processing` | `null` | `0` | `null` | `null` | 正在执行中 |
| `completed` | `null` | `null` | **有值** | **有值** | 已完成，可下载文件 |
| `failed` | **有值** | `null` | `null` | `null` | 执行失败，查看错误 |

**关键规则**:
- ✅ `status = "completed"` 时，`details.download_url` 和 `details.file_url` 有值
- ✅ `status = "failed"` 时，`details.error` 有值
- ✅ `status = "pending"` 或 `"processing"` 时，`queue_position` 有值
- ✅ **推荐使用 `download_url` 下载**（自动删除，节省空间）
- ✅ **需要多次下载时使用 `file_url`**（保留24小时）

### 轮询示例

**Python 完整示例**:
```python
import requests
import time

API_URL = "http://localhost:8000"
TOKEN = "your-secret-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

# 1. 提交任务
response = requests.post(
    f"{API_URL}/v2.0/generate",
    headers=headers,
    json={
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav"
    }
)
task_id = response.json()["task_id"]
print(f"任务已提交: {task_id}")

# 2. 轮询状态
while True:
    status_response = requests.get(
        f"{API_URL}/status/{task_id}",
        headers=headers
    )
    status = status_response.json()
    
    # 显示状态信息
    if status["status"] == "pending":
        position = status["details"]["queue_position"]
        print(f"排队中... 前面还有 {position} 个任务")
    elif status["status"] == "processing":
        print(f"正在生成中...")
    elif status["status"] == "completed":
        print(f"✅ 生成完成！")
        
        # 使用返回的下载链接
        download_url = status["details"]["download_url"]
        print(f"下载链接: {API_URL}{download_url}")
        
        # 下载文件
        download_response = requests.get(
            f"{API_URL}{download_url}",
            headers=headers,
            stream=True
        )
        
        with open("output.wav", "wb") as f:
            for chunk in download_response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"文件已下载！")
        break
    elif status["status"] == "failed":
        print(f"❌ 生成失败: {status['details']['error']}")
        break
    
    time.sleep(2)  # 每 2 秒查询一次
```

**JavaScript/Fetch 示例**:
```javascript
const API_URL = "http://localhost:8000";
const TOKEN = "your-secret-token";

async function pollTaskStatus(taskId) {
    while (true) {
        const response = await fetch(`${API_URL}/status/${taskId}`, {
            headers: {
                "Authorization": `Bearer ${TOKEN}`
            }
        });
        const status = await response.json();
        
        if (status.status === "pending") {
            console.log(`排队中... 前面还有 ${status.details.queue_position} 个任务`);
        } else if (status.status === "processing") {
            console.log("正在生成中...");
        } else if (status.status === "completed") {
            console.log("✅ 生成完成！");
            
            // 使用返回的下载链接
            const downloadUrl = status.details.download_url;
            console.log("下载链接:", `${API_URL}${downloadUrl}`);
            
            return downloadUrl;
        } else if (status.status === "failed") {
            console.error("❌ 生成失败:", status.details.error);
            throw new Error(status.details.error);
        }
        
        await new Promise(resolve => setTimeout(resolve, 2000));
    }
}
```

---

## V2.0 端点

### 1. `/v2.0/generate` - 纯参数方式（推荐对外使用）

**特点**:
- ✅ 完全兼容原项目 `vendor/indextts/infer_v2.py`
- ✅ 直接使用底层参数，无封装层
- ✅ 便于跟随原项目升级
- ✅ 最大灵活性

**使用示例**:
```python
import requests

# 方式1: 使用说话人原始情感
response = requests.post("http://localhost:8000/v2.0/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav"
})

# 方式2: 参考音频控制
response = requests.post("http://localhost:8000/v2.0/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emo_audio_prompt": "happy.wav",
    "emo_alpha": 0.8
})

# 方式3: 情绪向量控制
response = requests.post("http://localhost:8000/v2.0/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0]
})

# 方式4: 文本驱动
response = requests.post("http://localhost:8000/v2.0/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "use_emo_text": True,
    "emo_text": "非常高兴"
})
```

---

### 2. `/v2.0/emo_mode/generate` - emotion_mode 简化方式

**特点**:
- ✅ 使用 `emotion_mode` 枚举简化配置
- ✅ 自动参数验证
- ✅ 适合内部工具使用
- ⚠️ 需要维护封装层

**使用示例**:
```python
import requests

# 方式1: 与音色相同
response = requests.post("http://localhost:8000/v2.0/emo_mode/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emotion_mode": "same_as_speaker"
})

# 方式2: 参考音频
response = requests.post("http://localhost:8000/v2.0/emo_mode/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emotion_mode": "reference_audio",
    "emo_audio_prompt": "happy.wav",
    "emo_alpha": 0.8
})

# 方式3: 情绪向量
response = requests.post("http://localhost:8000/v2.0/emo_mode/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emotion_mode": "emotion_vector",
    "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0]
})

# 方式4: 文本驱动
response = requests.post("http://localhost:8000/v2.0/emo_mode/generate", json={
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav",
    "emotion_mode": "text_driven",
    "emo_text": "非常高兴"
})
```

---

## 所有端点对比

| 端点 | 版本 | 情感控制 | 参数方式 | 推荐场景 |
|------|------|---------|---------|----------|
| `/v1.5/generate` | V1.5 | ❌ 不支持 | 纯参数 | 基础 TTS 需求 |
| `/v2.0/generate` | V2.0 | ✅ 支持 | 纯参数 | 对外 API（推荐） |
| `/v2.0/emo_mode/generate` | V2.0 | ✅ 支持 | emotion_mode | 内部工具 |

### V2.0 端点详细对比

| 特性 | `/v2.0/generate` | `/v2.0/emo_mode/generate` |
|------|------------------|---------------------------|
| 参数方式 | 纯底层参数 | emotion_mode 枚举 |
| 兼容性 | ⭐⭐⭐⭐⭐ 原生兼容 | ⭐⭐⭐ 自定义封装 |
| 易用性 | ⭐⭐⭐ 需理解参数 | ⭐⭐⭐⭐⭐ 简单直观 |
| 升级维护 | ⭐⭐⭐⭐⭐ 自动跟随 | ⭐⭐⭐ 需同步更新 |
| 参数验证 | ⭐⭐⭐ 基础验证 | ⭐⭐⭐⭐⭐ 完整验证 |
| 推荐场景 | 对外 API | 内部工具 |

---

## 使用建议

### 基础 TTS 需求（使用 V1.5）
```python
# 简单的音色克隆，无需情感控制
API_ENDPOINT = "http://your-api.com/v1.5/generate"

response = requests.post(API_ENDPOINT, json={
    "text": "要合成的文本",
    "spk_audio_prompt": "speaker.wav"
})
```

### 对外 API（推荐 V2.0 纯参数）
```python
# 提供给第三方开发者
API_ENDPOINT = "http://your-api.com/v2.0/generate"

# 文档中说明底层参数使用方式
# 参考: docs/V2.0情感控制-纯参数方式.md
```

### 内部工具（可选 `/v2.0/emo_mode/generate`）
```python
# 内部管理界面、测试工具等
API_ENDPOINT = "http://localhost:8000/v2.0/emo_mode/generate"

# 使用 emotion_mode 简化配置
# 参考: docs/V2.0情感控制完整指南.md
```

---

## FastAPI 自动文档

访问 `http://localhost:8000/docs` 可以看到所有端点：

**V1.5 端点**:
- `POST /v1.5/generate` - V1.5 生成（基础版本）

**V2.0 端点**:
- `POST /v2.0/generate` - V2.0 生成（纯参数方式，推荐对外）
- `POST /v2.0/emo_mode/generate` - V2.0 生成（emotion_mode 方式）

**通用端点**:
- `GET /status/{task_id}` - 查询任务状态

每个端点都有详细的参数说明和交互式测试界面。

---

## 快速选择指南

**⚠️ 重要提醒**: 所有端点都需要 Bearer Token 认证（生产模式）

```
需要情感控制？
├─ 否 → 使用 /v1.5/generate
└─ 是 → V2.0
    ├─ 对外 API → /v2.0/generate (纯参数)
    └─ 内部工具 → /v2.0/emo_mode/generate (emotion_mode)
```

**认证示例**:
```python
headers = {"Authorization": "Bearer your-token"}
requests.post(url, headers=headers, json=data)
```
---

## 音频文件上传端点

### `POST /upload/audio` - 上传音频文件

当服务器缺少客户端引用的音频文件时，可以通过此端点上传。

**目录结构说明**：
- 客户端和服务器各有自己的 `voices` 目录
- 两者目录结构相同
- 通过相对路径引用文件（如 `voices/ref_audios/speaker.wav`）

**特点**:
- ✅ 支持多种音频格式（wav, mp3, flac, ogg, m4a）
- ✅ 文件大小限制：50MB
- ✅ 自动创建目录
- ✅ 路径安全验证

**请求参数**:
- `file`: 音频文件（multipart/form-data）
- `path`: 服务器端保存路径（相对路径）

**Python 示例**:
```python
import requests

headers = {"Authorization": "Bearer your-token"}

with open("speaker.wav", "rb") as f:
    files = {"file": f}
    data = {"path": "voices/ref_audios/speaker.wav"}
    
    response = requests.post(
        "http://localhost:8000/upload/audio",
        headers=headers,
        files=files,
        data=data
    )

print(response.json())
# {"success": true, "path": "voices/ref_audios/speaker.wav", "size": 123456}
```

**返回**:
```json
{
    "success": true,
    "path": "voices/ref_audios/speaker.wav",
    "size": 123456
}
```

---

## 音频文件检查机制

### 自动检查

所有生成端点都会自动检查音频文件是否存在。

**检查的文件**:
- `spk_audio_prompt`（必需）
- `emo_audio_prompt`（可选，仅 V2.0）

**如果文件缺失**:
```json
{
    "error": "missing_audio_files",
    "message": "Required audio files not found on server",
    "missing_files": ["voices/ref_audios/speaker.wav"]
}
```

### 完整工作流程

```python
import requests

API_URL = "http://localhost:8000"
TOKEN = "your-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

# 1. 尝试提交任务
try:
    response = requests.post(
        f"{API_URL}/v2.0/generate",
        headers=headers,
        json={
            "text": "测试",
            "spk_audio_prompt": "voices/ref_audios/new_speaker.wav"
        }
    )
    task_id = response.json()["task_id"]
    
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 400:
        error = e.response.json()
        
        # 2. 检查是否缺失文件
        if error.get("error") == "missing_audio_files":
            # 3. 上传缺失文件
            for file_path in error["missing_files"]:
                with open(file_path, "rb") as f:
                    requests.post(
                        f"{API_URL}/upload/audio",
                        headers=headers,
                        files={"file": f},
                        data={"path": file_path}
                    )
            
            # 4. 重新提交
            response = requests.post(
                f"{API_URL}/v2.0/generate",
                headers=headers,
                json={
                    "text": "测试",
                    "spk_audio_prompt": "voices/ref_audios/new_speaker.wav"
                }
            )
            task_id = response.json()["task_id"]
```

---

## 总结

### 所有端点列表

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/` | GET | API 信息 | ✅ |
| `/v1.5/generate` | POST | V1.5 生成 | ✅ |
| `/v2.0/generate` | POST | V2.0 生成（纯参数） | ✅ |
| `/v2.0/emo_mode/generate` | POST | V2.0 生成（emotion_mode） | ✅ |
| `/status/{task_id}` | GET | 查询任务状态 | ✅ |
| `/download/{task_id}` | GET | 流式下载 | ✅ |
| `/files/{task_id}` | GET | 静态文件访问 | ✅ |
| `/upload/audio` | POST | 上传音频文件 | ✅ |
| `/docs` | GET | API 文档 | ❌ |

### 快速开始

1. **配置 Token**：编辑 `config.yaml`，设置 `api.token`
2. **准备音频**：将参考音频放到 `voices` 目录
3. **提交任务**：调用生成端点
4. **查询状态**：轮询 `/status/{task_id}`
5. **下载文件**：使用返回的 `download_url`

完整示例请参考各端点的详细说明。
