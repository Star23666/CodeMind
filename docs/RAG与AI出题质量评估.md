# CodeMind RAG 与 AI 出题质量评估

本文档说明固定质量基线的运行方式、指标定义、阈值决策和模型变更规则。固定数据位于 [`testdata/eval/`](../testdata/eval/)。

## 1. 评估目标

评估覆盖两条生产链路：

1. RAG 检索：正确文档召回、引用文档准确性、空检索、依据不足问题的误召回风险，以及实际 LLM 拒答。
2. AI 出题：结构成功率、题型与认知层级、事实正确性、资料相关性、难度符合度、重复率和来源可核对性。

结构合法不等于语义正确。脚本的自动指标用于筛查和对比，事实、难度与来源仍需按评分表人工复核。

## 2. 环境准备

在 `backend/.env` 配置在线模型。密钥只保存在本地或受保护 Secret 中，不能写入结果文件。

```dotenv
EMBEDDING_API_KEY=...
EMBEDDING_BASE_URL=https://provider.example.com/v1
EMBEDDING_MODEL=Qwen/Qwen3-VL-Embedding-8B

LLM_API_KEY=...
LLM_BASE_URL=https://provider.example.com/v1
LLM_MODEL=Qwen/Qwen3.6-35B-A3B

# 留空时复用 LLM_API_KEY 和 LLM_BASE_URL
RERANK_API_KEY=
RERANK_BASE_URL=
RERANK_MODEL=Qwen/Qwen3-Reranker-8B
RERANK_SCORE_THRESHOLD=0.55
```

先安装后端依赖，然后执行数据校验：

```bash
cd backend
python scripts/evaluate_quality.py validate
```

校验会拒绝数量不足、重复编号、目标文档不存在、依据原句不在语料中、出题配置无效或疑似含密钥的数据集。

## 3. RAG 检索质量评估

当前生产链路使用章节感知 Embedding、Dense + BM25 候选召回、RRF 融合和在线 reranker。运行完整阈值扫描：

```bash
python scripts/evaluate_quality.py rag-hybrid \
  --output ../quality-results/rag-hybrid.json \
  --with-generation \
  --generation-positive-per-document 1 \
  --generation-concurrency 2
```

该命令扫描的是 `reranker_relevance_score`，默认候选参数为 Dense 12、BM25 12、RRF 20、最终 Top 2。生成阶段会评估每份文档的正例样本和全部依据不足问题；单个请求超时或供应商异常会记录在结果中，不会丢弃整轮已完成数据。

仅需要复现旧版纯向量相似度基线时使用：

```bash
python scripts/evaluate_quality.py rag \
  --output ../quality-results/rag-threshold.json
```

该命令扫描 `embedding_similarity`，用于诊断向量回退链路，不代表当前完整生产检索。

旧链路需要同时测实际回答和拒答时：

```bash
python scripts/evaluate_quality.py rag \
  --output ../quality-results/rag-full.json \
  --with-generation \
  --generation-positive-per-document 1
```

### 指标定义

| 指标 | 含义 |
| --- | --- |
| `recall_hit_rate` | 可回答问题的最终来源中包含目标文档的比例 |
| `top1_document_accuracy` | 第一条最终来源属于目标文档的比例 |
| `citation_document_precision` | 可回答问题返回的全部来源中，目标文档来源所占比例 |
| `positive_empty_rate` | 可回答问题经过阈值后无来源的比例 |
| `insufficient_empty_rate` | 依据不足问题被阈值正确过滤为空的比例 |
| `retrieval_confident_error_risk` | 依据不足问题仍返回来源、因而可能进入生成阶段的比例 |
| `error_confident_answer_rate` | 依据不足问题实际调用 LLM 后，没有明确拒答的比例 |

阈值质量门槛定义为：召回率不低于 90%，同时检索误召回风险不高于 10%。若没有扫描值满足门槛，报告的 `recommended_threshold` 为 `null`；`best_observed_threshold` 仅用于诊断，不能直接替换生产配置。

## 4. AI 出题评估

运行指定固定用例：

```bash
python scripts/evaluate_quality.py quiz \
  --output ../quality-results/quiz.json \
  --manual-csv ../quality-results/quiz-manual.csv \
  --case quiz-os-process-intermediate \
  --case quiz-tcp-basic
```

不传 `--case` 会运行全部 16 套用例，调用次数和费用较高。脚本直接复用生产 `QuizService` 的 Prompt、结构解析和校验，因此会真实暴露模型遗漏字段、题型越界和认知层级不满足等问题。

人工评分字段：

| 字段 | 0 分 | 1 分 | 2 分 |
| --- | --- | --- | --- |
| 事实正确性 | 错误或编造 | 部分正确或表述过宽 | 全部可由资料确认 |
| 资料相关性 | 与资料无关 | 相关但重点偏离 | 直接考查资料知识 |
| 难度符合度 | 明显不符 | 略高或略低 | 与标注认知要求一致 |
| 来源可核对 | 来源不支持答案 | 仅部分支持 | 答案与解析均有直接依据 |
| 重复 | 与其他题重复 | - | 不重复 |

填写后汇总：

```bash
python scripts/evaluate_quality.py manual-summary \
  --input ../quality-results/quiz-manual.csv
```

耗时只能在模型、题量、资料规模、上下文预算和日期相同的条件下比较。每次报告必须保留这些字段。

## 5. 强制重评条件

出现以下任一变化，旧结果不得继续作为当前配置的依据：

- 更换 Embedding 模型、API 供应商或输出维度。
- 修改 chunk 大小、重叠、文本清洗或文档解析方式。
- 修改 `top_k`、重排算法、`rerank_top_n` 或检索分数定义。
- 修改 RAG Prompt、LLM 模型、思考模式或回答上下文预算。
- 修改 AI 出题 Prompt、模型、题型协议、上下文预算或结构重试次数。
- 修改固定语料、RAG 标注或出题期望。

Embedding 模型或维度变化后，还必须重建 Chroma 集合并重新索引文档，不能将旧向量与新阈值混用。

## 6. 当前阈值状态

`RERANK_SCORE_THRESHOLD=0.55` 是当前完整混合检索链路的生产默认值。2026-07-22 固定集中，该值取得 100% 正例召回、100% Top1、100% 引用文档精度和 0% 依据不足误召回风险；32 条生成抽样也没有出现供应商错误、正例误拒答或负例错误自信回答。

`RETRIEVAL_SCORE_THRESHOLD=0.45` 只用于在线 reranker 不可用且 `RERANK_FAIL_OPEN=true` 时的向量回退。它是 Embedding 相似度，不能与 0 到 1 的 reranker 相关性分数互换。纯向量固定基线未达到质量门槛，因此日志出现 reranker 回退时应视为降级状态。

固定集规模有限，不能据此承诺所有真实资料均为 100%。新增领域资料、修改解析/切分/模型/候选数量/指令后必须重评；Embedding 模型或维度变化后还要重建 Chroma。

首轮完整数据见 [2026-07-22 质量基线](evaluation/2026-07-22质量基线.md)。

## 7. 手动在线 Job

`.github/workflows/quality-evaluation.yml` 只支持 `workflow_dispatch`，不会在普通 PR 自动消耗在线额度。`rag`、`rag-hybrid` 或 `quiz` 模式运行前需在仓库 Secrets 中配置 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`LLM_API_KEY` 和 `LLM_BASE_URL`，然后在 Actions 页面选择模式与模型。`rag-hybrid` 默认让 reranker 复用 LLM Secret；在线模式的 JSON/CSV 结果作为 Artifact 保存，`validate` 不需要模型 Secret。
