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
pip install  torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu129

# 安装 pynini（必须使用 conda）
conda install -c conda-forge pynini==2.1.6

# 安装 pynini（必须使用 conda）
pip install -r requirements.txt

# 拉取indextts依赖
download_indextts.ps1

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

---

## 📦 全局统一响应结构

为了极致简化不同客户端的对接，本系统的**所有 API 接口 (包括抛出的异常错误)**，均强制遵循同一个 JSON 结构体：

```json
{
  "status": "success",  // 接口状态描述：成功 ("success") 或 失败 ("failed") 或 轮询状态 ("processing", "completed" 等)
  "code": 0,            // 业务状态码：0 代表绝对成功，非 0 代表失败
  "message": "操作成功", // 提供给终端用户查看的直白中文提示 (如 "上传成功"、"名称已存在" 等)
  "data": { ... }       // 具体的业务数据负载 (无论多复杂，统统在这个节点内部)
}
```

### 1. 常规成功返回 (增删改查)
例如：新增或者重命名发音人
```json
{
  "status": "success",
  "code": 0,
  "message": "发音人重命名成功 (老赫磁性版)",
  "data": null
}
```

### 2. 全局鉴权拦截与错误格式
为了避免 Axios 等拦截器在取值时猜盲盒，只要触发后端报错拦截，格式同样统一：
```json
{
  "status": "failed",
  "code": -1,
  "message": "该分类下已存在同名发音人",
  "data": null
}
```

### 3. 排队与配音任务流式轮询结构
当发起生成请求后，业务详情将全部在 `data` 节点内展开：

**获取生成任务 ID (POST /generate):**
```json
{
  "status": "success",
  "code": 0,
  "message": "操作成功",
  "data": {
    "task_id": "7fbd0939-..."
  }
}
```

**轮询进度 (GET /status/{task_id}):**
```json
{
  "status": "processing", // 重点注意：在这个接口，status 将承载队列轮询状态: pending/processing/completed/failed
  "code": 0,
  "message": "查询成功",
  "data": {
    "task_id": "7fbd0939-...",
    "created_at": "2024-12-23 16:30:00",
    "queue_position": 0, // 表示当前正在执行 (如果是 1 则代表前面还有一个人排队)
    "queue_size": 1,
    "error": null,
    "download_url": null, // 当 status 变成 "completed" 时，此字段会变成可供下载的 URI
    "file_url": null,
    "subtitle_url": null
  }
}
```

## 📡 API 端点

### 1. TTS 与字幕生成
| 端点 | 方法 | 功能 |
|------|------|------|
| `/v1.5/generate` | POST | 基础 TTS 语音合成 (V1.5) |
| `/v2.0/generate` | POST | 高级 TTS 语音合成 (推荐，支持情感控制) |
| `/v2.0/emo_mode/generate` | POST | 简化版情感控制模式 |
| `/subtitle/generate` | POST | 音频转字幕 (Whisper 生成 SRT) |

### 2. 任务状态与文件下载
| 端点 | 方法 | 功能 |
|------|------|------|
| `/status/{task_id}` | GET | 查询生成任务的实时状态 |
| `/download/{task_id}` | GET | 流式下载生成完毕的音频 (支持阅后即焚清理) |
| `/files/{task_id}` | GET | 访问生成的音频静态文件 (支持断点续传及重试) |
| `/download/subtitle/{task_id}` | GET| 下载生成的 SRT 字幕文件 |

### 3. 发音人参考资源管理 (Speaker)
| 端点 | 方法 | 功能 |
|------|------|------|
| `/speaker/` | GET | 获取系统当前所有发音人列表及分类树 |
| `/speaker/category` | POST | 新增空的分类存放发音人 |
| `/speaker/upload` | POST | 上传新的发音人 (带有同名防冲突校验) |
| `/speaker/rename` | PUT | 对发音人进行重命名或移动分类 |
| `/speaker/` | DELETE| 删除指定发音人或整个分类目录 |

### 4. 情绪音参考资源管理 (Emotion)
| 端点 | 方法 | 功能 |
|------|------|------|
| `/emo/` | GET | 获取系统当前所有情绪音列表及分类树 |
| `/emo/category` | POST | 新增空的分类存放情绪音 |
| `/emo/upload` | POST | 上传新的情绪音 (带有同名防冲突校验) |
| `/emo/rename` | PUT | 对情绪音进行重命名或移动分类 |
| `/emo/` | DELETE| 删除指定情绪音或整个分类目录 |

### 5. 静态免限访问资源
| 端点 | 方法 | 功能 |
|------|------|------|
| `/static/voices/{file_path}` | GET | 获取音频文件 (无 Token 限制，可供 `<audio>` 标签在线播放) |

---

## 💡 详细使用示例

> **注意：** 除静态播放路由 `/static` 以外，所有接口请求 Header 均需要携带 `Authorization: Bearer your-token`（受 `config.yaml` 控制）。

### 1. TTS 任务生成相关

**1.1 基础 TTS 生成（V1.5）**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.post(
    "http://localhost:8000/v1.5/generate",
    headers=headers,
    json={
        "text": "这是要合成的文本", 
        "speaker": "老赫气泡音版" # 推荐直接传入发音人基础名称
    }
)
task_id = response.json()["data"]["task_id"]
```

**1.2 情感控制 TTS（V2.0）**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.post(
    "http://localhost:8000/v2.0/generate",
    headers=headers,
    json={
        "text": "今天真是太开心了！",
        "speaker": "发音人名称",       # 必填，基础发音人
        "emotion": "大笑",             # 可选，通过参考情绪音干预情绪
        "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],  # 或通过向量精确干预
        "emo_alpha": 0.9               # 干预强度
    }
)
task_id = response.json()["data"]["task_id"]
```

**1.3 字幕生成 (/subtitle/generate)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
with open("audio.wav", "rb") as audio:
    response = requests.post(
        "http://localhost:8000/subtitle/generate",
        headers=headers,
        files={"audio_file": audio},
        data={"text": "这是需要强制对齐的文本(可选)"}
    )
task_id = response.json()["data"]["task_id"]
```

---

### 2. 状态查询与结果下载

**2.1 查询状态 (/status/{id})**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.get(f"http://localhost:8000/status/{task_id}", headers=headers)
print(response.json()) # {"status": "completed", "code": 0, "message": "查询成功", "data": {"task_id": "...", ...}} 
```

**2.2 流式下载生成的音频 (/download/{id})**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
# 适合一次性保存到本地 (依据后端配置，这可能触发"阅后即焚")
response = requests.get(f"http://localhost:8000/download/{task_id}", headers=headers, stream=True)
with open("result.wav", "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
```

**2.3 静态下载生成的音频 (/files/{id})**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
# 支持大文件断点续传及重试获取，不会阅后即焚
response = requests.get(f"http://localhost:8000/files/{task_id}", headers=headers)
```

**2.4 下载 SRT 字幕 (/download/subtitle/{id})**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.get(f"http://localhost:8000/download/subtitle/{task_id}", headers=headers)
with open("result.srt", "wb") as f:
    f.write(response.content)
```

---

### 3. 发音人与情绪音资源管理

**3.1 获取所有声音列表 (GET /speaker/ | /emo/)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.get("http://localhost:8000/speaker/", headers=headers)
```

**3.2 创建空分类 (POST /speaker/category | /emo/category)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.post(
    "http://localhost:8000/speaker/category",
    headers=headers,
    json={"name": "全新的空白分类"}
)
```

**3.3 安全上传参考音频 (POST /speaker/upload | /emo/upload)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
with open("test.wav", "rb") as f:
    response = requests.post(
        "http://localhost:8000/speaker/upload", 
        headers=headers, 
        files={"file": f}, 
        data={
            "category": "常用", 
            "name": "男声一号" # 系统自带查重，如无冲突将落盘至: voices/ref_audios/常用/男声一号.wav
        }
    )
```

**3.4 重命名和分类移动 (PUT /speaker/rename | /emo/rename)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.put(
    "http://localhost:8000/speaker/rename",
    headers=headers,
    json={
        "old_path": "voices/ref_audios/常用/男声一号.wav",
        "new_path": "voices/ref_audios/不常用/老兵男声.wav"
    }
)
```

**3.5 删除音频或分类 (DELETE /speaker/ | /emo/)**
```python
import requests
headers = {"Authorization": "Bearer your-token"}
response = requests.delete(
    "http://localhost:8000/speaker/",
     headers=headers,
     json={"path": "voices/ref_audios/不常用/老兵男声.wav"} # 直接传"voices/ref_audios/不常用"则清空分类
)
```

---

### 4. 浏览器静态播放 (前端福利)

给客户端/网页调用的静态路由**已移除 Token 强校验**，并指定了内容内联 (`inline`) 的响应头。开发者直接将服务器路径嵌入原生 `<audio>` 标签即可。

```html
<!-- 直接绑定 src，实现在线无阻碍试听，避免诱导浏览器下载行为 -->
<audio controls src="http://localhost:8000/static/voices/ref_audios/常用/男声一号.wav"></audio>

<audio controls src="http://localhost:8000/static/voices/emo_audios/开心/大笑.wav"></audio>
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
    "emotion": "大笑", # 直接用情绪名称，或相对路径 "voices/emo_audios/开心/大笑.wav"
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
