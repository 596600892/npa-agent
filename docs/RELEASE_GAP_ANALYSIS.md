# NPA Agent 发布前差距盘点

> 状态：Alpha 发布候选盘点
> 日期：2026-06-11
> 目标：把当前实现与 PRD 的 P0/P1/P2 对齐，明确哪些可作为 Alpha 能力发布，哪些只能写入路线图。

## 1. 结论

当前版本已经具备本地 Alpha 的主闭环：

`上传资产包 Excel -> 字段识别 -> 分析报告 -> 执行计划 -> 知识沉淀 -> 私有 Skill 草稿`

发布判断：

- P0 MVP 主闭环基本完成，可作为 Alpha 发布候选。
- P1 多数能力已有基础版，但合同文书、模型、语音、知识库仍有明确限制。
- P2 仅完成私有 Skill 草稿和开源交付基线，其他平台化能力不应作为当前发布承诺。
- 开源发布前的关键工作不是继续加功能，而是确认样例流程、文档边界、安全忽略规则和 release notes。

## 2. P0 MVP 差距矩阵

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| 个贷/消费贷资产包 Excel 上传 | Done | 前端上传区、`/api/projects/{id}/files`、样例 Excel、API 集成测试 | 只支持 `.xlsx`，不支持 `.xls/.csv` | 可发布，说明格式限制 | P0 |
| Excel 字段自动识别与映射 | Done | `field_mapping`、字段确认卡、核心管线测试 | 行业非标准字段仍需继续积累别名 | 可发布，提示低置信度需人工确认 | P0 |
| 字段低置信度确认 | Done | 前端字段确认、`field-mapping/confirm` | 尚无复杂冲突解释 | 可发布 | P0 |
| 基础字段模板 | Done | `templates/个贷资产包标准模板.xlsx` | 模板说明可继续增强 | 可发布 | P0 |
| 本金必填校验 | Done | `normalization`、错误测试 | 无 | 可发布 | P0 |
| 债务人名称可用编号替代 | Done | 标准字段和样例覆盖 | 无 | 可发布 | P0 |
| 身份证解析年龄、性别、地区 | Done | `id_card`、画像分析测试 | 行政区划库为基础规则，不是完整权威库 | 可发布，注明地区线索限制 | P0 |
| 缺身份证替代分析 | Done | 数据可用性分层、报告缺失提示 | 替代字段置信度较低 | 可发布，报告已说明可信度 | P0 |
| 手机号/地址/身份证完整度 | Done | `data_quality`、`profile_analyzer` | 手机号仅格式和覆盖率，不代表真实触达 | 可发布 | P0 |
| 金额分布、户均本金、高金额户占比 | Done | 报告生成和样例测试 | 规则阈值仍为默认值 | 可发布 | P0 |
| 数据可用性 Level 1-3 | Done | 核心报告、样例 Level 1-3 | Level 4/5 依赖历史和外部数据 | 可发布，勿承诺外部增强 | P0 |
| 处置模式初判 | Done | `disposition`、报告章节 | 规则引擎仍需历史数据校准 | 可发布 | P0 |
| 电话调解策略与合规话术 | Done | `phone_mediation_strategy` manifest、执行计划话术 | 不接真实电话/短信系统 | 可发布，定位为策略辅助 | P0 |
| 三情景报价建议 | Done | `pricing`、报告报价章节 | 不做复杂 IRR，不构成投资建议 | 可发布，保留免责声明 | P0 |
| 报告输出 | Done | Markdown 报告、来源说明、报告测试 | 可继续美化导出格式 | 可发布 | P0 |
| 项目记录 | Done | SQLite 表、项目/文件/报告记录 | 无多用户协作 | 可发布为本地单机 | P0 |
| 敏感字段脱敏 | Done | `privacy`、报告和导出测试 | 仍需避免用户手动复制明文到公开材料 | 可发布 | P0 |
| 基础审计日志 | Partial | 数据库表和部分调用留痕 | 尚未形成完整可视化审计页 | Alpha 可发布，说明为基础留痕 | P1 |

P0 发布门槛：样例闭环、测试、健康检查、安全忽略规则必须全部通过。

## 3. P1 增强差距矩阵

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| 合同解析 | Partial | PDF/DOCX/TXT 文本提取、合同风险分析、测试 | PDF 仅可复制文本，不做 OCR | 可作为 Alpha 基础版发布 | P1 |
| 判决书/执行文书解析 | Not Started | 无专门解析器 | 缺文书类型识别、裁判要点、执行结果抽取 | 不应对外宣传已支持 | P1 |
| 管辖、仲裁、送达条款提取 | Done | `contract_risk_analyzer`、合同测试 | 规则抽取，复杂条款需人工复核 | 可发布为辅助提示 | P1 |
| 债权转让通知、诉讼时效风险 | Partial | 合同风险规则已有线索识别 | 保证期间和时效精确判断仍需材料和律师复核 | 可发布为风险线索，不写成法律结论 | P1 |
| 法院画像 | Partial | 公司历史数据聚合和法院画像 API | 未接外部法院公开数据 | 可发布为“基于公司历史数据” | P1 |
| 公司历史处置数据上传 | Done | 历史模板、导入 API、测试 | 样本质量依赖用户数据 | 可发布 | P1 |
| 历史数据校准评分 | Partial | 报价校准和法院画像 | 样本不足时不强行校准，规则仍简单 | 可发布为辅助校准 | P1 |
| 银登公告手动解析 | Done | URL 抓取、文本解析、创建项目测试 | 不做登录、验证码、全站爬虫 | 可发布，边界必须明确 | P1 |
| Obsidian 风格知识库 | Partial | 本地 Markdown vault 和搜索 API | 不自动写入用户已有 Obsidian vault | 可发布为本地 Markdown 知识库 | P1 |
| AgentMemory MCP 接入 | Not Started | 仅有本地记忆候选设计 | 未接外部 MCP | 不应对外宣传已支持 | P1 |
| 增强语音 | Partial | 浏览器语音、OpenAI-compatible TTS 网关 | 未接 BaiLongma 完整实时 ASR/WebSocket/打断 | 可发布为双轨基础版 | P1 |
| 模型 AI 调用 | Partial | DeepSeek、Qwen、自定义 OpenAI-compatible Chat Completions | 不做自动模型探测；真实调用依赖用户 Key | 可发布，写清需用户配置 | P1 |

P1 发布门槛：所有 Partial 能力必须在 README 中写清限制，不得用“完整支持”表述。

## 4. P2 平台化差距矩阵

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| 银登自动监控 | Not Started | 仅手动 URL 抓取 | 缺定时监控、去重、播报和合规抓取策略 | 放入 Roadmap | P2 |
| 行业新闻和公告播报 | Not Started | 无专门新闻源 | 缺信息源配置、摘要、播报队列 | 放入 Roadmap | P2 |
| 外部商业数据源 | Not Started | 无天眼查/司法/房产等接口 | 缺 provider、费用、合规和缓存策略 | 放入 Roadmap | P2 |
| GitHub/community Skill 安装治理 | Not Started | 仅内置 manifests | 缺版本锁定、沙箱、来源校验和禁用机制 | 放入 Roadmap | P2 |
| 公司私有 Skill 草稿 | Done | 私有草稿生成、审核 API、测试 | Approved 后仍不参与分析调用链 | 可发布为“草稿与审核” | P2 |
| 多角色权限 | Not Started | 单机本地服务 | 缺用户、角色、团队空间和授权策略 | 不作为 Alpha 范围 | P2 |
| 完整催收 CRM | Not Started | 仅轻量执行工作台 | 缺真实外呼、短信、企微、案件队列、质检 | 不作为 Alpha 范围 | P2 |

P2 发布门槛：README 只写路线图，不写成当前功能。

## 5. 开源交付状态

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| MIT License | Done | `LICENSE` | 无 | 可发布 | P0 |
| 快速启动 | Done | `Makefile`、README | 需最终人工按 README 走一遍 | 发布前检查 | P0 |
| Docker 启动 | Done | `Dockerfile`、`docker-compose.yml` | 不是生产级 SaaS 部署 | 可发布为本地容器方案 | P0 |
| 健康检查 | Done | `/api/health`、`make smoke` | 无 | 可发布 | P0 |
| 贡献指南 | Done | `CONTRIBUTING.md` | 后续可加 issue/PR 模板 | 可发布 | P1 |
| 安全文档 | Done | `SECURITY.md` | 后续可加漏洞报告邮箱 | 可发布 | P1 |
| 发布检查清单 | Done | `docs/OPEN_SOURCE_RELEASE_CHECKLIST.md` | 需加入本差距盘点和 Roadmap 核对 | 本轮补齐 | P0 |
| Demo walkthrough | Done | `docs/DEMO_WALKTHROUGH.md` | 需最终浏览器 smoke 对齐按钮文案 | 发布前检查 | P0 |

## 6. 安全合规状态

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| 本地优先 | Done | SQLite、本地 `data/`、Docker volume | 无 | 可发布 | P0 |
| 运行数据 ignored | Done | `.gitignore`、`.gitkeep` | 发布前需复查 staged | 可发布 | P0 |
| API Key 不返回明文 | Done | settings/secret 分离和测试 | 本地存储仍需用户保护机器 | 可发布 | P0 |
| 云模型脱敏默认 | Done | `redacted_cloud`、敏感替换 | 脱敏不是法律意义匿名化 | 可发布，写明限制 | P0 |
| 原文云端二次确认 | Partial | 网关有确认字段 | UI 流程仍可更细 | Alpha 可发布，继续增强 | P1 |
| 审计日志 | Partial | 基础表和部分调用记录 | 缺统一审计视图 | Alpha 可发布，说明基础留痕 | P1 |
| 法律/投资免责声明 | Done | README、报告、PRD | 无 | 可发布 | P0 |

## 7. 用户体验状态

| 能力 | 状态 | 当前证据 | 主要缺口 | 发布影响 | 优先级 |
|---|---|---|---|---|---|
| 引导式主流程 | Done | `deriveGuidanceState`、工作台步骤 | 复杂错误恢复仍可优化 | 可发布 | P0 |
| 专家区折叠 | Done | 前端辅助能力区 | 无 | 可发布 | P0 |
| 关键按钮禁用原因 | Partial | 多数流程已有提示 | 少数失败仍用通用错误 | Alpha 可发布 | P1 |
| 错误提示下一步 | Partial | API `next_actions`、部分 UI 状态 | 前端统一错误卡可继续增强 | Alpha 可发布 | P1 |
| 移动端体验 | Partial | CSS 有响应式基础 | 未做完整移动端验收矩阵 | 可发布为桌面优先 Alpha | P2 |

## 8. Alpha 发布前最小清单

必须完成：

1. README 明确 Alpha 能力边界和当前限制。
2. Roadmap 明确未完成能力，避免误导开源用户。
3. 运行完整测试：`make test`。
4. 运行健康检查：`make dev PORT=8767` + `make smoke PORT=8767`。
5. 按 `docs/DEMO_WALKTHROUGH.md` 人工跑通 5 分钟样例。
6. 检查 `git status --short --ignored`，确认运行数据和敏感信息未 staged。
7. 准备 baseline commit、tag 和 release notes。

建议但不阻塞 Alpha：

1. 增加 issue/PR 模板。
2. 增加端到端浏览器自动 smoke。
3. 增加更多非标准 Excel 字段样例。
4. 增加合同扫描件 OCR 方案设计。
5. 增加公开演示截图，但只能使用样例数据。
