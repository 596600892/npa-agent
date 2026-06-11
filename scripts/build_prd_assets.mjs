import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "npa_agent_prd_assets");

const baseHeaders = [
  "债务人名称",
  "债务人编号",
  "身份证号",
  "手机号",
  "地址",
  "本金",
  "利息",
  "逾期天数",
  "合同编号",
  "管辖法院",
  "备注",
];

const fieldGuideRows = [
  ["字段名", "是否必填", "类型", "说明", "缺失影响"],
  ["债务人名称", "否", "文本", "债务人姓名；没有姓名时可用债务人编号替代", "不能做人名脱敏展示，报告以编号展示"],
  ["债务人编号", "否", "文本", "内部编号、客户编号、借据编号均可", "与债务人名称二选一；两者都缺时系统自动用行号生成编号"],
  ["身份证号", "否", "文本", "用于年龄、性别、户籍地分析", "无法准确做身份证画像，使用年龄/性别/地址替代"],
  ["手机号", "否", "文本", "用于触达率、电话调解可行性分析", "电话调解评分下降"],
  ["地址", "否", "文本", "户籍、居住或通讯地址均可", "地区集中度可信度下降"],
  ["本金", "是", "数值", "未偿本金、本金余额、债权本金均可", "无法完成资产包金额分析，必须确认或补充"],
  ["利息", "否", "数值", "欠息、罚息、利息余额均可", "只按本金做分析，报价保守"],
  ["逾期天数", "否", "数值", "用于判断催收阶段和诉讼时效线索", "无法判断逾期结构"],
  ["合同编号", "否", "文本", "用于关联合同或文书", "无法做合同文件匹配"],
  ["管辖法院", "否", "文本", "合同约定或案件法院", "无法判断诉讼集中度"],
  ["备注", "否", "文本", "其他线索", "仅作为辅助文本"],
];

const aliasRows = [
  ["标准字段", "可识别别名"],
  ["债务人名称", "债务人名称、债务人姓名、客户名称、客户姓名、姓名、借款人、借款人姓名、主借人、借据人"],
  ["债务人编号", "债务人编号、客户编号、借款人编号、资产编号、案件编号、借据编号、账户编号"],
  ["身份证号", "身份证、身份证号、身份证号码、证件号码、证件号、证件编号、身份证件号"],
  ["手机号", "手机号、手机号码、联系电话、联系方式、电话、移动电话、借款人电话"],
  ["地址", "地址、户籍地址、居住地址、通讯地址、联系地址、家庭住址、现住址"],
  ["本金", "本金、本金余额、未偿本金、剩余本金、债权本金、贷款本金、逾期本金、本金合计"],
  ["利息", "利息、欠息、罚息、利息余额、逾期利息、利罚息、息费、费用"],
];

const templateRows = [
  baseHeaders,
  ["张三", "CL-0001", "440305199001011234", "13812345678", "广东省深圳市南山区科技园", 18600, 940, 420, "HT-2023-0001", "深圳市南山区人民法院", "示例行，可删除"],
  ["李四", "CL-0002", "430102198706156789", "13987654321", "湖南省长沙市芙蓉区", 9200, 360, 210, "HT-2023-0002", "长沙市芙蓉区人民法院", "示例行，可删除"],
];

const level1Rows = [
  ["债务人编号", "本金"],
  ["L1-0001", 3800],
  ["L1-0002", 12600],
  ["L1-0003", 5400],
  ["L1-0004", 20800],
  ["L1-0005", 7600],
  ["L1-0006", 45200],
  ["L1-0007", 3100],
  ["L1-0008", 9800],
  ["L1-0009", 18400],
  ["L1-0010", 6300],
  ["L1-0011", 112000],
  ["L1-0012", 26500],
];

const level2Rows = [
  ["姓名", "证件号码", "联系电话", "居住地址", "未偿本金", "欠息"],
  ["张伟", "440305199001011234", "13812345678", "广东省深圳市南山区科技园", 18600, 940],
  ["王芳", "420106198803223456", "13622223333", "湖北省武汉市武昌区中南路", 9200, 360],
  ["李娜", "430102199510017654", "13788889999", "湖南省长沙市芙蓉区五一大道", 12800, 520],
  ["刘强", "510104198512126543", "13566667777", "四川省成都市锦江区春熙路", 31000, 1600],
  ["陈敏", "320106199207084321", "13900001111", "江苏省南京市鼓楼区中央路", 7400, 210],
  ["杨磊", "330102198011118888", "", "浙江省杭州市上城区", 56000, 2800],
  ["赵静", "440104199906306666", "18812340000", "广东省广州市越秀区", 4800, 120],
  ["周杰", "", "15811112222", "广西壮族自治区南宁市青秀区", 22000, 870],
  ["吴婷", "610104199304055555", "17799990000", "陕西省西安市莲湖区", 16300, 650],
  ["郑凯", "370102198908097777", "15655556666", "", 39000, 2100],
  ["孙梅", "110105197912313333", "18622221111", "北京市朝阳区", 112000, 5300],
  ["黄鹏", "350102199601028888", "15288889999", "福建省福州市鼓楼区", 6800, 190],
];

const level3Rows = [
  ["客户名称", "客户编号", "身份证号码", "手机号码", "通讯地址", "本金余额", "利息余额", "逾期天数", "合同编号", "约定管辖法院", "备注"],
  ["张伟", "L3-0001", "440305199001011234", "13812345678", "广东省深圳市南山区科技园", 18600, 940, 420, "HT-SZ-0001", "深圳市南山区人民法院", "手机号有效，适合首轮调解"],
  ["王芳", "L3-0002", "420106198803223456", "13622223333", "湖北省武汉市武昌区中南路", 9200, 360, 210, "HT-SZ-0002", "深圳市南山区人民法院", ""],
  ["李娜", "L3-0003", "430102199510017654", "13788889999", "湖南省长沙市芙蓉区五一大道", 12800, 520, 330, "HT-SZ-0003", "深圳市南山区人民法院", ""],
  ["刘强", "L3-0004", "510104198512126543", "13566667777", "四川省成都市锦江区春熙路", 31000, 1600, 680, "HT-SZ-0004", "深圳市南山区人民法院", "金额较高，调解后可转重点攻坚"],
  ["陈敏", "L3-0005", "320106199207084321", "13900001111", "江苏省南京市鼓楼区中央路", 7400, 210, 160, "HT-SZ-0005", "深圳市南山区人民法院", ""],
  ["杨磊", "L3-0006", "330102198011118888", "", "浙江省杭州市上城区", 56000, 2800, 900, "HT-SZ-0006", "深圳市南山区人民法院", "缺手机号，需补触达信息"],
  ["赵静", "L3-0007", "440104199906306666", "18812340000", "广东省广州市越秀区", 4800, 120, 95, "HT-GZ-0007", "广州市越秀区人民法院", "金额低，适合批量触达"],
  ["周杰", "L3-0008", "", "15811112222", "广西壮族自治区南宁市青秀区", 22000, 870, 500, "HT-NN-0008", "南宁市青秀区人民法院", "缺身份证"],
  ["吴婷", "L3-0009", "610104199304055555", "17799990000", "陕西省西安市莲湖区", 16300, 650, 260, "HT-XA-0009", "西安市莲湖区人民法院", ""],
  ["郑凯", "L3-0010", "370102198908097777", "15655556666", "", 39000, 2100, 720, "HT-JN-0010", "济南市历下区人民法院", "缺地址"],
  ["孙梅", "L3-0011", "110105197912313333", "18622221111", "北京市朝阳区", 112000, 5300, 1050, "HT-BJ-0011", "北京市朝阳区人民法院", "重点户"],
  ["黄鹏", "L3-0012", "350102199601028888", "15288889999", "福建省福州市鼓楼区", 6800, 190, 130, "HT-FZ-0012", "福州市鼓楼区人民法院", ""],
];

function styleSheet(sheet, rangeAddress, numericRanges = []) {
  sheet.showGridLines = false;
  const used = sheet.getRange(rangeAddress);
  used.format.borders = { preset: "all", style: "thin", color: "#D9DEE8" };
  used.format.wrapText = true;
  sheet.getRange(rangeAddress.split(":")[0].replace(/\d+$/, "1") + ":" + rangeAddress.split(":")[1].replace(/\d+$/, "1")).format = {
    fill: "#123C3A",
    font: { bold: true, color: "#FFFFFF" },
  };
  for (const address of numericRanges) sheet.getRange(address).setNumberFormat("#,##0.00");
  sheet.freezePanes.freezeRows(1);
  used.format.autofitColumns();
  used.format.autofitRows();
}

function addReadme(workbook, title, rows) {
  const sheet = workbook.worksheets.add("说明");
  const data = [["项目", title], ["用途", "NPA Agent PRD V0.1 验收样例"], ...rows];
  sheet.getRangeByIndexes(0, 0, data.length, 2).values = data;
  sheet.getRange("A1:B1").format = { fill: "#123C3A", font: { bold: true, color: "#FFFFFF" } };
  sheet.getRangeByIndexes(0, 0, data.length, 2).format.borders = { preset: "all", style: "thin", color: "#D9DEE8" };
  sheet.getRange("A:A").format.columnWidthPx = 150;
  sheet.getRange("B:B").format.columnWidthPx = 520;
}

async function exportWorkbook(workbook, filepath, previewPrefix) {
  await fs.mkdir(path.dirname(filepath), { recursive: true });
  await fs.mkdir(outputDir, { recursive: true });

  for (const sheet of workbook.worksheets.items) {
    const blob = await workbook.render({ sheetName: sheet.name, autoCrop: "all", scale: 1, format: "png" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    await fs.writeFile(path.join(outputDir, `${previewPrefix}-${sheet.name}.png`), bytes);
  }

  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 50 },
    summary: "formula error scan",
  });
  console.log(errors.ndjson);

  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(filepath);
}

function makeTemplateWorkbook() {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.getOrAdd("资产包清单", { renameFirstIfOnlyNewSpreadsheet: true });
  sheet.getRangeByIndexes(0, 0, templateRows.length, baseHeaders.length).values = templateRows;
  styleSheet(sheet, `A1:K${templateRows.length}`, ["F2:G200"]);
  sheet.getRange("A1:K1").format.rowHeightPx = 32;

  const guide = workbook.worksheets.add("字段说明");
  guide.getRangeByIndexes(0, 0, fieldGuideRows.length, 5).values = fieldGuideRows;
  styleSheet(guide, `A1:E${fieldGuideRows.length}`);
  guide.getRange("A:E").format.columnWidthPx = 180;

  const alias = workbook.worksheets.add("字段别名");
  alias.getRangeByIndexes(0, 0, aliasRows.length, 2).values = aliasRows;
  styleSheet(alias, `A1:B${aliasRows.length}`);
  alias.getRange("A:A").format.columnWidthPx = 160;
  alias.getRange("B:B").format.columnWidthPx = 680;

  return workbook;
}

function makeSampleWorkbook(sheetName, rows, readmeRows, numericRanges = []) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.getOrAdd(sheetName, { renameFirstIfOnlyNewSpreadsheet: true });
  sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length).values = rows;
  const lastCol = String.fromCharCode("A".charCodeAt(0) + rows[0].length - 1);
  styleSheet(sheet, `A1:${lastCol}${rows.length}`, numericRanges);
  addReadme(workbook, sheetName, readmeRows);
  return workbook;
}

await exportWorkbook(
  makeTemplateWorkbook(),
  path.join(root, "templates", "个贷资产包标准模板.xlsx"),
  "template"
);

await exportWorkbook(
  makeSampleWorkbook("Level1_基础金额", level1Rows, [
    ["数据等级", "Level 1"],
    ["字段特点", "只有债务人编号和本金，适合验证最低可分析条件。"],
    ["预期输出", "金额规模、户均本金、低数据完整度提示、补充身份证/手机号/地址建议。"],
  ], ["B2:B200"]),
  path.join(root, "samples", "level1_basic.xlsx"),
  "level1"
);

await exportWorkbook(
  makeSampleWorkbook("Level2_画像触达", level2Rows, [
    ["数据等级", "Level 2"],
    ["字段特点", "有姓名、身份证、手机号、地址、本金、利息，适合验证画像和电话调解初判。"],
    ["预期输出", "年龄、性别、地区、手机号完整度、电话调解优先策略。"],
  ], ["E2:F200"]),
  path.join(root, "samples", "level2_profile.xlsx"),
  "level2"
);

await exportWorkbook(
  makeSampleWorkbook("Level3_法院管辖", level3Rows, [
    ["数据等级", "Level 3"],
    ["字段特点", "增加合同编号、管辖法院、逾期天数，适合验证法院集中度和处置模式。"],
    ["预期输出", "管辖集中度、重点户、电话调解和批量诉讼组合建议。"],
  ], ["F2:G200", "H2:H200"]),
  path.join(root, "samples", "level3_court.xlsx"),
  "level3"
);

console.log("NPA Agent PRD assets generated.");
