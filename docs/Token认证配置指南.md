# API Token 认证配置指南

## 概述

IndexTTS API 支持 Bearer Token 认证，保护您的 API 端点免受未授权访问。

---

## 配置方法

### 1. 编辑 `config.yaml`

```yaml
# API 配置
api:
  # Bearer Token 认证
  # 留空则禁用认证（开发模式）
  # 生产环境请设置强密码 token
  token: "your-secret-token-here"
```

### 2. 生成安全的 Token

**推荐使用强随机字符串**:
```python
import secrets
token = secrets.token_urlsafe(32)
print(token)
# 例如: "xK7mP9nQ2wR5tY8uI1oP4aS6dF3gH0jL"
```

或使用在线工具生成 UUID:
```
https://www.uuidgenerator.net/
```

---

## 使用方法

### Python 客户端

```python
import requests

# 配置 API 地址和 Token
API_URL = "http://localhost:8000"
TOKEN = "your-secret-token-here"

# 设置认证头
headers = {
    "Authorization": f"Bearer {TOKEN}"
}

# 发送请求
response = requests.post(
    f"{API_URL}/v2.0/generate",
    headers=headers,
    json={
        "text": "测试文本",
        "spk_audio_prompt": "speaker.wav"
    }
)

print(response.json())
```

### cURL

```bash
curl -X POST "http://localhost:8000/v2.0/generate" \
  -H "Authorization: Bearer your-secret-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "测试文本",
    "spk_audio_prompt": "speaker.wav"
  }'
```

### JavaScript/Fetch

```javascript
const API_URL = "http://localhost:8000";
const TOKEN = "your-secret-token-here";

fetch(`${API_URL}/v2.0/generate`, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        text: "测试文本",
        spk_audio_prompt: "speaker.wav"
    })
})
.then(response => response.json())
.then(data => console.log(data));
```

---

## 开发模式 vs 生产模式

### 开发模式（Token 未配置）

```yaml
api:
  token: ""  # 留空
```

**特点**:
- ✅ 无需认证，方便开发调试
- ⚠️ 任何人都可以访问 API
- ❌ 不适合生产环境

### 生产模式（Token 已配置）

```yaml
api:
  token: "xK7mP9nQ2wR5tY8uI1oP4aS6dF3gH0jL"
```

**特点**:
- ✅ 需要有效 Token 才能访问
- ✅ 保护 API 免受未授权访问
- ✅ 适合生产环境

---

## 错误处理

### 401 Unauthorized - Token 无效

**请求**:
```bash
curl -X POST "http://localhost:8000/v2.0/generate" \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "spk_audio_prompt": "speaker.wav"}'
```

**响应**:
```json
{
    "detail": "Invalid or missing token"
}
```

### 401 Unauthorized - 缺少 Token

**请求**:
```bash
curl -X POST "http://localhost:8000/v2.0/generate" \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "spk_audio_prompt": "speaker.wav"}'
```

**响应**:
```json
{
    "detail": "Not authenticated"
}
```

---

## 安全最佳实践

### 1. 使用强密码 Token
- ✅ 至少 32 字符
- ✅ 包含字母、数字、特殊字符
- ❌ 不要使用简单密码如 "123456"

### 2. 定期更换 Token
建议每 3-6 个月更换一次 Token

### 3. 不要在代码中硬编码 Token
**❌ 错误做法**:
```python
TOKEN = "xK7mP9nQ2wR5tY8uI1oP4aS6dF3gH0jL"  # 硬编码
```

**✅ 正确做法**:
```python
import os
TOKEN = os.getenv("INDEXTTS_API_TOKEN")  # 从环境变量读取
```

### 4. 使用 HTTPS
生产环境务必使用 HTTPS 加密传输，防止 Token 被窃取

### 5. 限制 Token 访问权限
- 不要将 Token 提交到 Git 仓库
- 不要在公开场合分享 Token
- 为不同客户端使用不同 Token（如需要）

---

## FastAPI 自动文档中的认证

访问 `http://localhost:8000/docs` 时：

1. 点击右上角的 **Authorize** 按钮
2. 在弹出框中输入 Token（不需要 "Bearer " 前缀）
3. 点击 **Authorize**
4. 现在可以直接在文档中测试 API

---

## 受保护的端点

所有生成端点都需要认证：
- ✅ `POST /v1.5/generate`
- ✅ `POST /v2.0/generate`
- ✅ `POST /v2.0/emo_mode/generate`

公开端点（无需认证）：
- ✅ `GET /` - 根路径
- ✅ `GET /status/{task_id}` - 任务状态查询

---

## 故障排查

### 问题：Token 配置后仍然可以无认证访问

**检查**:
1. 确认 `config.yaml` 中 `api.token` 不为空
2. 重启 API 服务器
3. 检查日志是否有 "API token not configured" 警告

### 问题：正确的 Token 仍然返回 401

**检查**:
1. Token 前是否有多余空格
2. 是否使用了 "Bearer " 前缀（应该在 Header 中自动添加）
3. Token 是否完全匹配（区分大小写）

### 问题：如何临时禁用认证

编辑 `config.yaml`:
```yaml
api:
  token: ""  # 设为空字符串
```

然后重启服务器。
