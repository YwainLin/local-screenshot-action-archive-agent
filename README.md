# 本地截图行动归档 Agent

一个默认离线运行的桌面文件整理 Agent，通过图像去重、OCR 和规则提取，将截图整理为可检索信息和行动建议。

## 功能特性

- **只读扫描**：安全扫描用户指定目录，不修改原文件
- **图像去重**：SHA-256 完全重复 + pHash 近似重复检测
- **本地 OCR**：使用 PaddleOCR/Tesseract 进行文字识别
- **规则提取**：自动识别日期、链接、金额、行动词等
- **归档建议**：生成待审批的归档计划，用户完全控制
- **审计日志**：所有文件操作可追溯

## 安装

```bash
# 克隆仓库
git clone https://github.com/YwainLin/local-screenshot-action-archive-agent.git
cd local-screenshot-action-archive-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 可选：安装 OCR 支持
pip install paddleocr paddlepaddle

# 可选：安装图数据库支持
pip install neo4j neo4j-graphrag
```

## 快速开始

```bash
# 启动服务
uvicorn app.api.main:app --reload

# 访问 Web 界面
open http://localhost:8000
```

## 项目结构

```
local-screenshot-action-archive-agent/
├── app/
│   ├── api/          # FastAPI 路由和端点
│   ├── services/     # 业务逻辑服务
│   ├── agent/        # LangGraph 编排逻辑
│   ├── storage/      # 数据库和配置管理
│   └── templates/    # Jinja2 模板
├── tests/
│   ├── fixtures/     # 脱敏测试样例
│   ├── unit/         # 单元测试
│   └── integration/  # 集成测试
├── docs/             # 项目文档
└── artifacts/        # 生成的产物
```

## 配置

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

## 隐私说明

- 所有处理在本地完成，不上传任何数据到云端
- 原始截图始终保留在用户指定目录
- 敏感信息（验证码、银行卡号等）自动掩码处理
- 公开演示仅使用脱敏样例

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

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
