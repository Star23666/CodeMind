<template>
  <el-option-group v-if="publicBases.length" label="公共知识库">
    <el-option
      v-for="base in publicBases"
      :key="base.id"
      :label="base.name"
      :value="base.id"
    >
      <span class="option-label">{{ base.name }}</span>
      <el-tag size="small" effect="plain">公共</el-tag>
    </el-option>
  </el-option-group>
  <el-option-group v-if="privateBases.length" label="我的知识库">
    <el-option
      v-for="base in privateBases"
      :key="base.id"
      :label="base.name"
      :value="base.id"
    >
      <span class="option-label">{{ base.name }}</span>
      <el-tag size="small" type="info" effect="plain">私人</el-tag>
    </el-option>
  </el-option-group>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  bases: {
    type: Array,
    default: () => [],
  },
});

const publicBases = computed(() =>
  props.bases.filter((base) => base.visibility === "public"),
);
const privateBases = computed(() =>
  props.bases.filter((base) => base.visibility !== "public"),
);
</script>

<style scoped>
.option-label {
  display: inline-block;
  max-width: calc(100% - 62px);
  margin-right: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}
</style>
