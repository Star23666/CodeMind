<template>
  <div class="markdown-content" @click="handleContentClick" v-html="renderedHtml" />
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import DOMPurify from "dompurify";
import { marked } from "marked";

const props = defineProps({
  content: {
    type: String,
    default: "",
  },
  fallback: {
    type: String,
    default: "",
  },
  citationTargets: {
    type: Array,
    default: () => [],
  },
});

const router = useRouter();

const renderedHtml = computed(() => {
  const markdown = props.content || props.fallback;
  const sanitizedHtml = DOMPurify.sanitize(marked.parse(markdown, {
    breaks: true,
    gfm: true,
  }));

  if (!props.citationTargets.length || !sanitizedHtml.includes("[来源")) {
    return sanitizedHtml;
  }

  return injectCitationLinks(sanitizedHtml);
});

function injectCitationLinks(html) {
  const template = window.document.createElement("template");
  template.innerHTML = html;

  const walker = window.document.createTreeWalker(
    template.content,
    NodeFilter.SHOW_TEXT,
  );
  const textNodes = [];

  while (walker.nextNode()) {
    const parentTag = walker.currentNode.parentElement?.tagName;
    if (!["A", "CODE", "PRE", "SCRIPT", "STYLE"].includes(parentTag)) {
      textNodes.push(walker.currentNode);
    }
  }

  for (const textNode of textNodes) {
    replaceCitationsInTextNode(textNode);
  }

  return template.innerHTML;
}

function replaceCitationsInTextNode(textNode) {
  const value = textNode.nodeValue || "";
  const citationPattern = /\[来源\s*(\d+)\]/g;
  const fragment = window.document.createDocumentFragment();
  let cursor = 0;
  let hasCitation = false;

  for (const match of value.matchAll(citationPattern)) {
    const sourceIndex = Number(match[1]) - 1;
    const target = props.citationTargets[sourceIndex];
    if (!target) continue;

    const matchIndex = match.index ?? 0;
    fragment.append(value.slice(cursor, matchIndex));

    const link = window.document.createElement("a");
    link.className = "source-citation";
    link.dataset.sourceIndex = String(sourceIndex);
    link.href = resolveTargetHref(target);
    link.title = `查看${match[0]}对应的原文片段`;
    link.textContent = match[0];
    fragment.append(link);

    cursor = matchIndex + match[0].length;
    hasCitation = true;
  }

  if (!hasCitation) return;

  fragment.append(value.slice(cursor));
  textNode.replaceWith(fragment);
}

function resolveTargetHref(target) {
  if (isExternalTarget(target)) return target;
  try {
    return router.resolve(target).href;
  } catch {
    return "#";
  }
}

function handleContentClick(event) {
  const citation = event.target.closest?.("[data-source-index]");
  if (!citation) return;

  const sourceIndex = Number(citation.dataset.sourceIndex);
  const target = props.citationTargets[sourceIndex];
  if (!target) return;

  event.preventDefault();
  if (isExternalTarget(target)) {
    window.location.assign(target);
    return;
  }
  router.push(target);
}

function isExternalTarget(target) {
  return typeof target === "string" && /^(?:https?:)?\/\//i.test(target);
}
</script>

<style scoped>
.markdown-content {
  min-width: 0;
  color: inherit;
  font-size: inherit;
  line-height: inherit;
  overflow-wrap: anywhere;
}

.markdown-content :deep(> :first-child) {
  margin-top: 0;
}

.markdown-content :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(p),
.markdown-content :deep(ul),
.markdown-content :deep(ol),
.markdown-content :deep(blockquote),
.markdown-content :deep(pre),
.markdown-content :deep(table) {
  margin: 0 0 1em;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4),
.markdown-content :deep(h5),
.markdown-content :deep(h6) {
  margin: 1.35em 0 0.65em;
  color: var(--cm-heading, #172a45);
  font-weight: 700;
  line-height: 1.35;
}

.markdown-content :deep(h1) {
  font-size: 1.75em;
}

.markdown-content :deep(h2) {
  font-size: 1.45em;
}

.markdown-content :deep(h3) {
  font-size: 1.22em;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 1.65em;
}

.markdown-content :deep(li + li) {
  margin-top: 0.3em;
}

.markdown-content :deep(blockquote) {
  padding: 0.55em 1em;
  border-left: 4px solid var(--cm-primary, #3188e8);
  border-radius: 0 8px 8px 0;
  color: var(--cm-muted, #708096);
  background: var(--cm-surface-soft, rgba(238, 247, 255, 0.76));
}

.markdown-content :deep(code) {
  padding: 0.14em 0.36em;
  border-radius: 5px;
  background: var(--cm-primary-soft, rgba(218, 237, 255, 0.78));
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.9em;
}

.markdown-content :deep(pre) {
  overflow-x: auto;
  padding: 1em;
  border-radius: 12px;
  color: #e7edf6;
  background: #142033;
}

.markdown-content :deep(pre code) {
  padding: 0;
  color: inherit;
  background: transparent;
}

.markdown-content :deep(table) {
  display: block;
  width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  padding: 0.58em 0.75em;
  border: 1px solid var(--cm-border, #d8e3ef);
  text-align: left;
}

.markdown-content :deep(th) {
  color: var(--cm-heading, #172a45);
  background: var(--cm-surface-soft, #f5f9fd);
}

.markdown-content :deep(hr) {
  margin: 1.5em 0;
  border: 0;
  border-top: 1px solid var(--cm-border, #d8e3ef);
}

.markdown-content :deep(img) {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1em auto;
  border-radius: 10px;
}

.markdown-content :deep(a) {
  color: var(--cm-primary, #3188e8);
  text-decoration: underline;
  text-decoration-color: rgba(49, 136, 232, 0.38);
  text-underline-offset: 3px;
}

.markdown-content :deep(.source-citation) {
  color: #4b9bea;
  font-weight: 700;
  text-decoration: none;
  transition: color 0.18s ease;
}

.markdown-content :deep(.source-citation:hover),
.markdown-content :deep(.source-citation:focus-visible) {
  color: #2074cd;
  text-decoration: underline;
  text-decoration-color: rgba(32, 116, 205, 0.5);
  outline: none;
}
</style>
