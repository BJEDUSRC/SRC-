# SRC脱敏标注数据管理系统

基于大模型的 SRC（安全应急响应中心）脱敏标注数据管理系统，用于 PDF 文档的智能转换、数据脱敏与文档管理。

## 项目概述

本系统用于管理 SRC 相关 PDF 文档，提供以下核心能力：

- **PDF 转换**：将 PDF 转为 Markdown，保留结构与图片引用
- **数据脱敏**：基于大模型对文档内容进行智能脱敏（仅 LLM，无正则）
- **文档管理**：上传、查重、标签、漏洞等级自动标注、查询、下载、删除
- **查询与筛选**：关键词全文搜索、漏洞等级/标签/时间等筛选，结果实时更新

## 功能模块

### 1. PDF 转换

| 功能 | 说明 |
|------|------|
| 文本与表格解析 | 使用 PyMuPDF 解析 PDF 文本与表格 |
| Markdown 输出 | 转换为结构化 Markdown，尽量保留层级与格式 |
| 图片提取 | 提取内嵌图片，单独保存并在 MD 中生成引用 |
| 单文件/批量 | 支持单文件上传与文件夹批量上传（仅处理 PDF） |

图片规则：提取后保存至 `converted/{doc_id}/` 下，命名含页码与序号，在 MD 中以相对路径引用。

### 2. 数据脱敏

- **方式**：仅使用大模型（LangChain + OpenAI 兼容接口）进行识别与脱敏，不使用正则规则。
- **敏感类型**：由模型识别并脱敏，如 IP、身份证、手机、邮箱、姓名、地址、银行卡、URL 参数、内网域名等。
- **入口**：上传时可勾选"脱敏"；首页提供独立"数据脱敏"页，支持文本与 MD 文件脱敏。
- **约束**：启用脱敏时，若 LLM 不可用则禁止上传；脱敏失败则不会保存未脱敏文档。
- **URL 跨文档脱敏映射**：自动记录 URL 路径段的脱敏映射关系，确保不同文档中相同 URL 路径段脱敏结果一致。映射表采用 FIFO 策略，最大 1000 条记录。

### 3. 文档上传与入库

| 功能 | 说明 |
|------|------|
| 单文件上传 | 上传单个 PDF，可选脱敏与标签 |
| 文件夹批量上传 | 选择文件夹，仅处理其中 PDF，重复文件名跳过 |
| 文件名查重 | 按原始文件名查重，重复则提示并拒绝/跳过 |
| 标签 | 上传时可填写标签（逗号分隔） |
| 漏洞等级自动标注 | 入库时从内容中识别“等级：严重/高危/中危”等并自动打等级标签 |

### 4. 查询文档

| 功能 | 说明 |
|------|------|
| 全文搜索 | 关键词搜索文件名与内容 |
| 文件名 | 文件名模糊匹配 |
| 上传时间 | 开始/结束日期范围 |
| 脱敏状态 | 已脱敏 / 未脱敏 |
| 漏洞等级 | 严重、高危、中危、其他（基于自动标注的标签） |
| 标签 | 多标签筛选（逗号分隔） |
| 排序 | 按上传时间、文件名、大小、图片数排序，升序/降序 |
| 实时筛选 | 修改任意筛选条件后自动刷新结果，无需点击“搜索” |
| 删除 | 单条删除、批量删除（含关联文件与记录） |

### 5. 下载与统计

| 功能 | 说明 |
|------|------|
| 单文档下载 | 仅 MD 或 MD+图片 ZIP |
| 批量下载 | 勾选多文档打包 ZIP 下载 |
| 下载记录 | 记录单次/批量下载日志 |

### 6. 漏洞等级

- **等级**：严重、高危、中危、其他。
- **来源**：从文档内容中识别“等级：中危”“等级：高危”等表述并打标签。
- **查询**：查询页提供“漏洞等级”下拉筛选。
- **批量标注**：可通过接口对已有文档批量提取等级并打标签（见 API 说明）。

## 技术架构

### 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | FastAPI |
| 前端 | Bootstrap 5 + 原生 JS |
| 数据库 | MySQL 8.0+ |
| ORM | SQLAlchemy |
| PDF | PyMuPDF (fitz) |
| 脱敏/LLM | LangChain 1.x，OpenAI 兼容 API |
| 模板 | Jinja2 |

### 系统结构示意

```
┌─────────────────────────────────────────────────────────────────┐
│                          前端页面                                 │
│  首页 │ PDF转换 │ 上传文档 │ 查询文档 │ 数据脱敏 │ 下载记录        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端 (API v1)                        │
│  /api/v1/upload  /api/v1/documents  /api/v1/download            │
│  /api/v1/convert  /api/v1/desensitize  /api/v1/vulnerability-level │
│         │                                                         │
│  PDF转换 │ 脱敏服务(LLM) │ 文档服务 │ 查询服务 │ 漏洞等级服务      │
│         │                                                         │
│  MySQL (文档/标签/图片/下载日志) │ 文件存储 (converted, uploads)   │
└─────────────────────────────────────────────────────────────────┘
```

## 目录结构

```
SRCDataManage/
├── app/
│   ├── main.py              # 应用入口
│   ├── config.py            # 配置（含 DB、LLM、文件路径）
│   ├── database.py         # 数据库连接与初始化
│   ├── api/
│   │   ├── web.py           # 页面路由
│   │   ├── upload.py        # 上传 API
│   │   ├── query.py         # 文档查询与删除 API
│   │   ├── download.py      # 下载 API
│   │   ├── convert.py       # PDF 转换 API
│   │   ├── desensitize_api.py      # 脱敏 API
│   │   └── vulnerability_level_api.py  # 漏洞等级标注 API
│   ├── models/
│   │   └── document.py      # 文档、图片、标签、下载日志、URL映射模型
│   ├── schemas/
│   │   └── document.py      # 请求/响应模型
│   ├── services/
│   │   ├── pdf_converter.py       # PDF 转 MD
│   │   ├── image_extractor.py     # 图片提取
│   │   ├── desensitizer.py        # 脱敏（LLM）
│   │   ├── llm_service.py          # LLM 调用
│   │   ├── document_service.py    # 文档入库与流程
│   │   ├── query_service.py       # 查询与删除
│   │   ├── download_service.py   # 下载与打包
│   │   ├── file_service.py        # 文件操作
│   │   ├── url_desensitization_service.py  # URL跨文档脱敏映射
│   │   └── vulnerability_level_service.py  # 漏洞等级提取与标签
│   ├── templates/           # Jinja2 页面
│   └── utils/               # 工具与日志
├── converted/               # 转换后的 MD 与图片（按文档 ID 分目录）
├── uploads/                 # 上传临时目录
├── logs/                    # 日志
├── requirements.txt
├── run.py                   # 启动脚本
├── init_database.py         # 数据库初始化脚本
├── .env.example             # 环境变量示例
└── README.md
```

## 环境要求

- Python 3.9+
- MySQL 8.0+
- 可访问的 LLM 服务（OpenAI 或兼容接口，用于脱敏）

## 安装与运行

### 1. 克隆与虚拟环境

```bash
git clone <repository-url>
cd SRCDataManage
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 数据库

```sql
CREATE DATABASE src_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 创建用户并授权（按需修改用户名与密码）
```

### 4. 环境变量

复制 `.env.example` 为 `.env` 并填写：

```env
# 数据库
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=src_data

# LLM（脱敏必填；不配置则无法使用脱敏与"启用脱敏"的上传）
LLM_API_KEY=your_api_key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# 脱敏配置
# 是否在脱敏输出中包含LLM的思考过程（true: 显示，用于调试；false: 不显示，生产环境推荐）
SHOW_LLM_THINKING_PROCESS=False

# 可选
UPLOAD_DIR=./uploads
CONVERTED_DIR=./converted
MAX_FILE_SIZE=52428800
DEBUG=True
```

### 5. 初始化与启动

```bash
# 初始化表（DEBUG 时 main 也会执行）
python -c "from app.database import init_db; init_db()"

# 启动
python run.py
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：http://localhost:8000  
API 文档（DEBUG 时）：http://localhost:8000/docs

## 主要 API（v1）

| 用途 | 方法 | 路径 |
|------|------|------|
| 文档列表/查询 | GET | `/api/v1/documents/` |
| 文档详情 | GET | `/api/v1/documents/{id}` |
| 删除文档 | DELETE | `/api/v1/documents/{id}` |
| 批量删除 | POST | `/api/v1/documents/batch-delete` |
| 上传 | POST | `/api/v1/upload/` |
| 批量上传 | POST | `/api/v1/upload/batch` |
| 单文档下载 | GET | `/api/v1/download/{id}` |
| 批量下载 | POST | `/api/v1/download/batch` |
| 脱敏（文本/文件） | POST | `/api/v1/desensitize/...` |
| 漏洞等级批量提取 | POST | `/api/v1/vulnerability-level/batch-extract` |
| 单文档等级提取 | POST | `/api/v1/vulnerability-level/extract/{id}` |

查询参数示例：`keyword`、`filename`、`start_date`、`end_date`、`tags`、`is_desensitized`、`vulnerability_level`（严重/高危/中危/其他）、`page`、`page_size`、`sort_by`、`sort_order`。

## 许可证

MIT License

## 联系方式

如有问题，请通过项目 Issue 或联系维护人员。
