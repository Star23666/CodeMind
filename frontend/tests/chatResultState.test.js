import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import {
  clearChatResultStateForQaRecords,
  readChatResultState,
  saveChatResultState,
} from "../src/utils/chatResultState.js";

beforeEach(() => {
  globalThis.sessionStorage = createMemoryStorage();
});

test("删除其他历史记录时保留当前持久化回答", () => {
  saveChatResultState(7, {
    qaRecordId: 36,
    questionSnapshot: "AMAT 计算公式",
  });

  assert.equal(clearChatResultStateForQaRecords(7, [35]), false);
  assert.equal(readChatResultState(7)?.qaRecordId, 36);
});

test("单条删除当前历史记录时清除持久化回答", () => {
  saveChatResultState(7, {
    qaRecordId: 36,
    questionSnapshot: "AMAT 计算公式",
  });

  assert.equal(clearChatResultStateForQaRecords(7, [36]), true);
  assert.equal(readChatResultState(7), null);
});

test("批量删除包含当前历史记录时清除持久化回答", () => {
  saveChatResultState(7, {
    qaRecordId: 36,
    questionSnapshot: "AMAT 计算公式",
  });

  assert.equal(clearChatResultStateForQaRecords(7, [12, 36, 48]), true);
  assert.equal(readChatResultState(7), null);
});

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
    clear() {
      values.clear();
    },
  };
}
