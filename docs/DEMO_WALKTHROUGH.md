# Demo Walkthrough

This walkthrough uses only sample data committed to the repository.

## 1. Start The App

```bash
make setup
make dev PORT=8767
```

Open:

```text
http://127.0.0.1:8767
```

Check:

```bash
make smoke PORT=8767
```

The health response should identify `NPA Agent`.

## 2. Create A Project

On the guided workbench, click `新建分析项目`.

The recommendation card should move to `上传资产包 Excel`.

## 3. Upload A Sample Excel

Upload:

```text
samples/level1_basic.xlsx
```

Click `上传并识别字段`.

The system should identify `债务人编号` and `本金`, and explain that ID card, phone, address, and interest are missing optional fields.

## 4. Confirm Field Mapping

Click `确认字段映射`.

The recommendation card should move to `生成初筛报告`.

## 5. Generate Report

Click `生成初筛报告`.

The report preview should include:

- 结论摘要
- 资产包基础情况
- 数据完整度
- 债务人画像
- 处置模式建议
- 报价建议
- 数据来源说明

## 6. Generate Execution Plan

Click `生成执行计划`.

The expert area contains the execution workbench with task batches, masked debtor names, suggested actions, scripts, and export.

## 7. Optional Enhancements

Open `辅助能力 / 专家区` to try:

- 银登公告解析
- 公司历史数据校准
- 合同/文书风险
- AI 辅助摘要或话术
- 知识库记忆
- 私有 Skill 草稿

All runtime output stays under `data/` and is ignored by git.
