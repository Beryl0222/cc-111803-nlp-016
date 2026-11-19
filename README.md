# 内容申诉中的政策适用与执行撤回

本地文本工作区用于保存上下文窗口和内容分类相关的合成记录，并提供基础规范化和词项查看能力。

## 环境

需要 Python 3.11 或更新版本。运行程序仅使用 Python 标准库。测试依赖固定为 pytest 8.3.4，可执行 `python -m pip install -r requirements-dev.txt` 安装。

## 运行

运行 `PYTHONPATH=src python -m nlp_content_policy_appeals.desk_cli` 查看申诉裁决与限制执行核对结果。输出分两层：`findings` 为逐条认定的裁决（含发言日适用版本、初判证据原文、归属交叉核对结论与具体待核点），`limits` 为按限制汇总的处置（多认定支撑时的收窄范围、该撤回与已撤回范围、回执对应动作）。可通过 `--case`、`--registry`、`--threads` 分别指定审核记录、业务目录和完整对话线程。政策按发言日期采取当时生效版本。申诉裁决和执行回执分开记录。

从项目根目录执行 `PYTHONPATH=src python -m nlp_content_policy_appeals.cli ingest fixtures/records.json` 导入样例，随后执行 `PYTHONPATH=src python -m nlp_content_policy_appeals.cli list` 查看记录。工作数据写入 `var/records.json`。业务查询使用 fixtures/business.json 中的初始资料，约定见 fixtures/business-contract.md。执行 PYTHONPATH=src python -m nlp_content_policy_appeals.cli business 可查看当前业务目录结果。

样例为本地合成文本。记录包含来源、修订号和原文，当前工作区对空白做统一处理，并提供字符及英文词项切分。

## 测试

执行 `python -m pytest -q` 检查规范化、记录持久化和来源筛选。
