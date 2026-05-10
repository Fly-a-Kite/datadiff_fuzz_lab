# DataDiffFuzz

面向 DataFrame 与嵌入式分析引擎的语义差分模糊测试 MVP。

当前支持：

- pandas backend
- polars backend
- DuckDB backend
- SQLite backend
- 随机表数据生成
- 类型感知/非类型感知生成器消融
- DSL 操作序列生成
- 语义归一化
- 差分 oracle
- metamorphic oracle
- feedback-guided corpus
- reducer
- bug artifact 保存
- Markdown / CSV 报告
- duration-based fuzzing
- ablation experiment matrix
- pytest 自动测试

快速开始：

```bash
cd /Users/fly/datadiff_fuzz_lab
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest -q
.venv/bin/datadiff fuzz --cases 100 --seed 1 --backends pandas,polars,duckdb,sqlite
.venv/bin/datadiff report
.venv/bin/datadiff show-bugs
```

按时间运行：

```bash
.venv/bin/datadiff fuzz --duration 10m --seed 1 --backends pandas,polars,duckdb,sqlite
.venv/bin/datadiff fuzz --duration 24h --seed 1 --backends pandas,polars,duckdb,sqlite
```

启用 metamorphic oracle：

```bash
.venv/bin/datadiff fuzz --cases 1000 --seed 1 --backends pandas,polars,duckdb,sqlite --enable-metamorphic-oracle
```

边界浮点语义实验：

```bash
.venv/bin/datadiff fuzz --cases 1000 --seed 1 --profile edge_float --backends pandas,polars,duckdb,sqlite
```

批量消融实验：

```bash
.venv/bin/datadiff experiment \
  --cases 1000 \
  --seeds 1,1001,2001 \
  --presets baseline,no_type_aware,no_normalizer,no_feedback,metamorphic,reducer \
  --backends pandas,polars,duckdb,sqlite
.venv/bin/datadiff experiment-summary
```

主要输出：

- `runs/*.jsonl`: 每个 case 的完整执行记录
- `runs/*.meta.json`: 运行配置、耗时、吞吐量、环境信息
- `bugs/bug_*`: 可复现 bug artifact
- `reports/*.md`: Markdown 实验报告
- `reports/*.csv`: finding 明细表

默认生成器现在聚焦公共语义子集，避免把 NaN/Infinity、未排序 LIMIT、all-NULL sum 等已知语义差异误报为实现 bug。后续可以把这些边界语义作为单独研究目标打开。

复现和验证 artifact：

```bash
.venv/bin/datadiff reproduce --bug bugs/bug_x
.venv/bin/datadiff validate-artifact --bug bugs/bug_x
```
