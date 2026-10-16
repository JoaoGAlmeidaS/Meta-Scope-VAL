// D24 — tema próprio do ECharts, lido dos tokens de style.css em tempo de execução.
// O tema padrão do ECharts nunca aparece: todo gráfico é criado com `chart(el)` (app.js), que
// usa o tema "metascope". Mudou um token no CSS, o gráfico acompanha (inclusive no tema claro).

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function metascopeTheme() {
  const t = {
    text: cssVar("--text"),
    muted: cssVar("--text-muted"),
    faint: cssVar("--text-faint"),
    border: cssVar("--border"),
    strong: cssVar("--border-strong"),
    surface: cssVar("--surface"),
    surface2: cssVar("--surface-2"),
    attack: cssVar("--attack"),
    defense: cssVar("--defense"),
    gold: cssVar("--gold"),
    neutral: cssVar("--neutral"),
    sans: cssVar("--font-sans"),
    display: cssVar("--font-display"),
  };
  const axis = {
    axisLine: { show: true, lineStyle: { color: t.strong } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11, fontFamily: t.sans },
    splitLine: { show: true, lineStyle: { color: t.border, width: 1 } },
    nameTextStyle: { color: t.muted, fontSize: 11, fontFamily: t.sans },
  };
  return {
    color: [t.attack, t.defense, t.gold, t.neutral, t.text],
    backgroundColor: "transparent",
    textStyle: { fontFamily: t.sans, color: t.text, fontSize: 12 },
    title: { textStyle: { color: t.text, fontSize: 16, fontWeight: 600, fontFamily: t.display }, subtextStyle: { color: t.muted } },
    grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: { ...axis, axisLine: { show: false } },
    timeAxis: { ...axis, splitLine: { show: false } },
    legend: { textStyle: { color: t.muted, fontSize: 11 }, itemWidth: 12, itemHeight: 8, icon: "rect" },
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.strong,
      borderWidth: 1,
      padding: [6, 10],
      textStyle: { color: t.text, fontSize: 12, fontFamily: t.sans },
      extraCssText: "border-radius:0;box-shadow:none;",
      axisPointer: { lineStyle: { color: t.strong }, crossStyle: { color: t.strong } },
    },
    line: { symbol: "circle", symbolSize: 5, lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: 0 } },
    markLine: { symbol: "none", label: { color: t.faint, fontSize: 10 } },
    visualMap: { textStyle: { color: t.muted } },
    dataZoom: { borderColor: t.border, textStyle: { color: t.muted } },
    tokens: t, // acessível em app.js via theme().tokens
  };
}

if (typeof echarts !== "undefined") {
  echarts.registerTheme("metascope", metascopeTheme());
}
