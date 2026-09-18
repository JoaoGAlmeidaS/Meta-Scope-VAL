// D24 — tema proprio do ECharts, derivado dos tokens de style.css.
// O tema padrao do ECharts e o maior denunciador de portfolio generico.

const metascopeTheme = {
  color: ["#ff4655", "#4cc9f0", "#f4a261", "#8ecae6", "#c77dff", "#90be6d"],
  backgroundColor: "transparent",
  textStyle: { fontFamily: "system-ui, -apple-system, sans-serif" },
  // TODO(D24): eixos, grid, tooltip e legenda alinhados aos tokens.
};

if (typeof echarts !== "undefined") {
  echarts.registerTheme("metascope", metascopeTheme);
}
