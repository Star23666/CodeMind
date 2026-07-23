import test from "node:test";
import assert from "node:assert/strict";

import { filterMindMapHistories } from "../src/utils/mindMapState.js";

const histories = [
  { id: 1, title: "进程与线程", knowledge_base_id: 10 },
  { id: 2, title: "TCP 连接", knowledge_base_id: 20 },
  { id: 3, title: "内存管理", knowledge_base_id: 10 },
];
const knowledgeBases = [
  { id: 10, name: "操作系统" },
  { id: 20, name: "计算机网络" },
];

test("知识地图列表可跨知识库按标题或知识库名称搜索", () => {
  assert.deepEqual(
    filterMindMapHistories(histories, { query: "操作系统", knowledgeBases }).map((item) => item.id),
    [1, 3],
  );
  assert.deepEqual(
    filterMindMapHistories(histories, { query: "TCP", knowledgeBases }).map((item) => item.id),
    [2],
  );
});

test("知识地图列表可按知识库筛选", () => {
  assert.deepEqual(
    filterMindMapHistories(histories, { knowledgeBaseId: 20, knowledgeBases }).map((item) => item.id),
    [2],
  );
});
