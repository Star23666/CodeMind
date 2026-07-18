export function pickDefaultKnowledgeBase(bases, requestedId = null) {
  const normalizedId = Number(requestedId);
  const requested = bases.find((base) => base.id === normalizedId);
  if (requested) return requested;
  return bases.find((base) => base.visibility !== "public") || bases[0] || null;
}
