# NPA Agent

NPA Agent 是一个本地优先的不良资产分析工作台，第一版聚焦个贷/消费贷资产包。它帮助 AMC、投资人、律所、电话调解/催收团队完成从 Excel 初筛到报告、执行计划和知识沉淀的本地闭环。

核心流程：

```text
上传资产包 Excel -> 自动字段识别 -> 画像/处置/报价分析 -> 报告 -> 执行计划 -> 知识库/私有 Skill 草稿
```

> 法律风险分析只作为辅助提示，不替代律师意见。报价分析只作为辅助判断，不构成投资建议。

## Alpha 本地版已支持

- 个贷/消费贷资产包 Excel 上传、字段自动识别和字段确认。
- 身份证、手机号、地址、本金、利息等完整度分析。
- 金额结构、债务人画像、触达能力、处置模式和三情景报价。
- 合同/条款 PDF、DOCX、TXT 基础风险解析：管辖、仲裁、送达、债转通知、时效、证据链、息费。
- 公司历史处置数据导入、基于公司历史的法院画像和报价校准。
- 银登公开 URL/公告文本手动解析。
- 国内模型 Provider 调用入口：DeepSeek、Qwen/百炼、自定义 OpenAI-compatible。
- 浏览器自带语音和 OpenAI-compatible 增强 TTS 基础入口。
- 处置执行工作台：批次、任务、话术、跟进、Excel 导出。
- 本地 Markdown 知识库和私有 Skill 草稿审核。
- 傻瓜式引导工作台：系统根据当前项目状态提示下一步。

## Beta main 已启动能力

- 多模态文档解析入口：PDF 文本层、图片型 PDF、PNG/JPG/WEBP、DOCX、TXT、HTML。
- 可选本地 OCR：安装 `requirements-ocr.txt` 及本机 `tesseract/poppler` 后，可解析扫描 PDF 和图片公告。
- 银登公告附件增强：公开 URL 页面发现 PDF/图片附件时，会尝试解析公开附件并合并公告线索。
- 判决书、执行文书、调解文书基础识别，并将线索并入报告、报价和执行计划。
- 安全与审计工作台：本地查看上传、解析、OCR、银登抓取、模型调用、语音调用、导出、知识库写入和私有 Skill 草稿等审计记录。
- 原文云端分析和原文敏感导出需要二次确认；审计日志只保存动作元数据和脱敏摘要，不保存完整敏感 prompt。

## 当前限制

这是本地 Alpha，不是生产级多用户 SaaS。以下能力已经预留接口、配置或路线图，但不代表完整生产能力：

- OCR 是本地可选能力，不默认云端识别；缺少依赖时会降级提示上传文本版或粘贴正文。
- 判决书、执行文书、调解记录为规则抽取基础版，复杂文书仍需人工/律师复核。
- 暂未接入 AgentMemory MCP。
- 语音不是完整实时 ASR 对话系统；浏览器语音可用性取决于用户浏览器，增强 TTS 需要用户自行配置兼容服务。
- 银登只支持用户输入公开 URL 或公告文本，不做登录、验证码绕过、全站爬虫或自动监控。
- 法院画像第一版主要来自公司历史数据，不接外部法院公开数据或商业司法数据源。
- 私有 Skill 只生成草稿并进入审核区，不会自动启用或参与分析调用链。
- 审计日志是本地可追溯记录，不是生产级合规系统、电子证据系统或多用户审批系统。
- 不做完整催收 CRM，不接真实外呼、短信、企微或自动触达系统。
- 法律风险分析只作为辅助提示，不替代律师意见；报价分析只作为辅助判断，不构成投资建议。

## 快速启动

```bash
make setup
make dev
```

如需本地 OCR：

```bash
.venv/bin/pip install -r requirements-ocr.txt
# macOS 示例：brew install tesseract tesseract-lang poppler
```

默认地址：

```text
http://127.0.0.1:8765
```

如果 `8765` 已被其他本地服务占用：

```bash
make dev PORT=8767
```

确认当前端口确实是 NPA Agent：

```bash
make smoke PORT=8767
```

或直接访问：

```bash
curl http://127.0.0.1:8767/api/health
```

返回里的 `app_name` 应为 `NPA Agent`。工作台顶部也会显示当前服务地址。

## Docker 启动

```bash
docker compose up --build
```

然后打开：

```text
http://127.0.0.1:8765
```

Docker 会把本地 `./data` 挂载到容器内 `/app/data`，数据库、上传文件、报告和知识库仍保存在本机。

如果宿主机 `8765` 被占用：

```bash
PORT=8876 docker compose up --build
```

然后打开 `http://127.0.0.1:8876`。

## 5 分钟跑通样例

1. 启动服务并打开工作台。
2. 点击 `新建分析项目`。
3. 上传 `samples/level1_basic.xlsx`。
4. 点击 `上传并识别字段`。
5. 确认字段映射。
6. 点击 `生成初筛报告`。
7. 生成报告后，点击 `生成执行计划`。

更详细的演示见 [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md)。

## 测试

```bash
make test
```

等价于：

```bash
node --check frontend/src/app.js
.venv/bin/python -m compileall backend tests
.venv/bin/python -m unittest discover -v
```

## 数据安全

默认本地优先。以下运行数据不应提交到 git：

- `data/app.sqlite`
- `data/uploads/`
- `data/reports/`
- `data/legal_docs/`
- `data/knowledge/`
- `data/private_skills/`
- `data/secrets/`
- `.env`

API Key 不应写入仓库。可参考 `.env.example`，真实配置请通过本地 UI 或本机环境文件管理。

高风险动作默认受控：

- 模型调用默认使用 `redacted_cloud`，原文云端 `original_cloud` 必须填写确认说明。
- 执行清单默认导出脱敏版，原文敏感导出必须填写确认说明。
- 审计记录会显示是否读取敏感数据、是否联网、是否写入长期记忆、是否导出原文。

更多说明见 [SECURITY.md](SECURITY.md)。

## 发布状态与路线图

- 当前差距盘点见 [docs/RELEASE_GAP_ANALYSIS.md](docs/RELEASE_GAP_ANALYSIS.md)。
- 后续路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。
- 发布前检查见 [docs/OPEN_SOURCE_RELEASE_CHECKLIST.md](docs/OPEN_SOURCE_RELEASE_CHECKLIST.md)。

## 项目结构

```text
backend/     本地 HTTP API、规则分析、存储、模型/语音网关
frontend/    原生 HTML/CSS/JS 工作台
templates/   标准 Excel 模板
samples/     可公开演示的样例 Excel
docs/        PRD、技术设计、样例报告、演示和发布检查清单
data/        本地运行数据，仅保留 .gitkeep
tests/       unittest 测试
```

## 开发与贡献

```bash
make setup
make test
make status
```

提交前请确认没有真实资产包、合同、手机号、身份证、地址、API Key、数据库或报告进入 staged files。

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。发布前检查见 [docs/OPEN_SOURCE_RELEASE_CHECKLIST.md](docs/OPEN_SOURCE_RELEASE_CHECKLIST.md)。

## 许可证

MIT License. See [LICENSE](LICENSE).
