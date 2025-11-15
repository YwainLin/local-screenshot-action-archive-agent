# 本地截图行动归档 Agent

一个默认离线运行的桌面文件整理 Agent，通过图像去重、OCR 和规则提取，将截图整理为可检索信息和行动建议。

## 功能特性

- **只读扫描**：安全扫描用户指定目录，不修改原文件
- **图像去重**：SHA-256 完全重复 + pHash 近似重复检测
- **本地 OCR**：使用 PaddleOCR 进行文字识别
- **规则提取**：自动识别日期、链接、金额、行动词等
- **LLM 增强**：支持 Ollama 本地模型或 OpenAI 兼容 API
- **全文搜索**：基于 SQLite FTS5 的本地全文搜索
- **归档建议**：生成待审批的归档计划，用户完全控制
- **审计日志**：所有文件操作可追溯
- **敏感信息掩码**：银行卡号、验证码、密码等自动掩码

## 安装

### 使用 Conda（推荐）

```bash
# 克隆仓库
git clone https://github.com/YwainLin/local-screenshot-action-archive-agent.git
cd local-screenshot-action-archive-agent

# 创建 conda 环境
conda create -n screenshot-agent python=3.11 -y
conda activate screenshot-agent

# 安装依赖
conda install -c conda-forge fastapi uvicorn pydantic sqlalchemy pillow jinja2 httpx numpy -y
pip install aiosqlite python-multipart imagehash
```

### 可选依赖

```bash
# OCR 支持
pip install paddleocr paddlepaddle

# 图数据库支持
pip install neo4j neo4j-graphrag
```

## 快速开始

```bash
# 激活环境
conda activate screenshot-agent

# 启动服务
uvicorn app.api.main:app --reload

# 访问 Web 界面
# http://localhost:8000
```

## Web 页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 工作区 | `/` | 选择目录、创建扫描任务 |
| 扫描结果 | `/runs/{id}` | 文件数、重复组、OCR 状态 |
| 搜索 | `/search` | 关键词/日期/标签查询 |
| 归档审批 | `/proposals` | 单项确认、修改目标、拒绝 |
| 审计日志 | `/audit` | 已批准复制/导出操作及哈希 |

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/api/v1/scans` | 提交目录扫描任务 |
| `GET` | `/api/v1/scans/{id}` | 查询扫描进度 |
| `GET` | `/api/v1/assets` | 查询资产列表 |
| `GET` | `/api/v1/search` | 全文搜索资产 |
| `GET` | `/api/v1/search/extractions` | 搜索提取结果 |
| `POST` | `/api/v1/proposals/generate` | 生成归档建议 |
| `GET` | `/api/v1/proposals` | 获取归档建议列表 |
| `POST` | `/api/v1/proposals/{id}/approve` | 批准单项建议 |
| `POST` | `/api/v1/proposals/{id}/reject` | 拒绝并记录原因 |
| `POST` | `/api/v1/proposals/batch-approve` | 批量批准 |
| `GET` | `/api/v1/audit` | 获取审计日志 |
| `GET` | `/api/v1/audit/summary` | 获取审计摘要 |
| `POST` | `/api/v1/audit/apply` | 执行已批准复制 |
| `POST` | `/api/v1/audit/apply-all` | 执行所有已批准复制 |

## 项目结构

```
local-screenshot-action-archive-agent/
├── app/
│   ├── api/              # FastAPI 路由和端点
│   │   ├── main.py       # 主应用
│   │   ├── scans.py      # 扫描 API
│   │   ├── search.py     # 搜索 API
│   │   ├── proposals.py  # 归档建议 API
│   │   └── audit.py      # 审计 API
│   ├── services/         # 业务逻辑服务
│   │   ├── scanner.py    # 目录扫描
│   │   ├── image_fingerprint.py  # 图像指纹
│   │   ├── duplicate_detector.py # 重复检测
│   │   ├── ocr_service.py       # OCR 服务
│   │   ├── extractor.py         # 规则提取
│   │   ├── index_store.py       # FTS 索引
│   │   ├── proposal_builder.py  # 归档建议生成
│   │   ├── file_operator.py     # 文件操作
│   │   ├── audit_service.py     # 审计服务
│   │   └── llm_service.py       # LLM 服务
│   ├── agent/            # Agent 编排逻辑
│   │   ├── orchestrator.py      # 状态图编排
│   │   └── graph_store.py       # Neo4j 图存储
│   ├── storage/          # 数据库和配置管理
│   │   ├── models.py     # 数据模型
│   │   ├── database.py   # 数据库管理
│   │   ├── workspace_config.py  # 工作区配置
│   │   └── llm_config.py        # LLM 配置
│   └── templates/        # HTML 模板
│       ├── scan_result.html     # 扫描结果页
│       ├── search.html          # 搜索页
│       ├── proposals.html       # 归档审批页
│       └── audit.html           # 审计日志页
├── tests/
│   ├── fixtures/         # 脱敏测试样例
│   ├── unit/             # 单元测试
│   └── integration/      # 集成测试
├── docs/                 # 项目文档
└── artifacts/            # 生成的产物
```

## 配置

### 工作区配置

工作区配置文件 `config.json` 示例：

```json
{
  "workspace_id": "my_workspace",
  "workspace_root": "/path/to/workspace",
  "allowed_directories": ["/path/to/screenshots"],
  "allowed_extensions": [".png", ".jpg", ".jpeg", ".webp"],
  "near_duplicate_threshold": 10,
  "ocr_enabled": true,
  "ocr_language": "ch",
  "local_model_enabled": false
}
```

### LLM 配置

支持两种 LLM 模式：

#### 1. Ollama（本地，推荐）

```bash
# 安装 Ollama
# https://ollama.com

# 拉取模型
ollama pull qwen2.5-vl:latest

# 设置环境变量
export LLM_PROVIDER=ollama
export LLM_BASE_URL=http://localhost:11434
export LLM_MODEL=qwen2.5-vl:latest
```

#### 2. OpenAI 兼容 API

```bash
# 设置环境变量
export LLM_PROVIDER=openai
export LLM_API_KEY=your_api_key_here
export LLM_BASE_URL=https://api.openai.com
export LLM_MODEL=gpt-4o
```

#### 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `ollama` | LLM 提供商（ollama/openai/custom） |
| `LLM_API_KEY` | `None` | API Key（Ollama 不需要） |
| `LLM_BASE_URL` | `http://localhost:11434` | API 基础 URL |
| `LLM_MODEL` | `qwen2.5-vl:latest` | 模型名称 |

## 隐私说明

- 所有处理在本地完成，不上传任何数据到云端
- 原始截图始终保留在用户指定目录
- 敏感信息（验证码、银行卡号等）自动掩码处理
- 公开演示仅使用脱敏样例

## 开发

```bash
# 激活环境
conda activate screenshot-agent

# 运行测试
pytest

# 代码格式化
black .
ruff check .

# 类型检查
mypy app/
```

## 许可证

MIT License
