export function filterMindMapHistories(
  histories,
  {
    query = "",
    knowledgeBaseId = "",
    knowledgeBases = [],
  } = {},
) {
  const normalizedQuery = String(query).trim().toLocaleLowerCase("zh-CN");
  const selectedKnowledgeBaseId = Number(knowledgeBaseId) || null;
  const baseNames = new Map(
    knowledgeBases.map((item) => [Number(item.id), String(item.name || "")]),
  );

  return histories.filter((history) => {
    if (
      selectedKnowledgeBaseId
      && Number(history.knowledge_base_id) !== selectedKnowledgeBaseId
    ) {
      return false;
    }
    if (!normalizedQuery) return true;
    const searchable = [
      history.title,
      baseNames.get(Number(history.knowledge_base_id)),
    ]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return searchable.includes(normalizedQuery);
  });
}
