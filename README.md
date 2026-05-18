# RFview

RFview 计划成为一款面向 SigMF 与 HDF5/RadioML 数据集的信号阅读器与数据集管理工具，为后续 RFML（Radio Frequency Machine Learning）训练、验证和回归测试提供可靠的数据检视、统计、可视化与标注基础。

当前仓库已从 P0 设计校准进入 **P1 核心验证**：在保留设计文档的同时，新增一个可复用的 Python core/CLI，用于验证 SigMF 与 HDF5/RadioML 导入、校验、首屏统计、样本窗口读取和缓存骨架。

设计文档入口：[`docs/design/index.html`](docs/design/index.html)，HDF5/RadioML2018 兼容方案见 [`docs/design/hdf5-radioml.html`](docs/design/hdf5-radioml.html)，阶段计划见 [`docs/design/roadmap.html`](docs/design/roadmap.html)。

## P1 功能范围

- **SigMF meta parser**：读取 `global`、`captures`、`annotations`，解析常见 `core:datatype`，并保留未知 namespace。
- **HDF5/RadioML adapter**：识别 HDF5 magic，安装 `hdf5` extra 后可通过 `h5py` 扫描 `X/Y/Z` dataset 的 shape、dtype 和 chunk。
- **Schema + project rule validator**：输出 error/warning/info 级别、规则 ID、路径和修复建议。
- **Sample window reader**：按 `sample_start` / `sample_count` 读取 SigMF IQ 窗口，支持 `cf32_*`、常见有符号/无符号整数 IQ。
- **First-screen stats**：生成窗口样本数、时长、I/Q min/max/mean、RMS、PAPR、NaN/Inf、PSD preview 和标签覆盖率。
- **Cache skeleton**：记录源文件路径、size、mtime、SHA-256、规则版本和摘要 payload，用于判断缓存是否失效。

## 快速开始

```bash
python -m pip install -e '.[dev]'
python -m rfview.cli inspect /path/to/example.sigmf-meta --cache-dir .rfview-cache --pretty
```

如需完整 HDF5/RadioML dataset 扫描，请安装可选依赖：

```bash
python -m pip install -e '.[dev,hdf5]'
python -m rfview.cli inspect /path/to/radioml2018.h5 --pretty
```

CLI 输出为 JSON 健康报告；当质量门禁为 `fail` 时退出码为 1，`pass` 或 `warn` 时退出码为 0。

## 开发检查

```bash
python -m pytest
python -m rfview.cli inspect tests/fixtures/example.sigmf-meta --pretty  # 若添加本地 fixture
```
