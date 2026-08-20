(function () {
  const data = JSON.parse(document.getElementById('dash-data').textContent);
  const REF = data.ref_month_index;
  const N = data.months.length;

  const fmt0 = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  const fmt1pct = (v) => v.toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + '%';
  const monthShort = (m) => { const [mon, yr] = m.split('./'); return mon.charAt(0).toUpperCase() + mon.slice(1) + '/' + yr; };
  const abs = Math.abs;

  // ---------- meta ----------
  document.getElementById('meta-ref').textContent = 'Mês de referência: ' + monthShort(data.months[REF]);
  document.getElementById('meta-horizon').textContent = 'Horizonte: ' + monthShort(data.months[0]) + ' – ' + monthShort(data.months[N - 1]);

  // ---------- KPI row ----------
  const receitaMes = data.receita_liquida[REF] + data.outras_receitas[REF];
  const despesasMes = data.total_despesas[REF];
  const resultadoMes = data.saldo_mes[REF];
  const saldoFinal = data.saldo_acumulado[N - 1];
  const obraPctPago = data.obra.previsto ? (data.obra.pago / data.obra.previsto * 100) : 0;

  function kpiTile({ label, value, deltaText, deltaClass, foot, meter }) {
    const el = document.createElement('div');
    el.className = 'kpi-tile';
    el.innerHTML = `
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      ${deltaText ? `<span class="delta ${deltaClass}">${deltaText}</span>` : ''}
      ${meter !== undefined ? `<div class="meter-track"><div class="meter-fill" style="width:${meter}%"></div></div>` : ''}
      ${foot ? `<div class="foot">${foot}</div>` : ''}
    `;
    return el;
  }

  const kpiRow = document.getElementById('kpi-row');
  kpiRow.appendChild(kpiTile({
    label: 'Receita do mês', value: fmt0.format(receitaMes),
    foot: 'Salário líquido + aportes',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Despesas do mês', value: fmt0.format(abs(despesasMes)),
    foot: 'Fixos + variáveis + obra',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Resultado do mês', value: (resultadoMes >= 0 ? '+' : '−') + fmt0.format(abs(resultadoMes)),
    deltaText: resultadoMes >= 0 ? 'Superavitário' : 'Deficitário',
    deltaClass: resultadoMes >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saldo projetado · ' + monthShort(data.months[N - 1]), value: fmt0.format(saldoFinal),
    deltaText: saldoFinal >= 0 ? 'Acumulado positivo' : 'Acumulado negativo',
    deltaClass: saldoFinal >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Obra — % pago', value: fmt1pct(obraPctPago),
    meter: Math.min(obraPctPago, 100),
    foot: fmt0.format(data.obra.pago) + ' de ' + fmt0.format(data.obra.previsto),
  }));

  // ---------- Alertas ----------
  (function () {
    const list = document.getElementById('alert-list');
    const alerts = data.alerts || [];
    if (!alerts.length) {
      list.innerHTML = '<div class="alert-empty">Sem alertas hoje — nenhum sinal de gasto excessivo ou ineficiência identificado na última atualização.</div>';
      return;
    }
    alerts.forEach((a) => {
      const text = typeof a === 'string' ? a : a.text;
      const icon = typeof a === 'object' && a.icon ? a.icon : '⚠';
      const item = document.createElement('div');
      item.className = 'alert-item';
      item.innerHTML = `<span class="icon">${icon}</span><span>${text}</span>`;
      list.appendChild(item);
    });
  })();

  // ---------- Fluxo de Caixa chart ----------
  (function () {
    const svg = document.getElementById('fluxo-chart');
    const W = 720, H = 300, ML = 58, MR = 14, MT = 16, MB = 30;
    const plotW = W - ML - MR, plotH = H - MT - MB;

    const saldoMes = data.saldo_mes, saldoAcum = data.saldo_acumulado;
    const allVals = saldoMes.concat(saldoAcum).concat([0]);
    let vmin = Math.min(...allVals), vmax = Math.max(...allVals);
    const pad = (vmax - vmin) * 0.1 || 1000;
    vmin -= pad; vmax += pad;
    const y = (v) => MT + (vmax - v) / (vmax - vmin) * plotH;
    const slotW = plotW / N;
    const x = (i) => ML + slotW * i + slotW / 2;
    const zeroY = y(0);

    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

    const ticks = 4;
    for (let t = 0; t <= ticks; t++) {
      const v = vmin + (vmax - vmin) * (t / ticks);
      const gy = y(v);
      svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: gy, y2: gy, stroke: 'var(--gridline)', 'stroke-width': 1 }));
      const label = el('text', { x: ML - 8, y: gy + 3, 'text-anchor': 'end', class: 'axis-label' });
      label.textContent = (abs(v) >= 1000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(0));
      svg.appendChild(label);
    }
    svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: zeroY, y2: zeroY, class: 'zero-line' }));

    const barW = slotW * 0.5;
    const groups = [];
    for (let i = 0; i < N; i++) {
      const v = saldoMes[i];
      const g = el('g', {});
      const y0 = y(Math.max(v, 0)), y1 = y(Math.min(v, 0));
      const rect = el('rect', {
        x: x(i) - barW / 2, y: y0, width: barW, height: Math.max(y1 - y0, 1.5),
        rx: 3, class: v >= 0 ? 'bar-good' : 'bar-critical',
      });
      g.appendChild(rect);

      const hit = el('rect', { x: ML + slotW * i, y: MT, width: slotW, height: plotH, fill: 'transparent' });
      g.appendChild(hit);
      svg.appendChild(g);
      groups.push({ hit, i });

      if (N <= 14) {
        const lbl = el('text', { x: x(i), y: H - MB + 16, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = monthShort(data.months[i]).replace('/2', '/');
        svg.appendChild(lbl);
      }
    }

    let d = '';
    for (let i = 0; i < N; i++) d += (i === 0 ? 'M' : 'L') + x(i) + ',' + y(saldoAcum[i]) + ' ';
    svg.appendChild(el('path', { d, class: 'saldo-line' }));
    for (let i = 0; i < N; i++) {
      const r = (i === N - 1) ? 4.5 : 2.2;
      svg.appendChild(el('circle', { cx: x(i), cy: y(saldoAcum[i]), r, class: 'saldo-dot' }));
    }
    const finalLabel = el('text', { x: x(N - 1) - 6, y: y(saldoAcum[N - 1]) - 10, 'text-anchor': 'end', fill: 'var(--accent)', 'font-weight': 600, 'font-size': 11 });
    finalLabel.textContent = fmt0.format(saldoAcum[N - 1]);
    svg.appendChild(finalLabel);

    const tooltip = document.getElementById('fluxo-tooltip');
    const wrap = svg.parentElement;
    groups.forEach(({ hit, i }) => {
      hit.addEventListener('mousemove', (ev) => {
        const rect = wrap.getBoundingClientRect();
        tooltip.style.opacity = 1;
        let left = ev.clientX - rect.left + 14;
        if (left > rect.width - 170) left = ev.clientX - rect.left - 170;
        tooltip.style.left = left + 'px';
        tooltip.style.top = (ev.clientY - rect.top - 50) + 'px';
        tooltip.innerHTML = `
          <div class="t-month">${monthShort(data.months[i])}</div>
          <div class="t-row"><span>Resultado</span><span style="color:${saldoMes[i] >= 0 ? 'var(--good)' : 'var(--critical)'}">${fmt0.format(saldoMes[i])}</span></div>
          <div class="t-row"><span>Acumulado</span><span>${fmt0.format(saldoAcum[i])}</span></div>
        `;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    });
  })();

  // ---------- Obra ----------
  (function () {
    const o = data.obra;
    document.getElementById('obra-sub').textContent =
      fmt0.format(o.previsto) + ' previstos · ' + fmt1pct(obraPctPago) + ' pago até o momento';

    const lancado = (o.pago + o.pendente + o.futuro) || 1;
    const meter = document.getElementById('obra-meter');
    meter.innerHTML = `
      <div style="width:${o.pago / lancado * 100}%; background: var(--good)"></div>
      <div style="width:${o.pendente / lancado * 100}%; background: var(--warning)"></div>
      <div style="width:${o.futuro / lancado * 100}%; background: var(--neutral-track)"></div>
    `;

    const tbody = document.getElementById('obra-table-body');
    const rows = [...o.por_classificacao].sort((a, b) => b.previsto - a.previsto);
    rows.forEach((r) => {
      const denom = (r.pago + r.pendente + r.futuro) || 1;
      const pct = r.previsto ? (r.pago / r.previsto * 100) : 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.classificacao}</td>
        <td class="num">${fmt0.format(r.previsto)}</td>
        <td><div class="mini-bar">
          <div style="width:${r.pago / denom * 100}%; background: var(--good)"></div>
          <div style="width:${r.pendente / denom * 100}%; background: var(--warning)"></div>
          <div style="width:${r.futuro / denom * 100}%; background: var(--neutral-track)"></div>
        </div></td>
        <td class="num">${fmt1pct(pct)}</td>
      `;
      tbody.appendChild(tr);
    });
  })();

  // ---------- DRE Resumida ----------
  (function () {
    const dre = data.dre_resumo;
    document.getElementById('dre-sub').textContent =
      monthShort(data.months[REF]) + ' — Receita Líquida ' + fmt0.format(dre.receita_liquida);

    const kpis = document.getElementById('dre-kpis');
    const tiles = [
      { label: 'Receita', value: dre.receita_liquida, pct: null },
      { label: 'Custos fixos', value: dre.custos_fixos, pct: dre.custos_fixos_pct },
      { label: 'Custos variáveis', value: dre.custos_variaveis, pct: dre.custos_variaveis_pct },
      { label: 'Obra', value: dre.obra, pct: dre.obra_pct },
      { label: 'Margem líquida', value: dre.margem_liquida, pct: dre.margem_liquida_pct },
    ];
    tiles.forEach((t) => {
      const div = document.createElement('div');
      div.className = 'dre-kpi';
      const color = t.label === 'Margem líquida' ? (t.value >= 0 ? 'var(--good)' : 'var(--critical)') : (t.label === 'Receita' ? 'var(--good)' : 'var(--ink)');
      div.innerHTML = `
        <div class="label">${t.label}</div>
        <div class="value" style="color:${color}">${fmt0.format(t.value)}</div>
        ${t.pct !== null ? `<div class="pct">${fmt1pct(t.pct)} da receita</div>` : ''}
      `;
      kpis.appendChild(div);
    });

    const grupoLabel = { RECEITA_BRUTA: 'Receita', DEDUCOES: 'Dedução', FIXO: 'Fixo', VARIAVEL: 'Variável', OBRA: 'Obra', OUTRAS_RECEITAS: 'Outras receitas' };
    const tbody = document.getElementById('dre-detail-body');
    data.dre_detalhe.forEach((r) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.label}</td>
        <td><span class="grupo-chip ${r.grupo}">${grupoLabel[r.grupo] || r.grupo}</span></td>
        <td class="num" style="color:${r.valor >= 0 ? 'var(--good)' : 'var(--ink)'}">${fmt0.format(r.valor)}</td>
        <td class="num">${fmt1pct(r.pct_peso)}</td>
      `;
      tbody.appendChild(tr);
    });
  })();

  // ---------- Gastos por Tipo ----------
  (function () {
    const rows = data.gastos_por_tipo;
    document.getElementById('tipo-sub').textContent =
      'Cartão pessoal, fatura atual — ' + rows.reduce((s, r) => s + r.n_itens, 0) + ' itens';
    const palette = ['var(--cat-1)', 'var(--cat-2)', 'var(--cat-3)', 'var(--cat-4)', 'var(--cat-5)', 'var(--accent)', 'var(--good)', 'var(--warning)', 'var(--critical)'];
    const list = document.getElementById('tipo-list');
    const maxVal = Math.max(...rows.map((r) => r.total), 1);
    rows.forEach((r, i) => {
      const row = document.createElement('div');
      row.className = 'tipo-row';
      row.innerHTML = `
        <span class="name">${r.tipo}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${r.total / maxVal * 100}%; background:${palette[i % palette.length]}"></span></span>
        <span class="val">${fmt0.format(r.total)}</span>
      `;
      list.appendChild(row);
    });
  })();

  // ---------- Composição de despesas do mês (Fixos / Variáveis / Obra / Investimentos) ----------
  (function () {
    const cats = [
      { name: 'Custos fixos', value: abs(data.custos_fixos[REF]), color: 'var(--cat-1)' },
      { name: 'Custos variáveis', value: abs(data.custos_variaveis[REF]), color: 'var(--cat-2)' },
      { name: 'Obra (Pix)', value: abs(data.obra_pix[REF]), color: 'var(--cat-5)' },
      { name: 'Investimentos', value: abs(data.investimentos[REF]), color: 'var(--cat-3)' },
    ].filter((c) => c.value > 0);
    const total = cats.reduce((s, c) => s + c.value, 0) || 1;
    document.getElementById('composicao-sub').textContent =
      monthShort(data.months[REF]) + ' — total de ' + fmt0.format(total);

    const bar = document.getElementById('composicao-bar');
    const key = document.getElementById('composicao-key');
    cats.forEach((c) => {
      const pct = c.value / total * 100;
      const seg = document.createElement('div');
      seg.className = 'stack-seg';
      seg.style.width = pct + '%';
      seg.style.background = c.color;
      bar.appendChild(seg);

      const row = document.createElement('div');
      row.className = 'row';
      row.innerHTML = `<span class="swatch" style="background:${c.color}"></span>
        <span class="name">${c.name}</span>
        <span class="val">${fmt1pct(pct)} · ${fmt0.format(c.value)}</span>`;
      key.appendChild(row);
    });
  })();

  // ---------- footnotes ----------
  document.getElementById('footnotes').innerHTML = `
    <div><b>Mês de referência</b> para os indicadores mensais e distribuição de parcelas de cartão: ${monthShort(data.months[REF])}. Ajustável em <code>finlib.py</code> (REF_MONTH_INDEX).</div>
    <div><b>Saldo acumulado</b> parte de um saldo inicial de R$ 0 (placeholder) — substitua pelo saldo real em conta em <code>build_fluxo_caixa.py</code> (SALDO_INICIAL).</div>
    <div><b>Cartão pessoal</b> detalhado a partir de ${data.n_itens_cartao_pessoal} itens de Contas!Cartão Pessoal; ${data.n_itens_obra_cartao} itens marcados "Obra Apto" não entram nesse total — já contabilizados em Obra_Consolidado.</div>
    <div><b>Alertas</b> gerados pela rotina diária a partir dos dados frescos; também gravados como comentários nas células correspondentes das abas DRE_Mensal / Gastos_Por_Tipo.</div>
    <div>Fonte: planilha Google Sheets FL_2024 — abas DRE_Mensal, Obra_Consolidado, Fluxo_Caixa e Gastos_Por_Tipo. Regenerado diariamente às 7h (América/São Paulo).</div>
  `;
})();
