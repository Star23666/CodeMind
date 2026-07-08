import { computed, ref } from "vue";

const THEME_KEY = "codemind-theme";
const theme = ref(localStorage.getItem(THEME_KEY) || "light");

function applyTheme(nextTheme) {
  theme.value = nextTheme;
  localStorage.setItem(THEME_KEY, nextTheme);
  document.documentElement.dataset.theme = nextTheme;
}

applyTheme(theme.value);

export function useTheme() {
  const isDark = computed(() => theme.value === "dark");

  function toggleTheme() {
    applyTheme(isDark.value ? "light" : "dark");
  }

  return {
    theme,
    isDark,
    toggleTheme,
  };
}
