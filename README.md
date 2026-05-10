# DataDiffFuzz

面向 DataFrame 与嵌入式分析引擎的语义差分模糊测试 MVP。

当前支持：

- pandas backend
- polars backend
- DuckDB backend
- 随机表数据生成
- DSL 操作序列生成
- 语义归一化
- 差分 oracle
- bug artifact 保存
- Markdown / CSV 报告
- pytest 自动测试

快速开始：

```bash
cd /Users/fly/datadiff_fuzz_lab
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest -q
.venv/bin/datadiff fuzz --cases 100 --seed 1 --backends pandas,polars,duckdb
.venv/bin/datadiff report
.venv/bin/datadiff show-bugs
```
