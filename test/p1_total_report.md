# P1 测试验收总报告

## 数据源约束

- `Data/` 下的 `trimmedSamples.sigmf-meta` 与 `trimmedSamples.sigmf-data` 仅作为只读验收输入使用。
- 验收过程中未通过修改 `Data/` 数据源来规避质量门禁。

## 关于“物理长度”和“逻辑长度”的澄清

- 之前实现把 `.sigmf-data` 按 datatype 推导出的样本数称为“物理长度”，把 metadata 中 `traceability:sample_length` 等字段声明的样本数称为“逻辑长度”。
- 按最新验收要求，二者不应被视为两个可同时成立的长度；如果 metadata 声明了样本数，它必须和 `.sigmf-data` 的字节长度换算出的样本数完全一致。
- 因此现在将二者作为“metadata 声明样本数”和“data 文件推导样本数”进行一致性校验，不一致就是 `SIGMF_SAMPLE_COUNT_MISMATCH` error。

## 轮次记录

### 第 1 轮：初始验收（失败）

- 命令：`python -m pytest && python -m rfview.cli inspect Data/trimmedSamples.sigmf-meta --cache-dir test/.rfview-cache --pretty`
- 结果：单元测试通过；真实 `Data/trimmedSamples.sigmf-meta` 验收失败。
- 失败原因：CLI 将 metadata 声明样本数与 data 文件推导样本数当作两个不同概念处理，导致不一致数据没有作为阻塞问题报告。

### 第 2 轮：修改后验收（通过检测能力，数据本身不匹配）

- 命令：`python test/p1_acceptance.py`
- 结果：验收脚本通过；含义是 RFview 已正确识别并拒绝当前不匹配的只读 Data fixture。
- 核心验证结果：metadata 声明样本数为 `22,372,352`，data 文件推导样本数为 `166,912`，二者不匹配。
- 健康报告 gate 为 `fail`，包含 `SIGMF_SAMPLE_COUNT_MISMATCH` error。
- 最新机器可读报告：`test/reports/p1_acceptance_latest.json`
- 最新 Markdown 报告：`test/reports/p1_acceptance_latest.md`

## 结论

当前 `Data/trimmedSamples.sigmf-meta` 与 `Data/trimmedSamples.sigmf-data` 不匹配。RFview 现在会把该情况作为阻塞错误报告，而不是通过“逻辑长度/物理长度”绕过验收。
