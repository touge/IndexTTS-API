# IndexTTS-API

基于 IndexTTS 的高性能 TTS（文本转语音）API 服务，支持音色克隆、情感控制和字幕生成。

## ✨ 特性

- 🎙️ **音色克隆**：基于参考音频生成自然语音
- 🎭 **情感控制**：支持多种情感控制方式（V2.0）
- 📝 **字幕生成**：自动生成 SRT 格式字幕文件
- ⚡ **异步队列**：高效的任务队列管理
- 🔐 **Token 认证**：安全的 Bearer Token 认证
- 📊 **实时状态**：任务状态实时查询
- 🚀 **多引擎支持**：可扩展的 TTS 引擎架构

## 📋 目录

- [快速开始](#快速开始)
- [API 端点](#api-端点)
- [使用示例](#使用示例)
- [配置说明](#配置说明)
- [部署指南](#部署指南)
- [开发文档](#开发文档)

## 🚀 快速开始

### 环境要求

- Python 3.8+
- CUDA 11.8+ (GPU 推理)
- 8GB+ GPU 显存（推荐）

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/IndexTTS-API.git
cd IndexTTS-API

# 安装依赖
pip install -r requirements.txt

# 配置文件
cp config.yaml.example config.yaml
# 编辑 config.yaml 设置模型路径和 API token
```

### 启动服务

```bash
# 开发模式
python main.py

# 生产模式
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --workers 1
```

服务启动后访问：
- API 文档：http://localhost:8000/docs
- 根路径：http://localhost:8000/

## 📡 API 端点

### TTS 生成

| 端点 | 版本 | 功能 | 情感控制 |
|------|------|------|---------|
| `POST /v1.5/generate` | V1.5 | 基础 TTS 生成 | ❌ |
| `POST /v2.0/generate` | V2.0 | 高级 TTS 生成（推荐） | ✅ |
| `POST /v2.0/emo_mode/generate` | V2.0 | 简化情感控制 | ✅ |

### 字幕生成

| 端点 | 功能 |
|------|------|
| `POST /subtitle/generate` | 音频转字幕（Whisper + 文本对齐） |

### 通用端点

| 端点 | 功能 |
|------|------|
| `GET /status/{task_id}` | 查询任务状态 |
| `GET /download/{task_id}` | 下载生成的音频 |
| `GET /download/subtitle/{task_id}` | 下载生成的字幕 |
| `POST /upload/audio` | 上传参考音频 |

## 💡 使用示例

### 基础 TTS 生成（V1.5）

```python
import requests

headers = {"Authorization": "Bearer your-token"}

response = requests.post(
    "http://localhost:8000/v1.5/generate",
    headers=headers,
    json={
        "text": "这是要合成的文本",
        "spk_audio_prompt": "voices/speaker.wav"
    }
)

task_id = response.json()["task_id"]
print(f"任务已提交: {task_id}")
```

### 情感控制 TTS（V2.0）

```python
import requests

headers = {"Authorization": "Bearer your-token"}

# 使用情感向量控制
response = requests.post(
    "http://localhost:8000/v2.0/generate",
    headers=headers,
    json={
        "text": "今天真是太开心了！",
        "spk_audio_prompt": "voices/speaker.wav",
        "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],  # [高兴, 愤怒, 悲伤, ...]
        "emo_alpha": 0.9
    }
)

task_id = response.json()["task_id"]
```

### 字幕生成

```python
import requests

headers = {"Authorization": "Bearer your-token"}

with open("audio.wav", "rb") as audio:
    files = {"audio_file": audio}
    data = {"text": "这是要对齐的文本内容"}
    
    response = requests.post(
        "http://localhost:8000/subtitle/generate",
        headers=headers,
        files=files,
        data=data
    )

task_id = response.json()["task_id"]
```

### 查询任务状态

```python
import requests
import time

headers = {"Authorization": "Bearer your-token"}

while True:
    response = requests.get(
        f"http://localhost:8000/status/{task_id}",
        headers=headers
    )
    status = response.json()
    
    if status["status"] == "completed":
        # 下载音频
        download_url = status["details"]["download_url"]
        print(f"完成！下载链接: {download_url}")
        break
    elif status["status"] == "failed":
        print(f"失败: {status['details']['error']}")
        break
    
    print(f"状态: {status['status']}")
    time.sleep(2)
```

## ⚙️ 配置说明

### config.yaml 主要配置

```yaml
# API 配置
api:
  host: "0.0.0.0"
  port: 8000
  token: "your-secret-token"  # 生产环境必须设置
  
  output:
    tasks_dir: "output/tasks"  # 任务输出目录
    cleanup:
      enabled: true
      max_age_hours: 24  # 自动清理 24 小时前的文件

# 模型配置
model:
  v1_5:
    path: "models/IndexTTS-V1.5"
  v2_0:
    path: "models/IndexTTS-V2.0"

# Whisper 配置（字幕生成）
whisper:
  model_size: "large-v3"
  device: "cuda"
  compute_type: "float16"
```

### 认证配置

**开发模式**（跳过认证）：
```yaml
api:
  token: ""
```

**生产模式**（必须认证）：
```yaml
api:
  token: "your-strong-secret-token-here"
```

## 🎭 情感控制说明（V2.0）

### 四种情感控制方式

#### 1. 与音色相同（默认）
不提供额外情感参数，使用说话人原始情感。

#### 2. 参考音频控制
```python
{
    "emo_audio_prompt": "voices/happy.wav",
    "emo_alpha": 0.8  # 情感强度 0.0-1.0
}
```

#### 3. 情绪向量控制
```python
{
    "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],
    # 向量维度: [高兴, 愤怒, 悲伤, 恐惧, 反感, 低落, 惊讶, 自然]
    "emo_alpha": 0.9
}
```

#### 4. 文本驱动
```python
{
    "use_emo_text": true,
    "emo_text": "非常高兴和激动"  # 可选，不填则使用主文本
}
```

## 🏗️ 架构设计

### 核心组件

```
IndexTTS-API/
├── app/
│   ├── api/              # API 路由
│   │   ├── v1_5/         # V1.5 端点
│   │   ├── v2_0/         # V2.0 端点
│   │   ├── subtitle_routes.py  # 字幕生成
│   │   └── main.py       # 主应用
│   ├── core/             # 核心逻辑
│   │   ├── queue_manager.py    # 任务队列管理
│   │   ├── subtitle/           # 字幕生成模块
│   │   └── security.py         # 认证模块
│   └── utils/            # 工具函数
├── vendor/               # 第三方模块
│   └── indextts/         # IndexTTS 原始代码
├── models/               # 模型文件
├── voices/               # 参考音频
├── output/               # 输出目录
└── config.yaml           # 配置文件
```

### 任务队列机制

- **异步处理**：所有生成任务异步执行
- **智能调度**：FIFO 队列，支持优先级
- **模型管理**：懒加载 + 自动卸载
- **状态追踪**：实时任务状态查询

### 支持的 TTS 引擎

当前支持：
- ✅ **IndexTTS**（V1.5 / V2.0）
- 🔄 **CosyVoice**（计划中）

扩展新引擎只需：
1. 在 `TTSEngine` 枚举中添加引擎类型
2. 实现对应的 `_run_xxx_inference` 方法

## 📦 部署指南

### Docker 部署

```bash
# 构建镜像
docker build -t indextts-api .

# 运行容器
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/voices:/app/voices \
  -v $(pwd)/output:/app/output \
  --gpus all \
  indextts-api
```

### Systemd 服务

```ini
[Unit]
Description=IndexTTS API Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/IndexTTS-API
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn app.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # 支持大文件上传
        client_max_body_size 50M;
    }
}
```

## 🧪 测试

### 运行测试

```bash
# 测试 TTS 生成
python tester/run_real_generation.py

# 测试字幕生成
python tester/subtitle/test_subtitle_api.py
```

### 测试配置

编辑 `tester/config.py` 设置测试参数：
```python
TEST_PAYLOAD_V1_5 = {
    "text": "测试文本",
    "spk_audio_prompt": "voices/speaker.wav"
}
```

## 📚 开发文档

详细文档请参考 `docs/` 目录：

- [API 端点说明](docs/API端点说明.md) - 完整的 API 参考
- [Token 认证配置指南](docs/Token认证配置指南.md) - 认证配置详解
- [字幕生成说明](tester/subtitle/README.md) - 字幕功能使用指南

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目基于 MIT 许可证开源。

## 🙏 致谢

- [IndexTTS](https://github.com/X-LANCE/IndexTTS) - 核心 TTS 模型
- [Whisper](https://github.com/openai/whisper) - 语音识别模型
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架

## 📞 联系方式

- Issues: [GitHub Issues](https://github.com/your-repo/IndexTTS-API/issues)
- Email: your-email@example.com

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**
