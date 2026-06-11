# NPA Agent 技术设计 V0.1

> 状态：草案
> 依赖文档：`docs/NPA_AGENT_PRD_V0.1.md`
> 第一阶段目标：把 PRD、Excel 模板、样例资产包和报告样例转成可开发的工程骨架

## 1. 技术目标

MVP 需要实现一个本地优先的个贷/消费贷资产包分析工作台。

第一阶段不追求复杂云端 SaaS，而是先做：

```text
本地 Web 工作台
-> 上传 Excel
-> 字段自动识别
-> 字段确认
-> 标准化 LoanAccount
-> 数据完整度评分
-> 个贷画像分析
-> 处置模式建议
-> 三情景报价建议
-> 报告生成
-> 项目记录与审计
```

默认技术取向：

- 本地优先。
- 数据结构清晰。
- 模块边界明确。
- 规则引擎先行。
- LLM 能力通过模型网关后置接入。
- 每个结论都能追溯来源。

## 2. 推荐项目结构

```text
npa-agent/
  backend/
    app.py
    api/
      projects.py
      files.py
      analysis.py
      reports.py
      settings.py
    core/
      field_mapping.py
      excel_parser.py
      normalization.py
      privacy.py
      data_quality.py
      id_card.py
      profile_analyzer.py
      disposition.py
      pricing.py
      attribution.py
      report_writer.py
    skills/
      registry.py
      manifests/
        asset_package_excel_parser.yaml
        consumer_loan_profile_analyzer.yaml
        phone_mediation_strategy.yaml
        disposal_mode_selector.yaml
        npa_report_writer.yaml
        privacy_anonymizer.yaml
    storage/
      db.py
      files.py
      audit.py
    model_gateway/
      providers.py
      redaction.py
      router.py
    voice_gateway/
      providers.py
      router.py
    tests/
      test_field_mapping.py
      test_excel_parser.py
      test_privacy.py
      test_data_quality.py
      test_profile_analyzer.py
      test_report_writer.py

  frontend/
    index.html
    src/
      app.js
      api.js
      components/
        TaskButtons.js
        UploadPanel.js
        FieldMappingCard.js
        ReportView.js
        SettingsModelPanel.js
        SettingsVoicePanel.js
      styles.css

  data/
    app.sqlite
    uploads/
    reports/
    audit/

  templates/
    个贷资产包标准模板.xlsx

  samples/
    level1_basic.xlsx
    level2_profile.xlsx
    level3_court.xlsx

  docs/
    NPA_AGENT_PRD_V0.1.md
    NPA_AGENT_TECH_DESIGN_V0.1.md
    sample_reports/
      个贷资产包初筛报告样例.md
```

MVP 可以先用 Python 后端 + 原生前端。后续若复用 Bailongma/QuantDinger，可再升级为 Electron 或更完整 Agent Gateway。

## 3. 后端 API 契约

### 3.1 创建项目

```http
POST /api/projects
```

请求：

```json
{
  "name": "深圳个贷资产包样例",
  "asset_type": "consumer_loan"
}
```

响应：

```json
{
  "ok": true,
  "project": {
    "id": "prj_20260609_001",
    "name": "深圳个贷资产包样例",
    "asset_type": "consumer_loan",
    "status": "draft",
    "created_at": "2026-06-09T17:00:00+08:00"
  }
}
```

### 3.2 上传文件

```http
POST /api/projects/{project_id}/files
```

表单：

```text
file: .xlsx
file_type: asset_package_excel
```

响应：

```json
{
  "ok": true,
  "file": {
    "id": "file_001",
    "filename": "level2_profile.xlsx",
    "file_type": "asset_package_excel",
    "stored_path": "data/uploads/prj_001/file_001.xlsx",
    "sha256": "..."
  }
}
```

### 3.3 字段映射预览

```http
POST /api/projects/{project_id}/field-mapping/preview
```

请求：

```json
{
  "file_id": "file_001",
  "sheet_name": "Level2_画像触达"
}
```

响应：

```json
{
  "ok": true,
  "mapping": {
    "debtor_name_or_id": {
      "source_column": "姓名",
      "confidence": 0.93,
      "needs_confirmation": false
    },
    "id_card": {
      "source_column": "证件号码",
      "confidence": 0.94,
      "needs_confirmation": false
    },
    "phone": {
      "source_column": "联系电话",
      "confidence": 0.91,
      "needs_confirmation": false
    },
    "address": {
      "source_column": "居住地址",
      "confidence": 0.88,
      "needs_confirmation": false
    },
    "principal": {
      "source_column": "未偿本金",
      "confidence": 0.96,
      "needs_confirmation": false
    },
    "interest": {
      "source_column": "欠息",
      "confidence": 0.9,
      "needs_confirmation": false
    }
  },
  "unmapped_columns": [],
  "preview_rows": [
    {
      "debtor_name_or_id": "张伟",
      "id_card": "440305********1234",
      "phone": "138****5678",
      "address": "广东省深圳市南山区***",
      "principal": 18600,
      "interest": 940
    }
  ],
  "next_actions": ["confirm_field_mapping"]
}
```

### 3.4 确认字段映射

```http
POST /api/projects/{project_id}/field-mapping/confirm
```

请求：

```json
{
  "file_id": "file_001",
  "mapping": {
    "debtor_name_or_id": "姓名",
    "id_card": "证件号码",
    "phone": "联系电话",
    "address": "居住地址",
    "principal": "未偿本金",
    "interest": "欠息"
  }
}
```

响应：

```json
{
  "ok": true,
  "normalized_count": 12,
  "data_level": "Level 2",
  "warnings": []
}
```

### 3.5 运行分析

```http
POST /api/projects/{project_id}/analysis/run
```

请求：

```json
{
  "analysis_type": "consumer_loan_initial_screening",
  "safety_mode": "local_rules_only"
}
```

响应：

```json
{
  "ok": true,
  "job": {
    "id": "job_001",
    "status": "completed"
  },
  "report_id": "rpt_001"
}
```

MVP 可以同步完成分析，但 API 形态保留 job，方便后续异步文档解析和外部数据补全。

### 3.6 查询报告

```http
GET /api/projects/{project_id}/reports/latest
```

响应：

```json
{
  "ok": true,
  "report": {
    "id": "rpt_001",
    "format": "markdown",
    "summary": {
      "rating": "B",
      "recommendation": "进入初步尽调",
      "primary_strategy": "电话调解优先 + 高金额户攻坚"
    },
    "markdown": "# 个贷/消费贷资产包初筛报告..."
  }
}
```

### 3.7 模型配置

```http
GET /api/settings/model
POST /api/settings/model
```

保存内容：

```json
{
  "mode": "redacted_cloud",
  "provider": "auto",
  "model": "auto",
  "base_url": null,
  "api_key_present": true,
  "allow_original_sensitive_data": false
}
```

API Key 不在 GET 响应中返回明文。

### 3.8 语音配置

```http
GET /api/settings/voice
POST /api/settings/voice
```

保存内容：

```json
{
  "mode": "builtin_fallback",
  "enhanced_enabled": false,
  "asr_provider": "auto",
  "tts_provider": "auto",
  "sensitive_data_readout": "masked_only"
}
```

## 4. 核心 JSON 数据结构

### 4.1 Project

```json
{
  "id": "prj_001",
  "name": "Level2 样例资产包",
  "asset_type": "consumer_loan",
  "status": "draft",
  "created_at": "2026-06-09T17:00:00+08:00",
  "updated_at": "2026-06-09T17:05:00+08:00",
  "file_ids": ["file_001"],
  "latest_report_id": "rpt_001"
}
```

### 4.2 LoanAccount

```json
{
  "id": "acct_001",
  "project_id": "prj_001",
  "row_number": 2,
  "debtor_name_or_id": "张伟",
  "id_card": "440305199001011234",
  "phone": "13812345678",
  "address": "广东省深圳市南山区科技园",
  "principal": 18600,
  "interest": 940,
  "optional": {
    "contract_no": "HT-SZ-0001",
    "overdue_days": 420,
    "jurisdiction_court": "深圳市南山区人民法院",
    "remark": "手机号有效，适合首轮调解"
  },
  "derived": {
    "masked_name": "张*",
    "masked_id_card": "440305********1234",
    "masked_phone": "138****5678",
    "masked_address": "广东省深圳市南山区***",
    "age": 36,
    "age_band": "36-45",
    "gender": "male",
    "id_region": "广东省深圳市",
    "amount_band": "10000-30000"
  }
}
```

### 4.3 AnalysisReport

```json
{
  "id": "rpt_001",
  "project_id": "prj_001",
  "version": "0.1",
  "generated_at": "2026-06-09T17:10:00+08:00",
  "summary": {
    "rating": "B",
    "recommendation": "进入初步尽调",
    "primary_strategy": "电话调解优先 + 高金额户攻坚"
  },
  "metrics": {
    "account_count": 12,
    "principal_total": 335900,
    "interest_total": 15660,
    "average_principal": 27991.67,
    "data_completeness_score": 91
  },
  "source_attributions": [],
  "missing_inputs": [],
  "next_actions": []
}
```

## 5. 核心模块设计

### 5.1 excel_parser

职责：

- 读取 `.xlsx`。
- 识别 sheet。
- 提取表头。
- 提取行数据。
- 跳过空白行。

输入：

```python
parse_excel(file_path: str, sheet_name: str | None) -> RawSheet
```

输出：

```python
RawSheet(headers: list[str], rows: list[dict])
```

### 5.2 field_mapping

职责：

- 根据别名库和内容特征识别字段。
- 计算置信度。
- 标记是否需要用户确认。

输入：

```python
preview_mapping(raw_sheet: RawSheet) -> FieldMappingPreview
```

核心规则：

```text
>= 0.80 自动映射
0.55-0.80 弹确认
< 0.55 不映射
```

### 5.3 normalization

职责：

- 将原始行转成 LoanAccount。
- 解析金额。
- 生成缺失名称时的临时编号。
- 保留原始 row_number。

本金缺失时：

- 不生成完整分析。
- 返回 `missing_required_field`。

### 5.4 privacy

职责：

- 姓名、身份证、手机号、地址脱敏。
- 生成报告展示值。
- 防止日志写入敏感明文。

### 5.5 id_card

职责：

- 校验身份证格式。
- 解析出生年月。
- 解析性别。
- 解析年龄段。
- 根据行政区划库解析户籍地。

MVP 如果行政区划库不完整，至少解析前两位省级线索，并标注可信度。

### 5.6 data_quality

职责：

- 计算数据完整度。
- 判断数据等级。
- 生成缺失字段影响。

### 5.7 profile_analyzer

职责：

- 统计金额结构。
- 统计年龄结构。
- 统计性别结构。
- 统计地区线索。
- 统计手机号、身份证、地址覆盖率。

### 5.8 disposition

职责：

- 根据默认阈值选择处置模式。
- 输出主策略、备选策略、不建议策略。
- 生成电话调解分层。

### 5.9 pricing

职责：

- 输出保守、基准、乐观三情景。
- 根据数据完整度和触达能力修正区间。
- 标注不构成投资建议。

### 5.10 attribution

职责：

- 为每个结论添加来源。
- 区分事实、计算、规则推断、缺失假设。

### 5.11 report_writer

职责：

- 生成 Markdown 报告。
- 按固定章节组织。
- 插入来源说明。
- 插入下一步动作。

## 6. Skill Manifest 结构

Skill manifest 存在 `backend/skills/manifests/*.yaml`。

示例：

```yaml
name: asset_package_excel_parser
version: "0.1"
risk_level: low
description: "解析个贷/消费贷资产包 Excel，生成字段映射和标准化债权数据"
required_inputs:
  - asset_package_excel
optional_inputs:
  - sheet_name
permissions:
  read_local_files: true
  write_project_record: true
  network_access: false
  read_memory: false
  write_memory: false
  access_sensitive_data: true
outputs:
  - field_mapping_preview
  - normalized_loan_accounts
missing_input_prompts:
  asset_package_excel: "我还缺资产包 Excel，请上传债权清单。"
```

MVP 不做动态安装，只做内置 skill registry。

## 7. 前端工作台设计

### 7.1 页面区域

```text
顶部：项目名称、安全模式、模型状态、语音状态
左侧：任务按钮、历史项目
中间：对话和引导卡片
右侧：当前项目摘要、上传文件、下一步动作
主内容：报告视图
```

### 7.2 核心组件

#### TaskButtons

按钮：

- 分析资产包。
- 生成处置策略。
- 生成电话调解话术。
- 查看历史项目。

#### UploadPanel

功能：

- 上传 Excel。
- 下载标准模板。
- 显示文件状态。

#### FieldMappingCard

功能：

- 显示自动识别字段。
- 高置信度字段默认确认。
- 低置信度字段允许用户选择。
- 显示无法识别字段。

#### ReportView

功能：

- 显示老板摘要。
- 显示详细指标。
- 显示数据来源。
- 显示下一步动作。

#### SettingsModelPanel

功能：

- 输入 API Key。
- 自动识别 provider。
- 选择安全模式。
- 显示原文云端风险提示。

#### SettingsVoicePanel

功能：

- 使用自带语音。
- 配置增强语音。
- 设置敏感数据播报策略。

## 8. 存储设计

MVP 使用 SQLite + 本地文件。

### 8.1 表结构草案

```sql
projects(id, name, asset_type, status, created_at, updated_at, latest_report_id)
files(id, project_id, filename, file_type, stored_path, sha256, created_at)
field_mappings(id, project_id, file_id, mapping_json, confidence_json, created_at)
loan_accounts(id, project_id, row_number, data_json, derived_json, created_at)
analysis_reports(id, project_id, version, markdown, data_json, created_at)
audit_logs(id, project_id, event_type, event_json, created_at)
settings(key, value_json, updated_at)
skill_calls(id, project_id, skill_name, permissions_json, input_summary_json, output_summary_json, created_at)
```

### 8.2 文件存储

```text
data/uploads/{project_id}/{file_id}.xlsx
data/reports/{project_id}/{report_id}.md
data/audit/{date}.jsonl
```

敏感原文只保存在本地，不进入普通日志。

## 9. 错误与边界处理

### 9.1 缺少本金

返回：

```json
{
  "ok": false,
  "code": "missing_required_field",
  "message": "缺少本金字段，无法完成资产包金额分析。",
  "next_actions": ["confirm_field_mapping", "upload_template"]
}
```

### 9.2 无法识别 Excel

返回：

```json
{
  "ok": false,
  "code": "unsupported_excel_format",
  "message": "无法读取该 Excel，请确认文件未加密且格式为 .xlsx。",
  "next_actions": ["upload_xlsx", "download_template"]
}
```

### 9.3 低置信度字段

不报错，进入字段确认流程。

### 9.4 敏感信息外发

默认拒绝原文外发，必须用户确认。

## 10. 测试映射

### 10.1 level1_basic.xlsx

验证：

- 本金字段识别。
- 债务人编号识别。
- Level 1 数据等级。
- 缺身份证、手机号、地址提示。
- 低数据完整度处置建议。

### 10.2 level2_profile.xlsx

验证：

- 非标准字段别名识别。
- 身份证解析。
- 手机号完整度。
- 地址完整度。
- 年龄、性别、地区画像。
- 电话调解优先策略。

### 10.3 level3_court.xlsx

验证：

- 合同编号识别。
- 管辖法院识别。
- 法院集中度初判。
- 电话调解 + 重点户攻坚组合策略。
- 报告接近 `docs/sample_reports/个贷资产包初筛报告样例.md`。

## 11. 与现有项目的复用边界

### 11.1 Bailongma

可借鉴：

- 语音配置和语音面板。
- 云端 ASR WebSocket 代理。
- 流式 TTS provider。
- 本地 Whisper 进程管理。
- ACUI 卡片式配置体验。
- 记忆系统和焦点管理思想。

MVP 不直接复制全部 Bailongma 主循环，避免把不良资产工作台复杂化。

### 11.2 QuantDinger

可借鉴：

- Agent Gateway 思想。
- 权限分级。
- 审计日志。
- 异步 job。
- MCP/REST 双入口。

MVP 可先做轻量本地 API，后续再演进为完整 Agent Gateway。

## 12. 开发顺序建议

1. 搭建后端项目和 SQLite。
2. 实现 Excel 解析与字段映射。
3. 实现标准化 LoanAccount。
4. 实现脱敏和身份证解析。
5. 实现数据完整度和画像分析。
6. 实现处置模式和报价规则。
7. 实现 Markdown 报告生成。
8. 实现前端上传、字段确认、报告视图。
9. 接入模型配置占位。
10. 接入语音配置占位。
