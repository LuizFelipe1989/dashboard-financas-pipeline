(function () {
  const data = JSON.parse(document.getElementById('dash-data').textContent);
  const REF = data.ref_month_index;
  const N = data.months.length;
  const abs = Math.abs;

  // ---------- formatting: parentheses + red for negatives, everywhere ----------
  const fmtNum = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  function fmt0(v) {
    const s = 'R$ ' + fmtNum.format(abs(v));
    return v < 0 ? `(${s})` : s;
  }
  function moneySpan(v) {
    return `<span class="${v < 0 ? 'neg' : ''}">${fmt0(v)}</span>`;
  }
  function fmt1pct(v) {
    const s = abs(v).toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + '%';
    return v < 0 ? `(${s})` : s;
  }
  const monthShort = (m) => { const [mon, yr] = m.split('./'); return mon.charAt(0).toUpperCase() + mon.slice(1) + '/' + yr; };

  // ---------- meta ----------
  document.getElementById('meta-ref').textContent = 'Mês de referência: ' + monthShort(data.months[REF]);
  document.getElementById('meta-horizon').textContent = 'Horizonte: ' + monthShort(data.months[0]) + ' – ' + monthShort(data.months[N - 1]);

  // ---------- KPI row ----------
  const receitaMes = data.entradas[REF];
  const despesasMes = data.saidas[REF];
  const resultadoMes = data.saldo_liquido[REF];
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
    label: 'Entradas do mês', value: fmt0(receitaMes),
    foot: 'Salário líquido + aportes',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saídas do mês', value: moneySpan(despesasMes),
    foot: `Fixos + variáveis (com obra) · Saúde (${fmt0(data.moradia_gabi[REF])}) paga pela Gabi`,
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saldo líquido do mês', value: moneySpan(resultadoMes),
    deltaText: resultadoMes >= 0 ? 'Superavitário' : 'Deficitário',
    deltaClass: resultadoMes >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saldo projetado · ' + monthShort(data.months[N - 1]), value: moneySpan(saldoFinal),
    deltaText: saldoFinal >= 0 ? 'Acumulado positivo' : 'Acumulado negativo',
    deltaClass: saldoFinal >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Obra — % pago', value: fmt1pct(obraPctPago),
    meter: Math.min(obraPctPago, 100),
    foot: fmt0(data.obra.pago) + ' de ' + fmt0(data.obra.previsto),
  }));

  // ---------- Fluxo de Caixa: entradas (cima) / saídas (baixo) + saldo líquido acumulado ----------
  (function () {
    const svg = document.getElementById('fluxo-chart');
    const W = 720, H = 300, ML = 58, MR = 14, MT = 16, MB = 30;
    const plotW = W - ML - MR, plotH = H - MT - MB;

    const entradas = data.entradas, saidas = data.saidas, saldoAcum = data.saldo_acumulado;
    const allVals = entradas.concat(saidas).concat(saldoAcum).concat([0]);
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
      label.textContent = (v < 0 ? '(' : '') + (abs(v) >= 1000 ? (abs(v) / 1000).toFixed(0) + 'k' : abs(v).toFixed(0)) + (v < 0 ? ')' : '');
      svg.appendChild(label);
    }
    svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: zeroY, y2: zeroY, class: 'zero-line' }));

    const barW = slotW * 0.34;
    const groups = [];
    for (let i = 0; i < N; i++) {
      const g = el('g', {});
      const yEntTop = y(entradas[i]);
      g.appendChild(el('rect', { x: x(i) - barW - 1, y: yEntTop, width: barW, height: Math.max(zeroY - yEntTop, 1.5), rx: 2, class: 'bar-good' }));
      const ySaiBot = y(saidas[i]);
      g.appendChild(el('rect', { x: x(i) + 1, y: zeroY, width: barW, height: Math.max(ySaiBot - zeroY, 1.5), rx: 2, class: 'bar-critical' }));

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
    const finalLabel = el('text', { x: x(N - 1) - 6, y: y(saldoAcum[N - 1]) - 10, 'text-anchor': 'end', fill: saldoAcum[N - 1] < 0 ? 'var(--critical)' : 'var(--accent)', 'font-weight': 600, 'font-size': 11 });
    finalLabel.textContent = fmt0(saldoAcum[N - 1]);
    svg.appendChild(finalLabel);

    const tooltip = document.getElementById('fluxo-tooltip');
    const wrap = svg.parentElement;
    groups.forEach(({ hit, i }) => {
      hit.addEventListener('mousemove', (ev) => {
        const rect = wrap.getBoundingClientRect();
        tooltip.style.opacity = 1;
        let left = ev.clientX - rect.left + 14;
        if (left > rect.width - 180) left = ev.clientX - rect.left - 180;
        tooltip.style.left = left + 'px';
        tooltip.style.top = (ev.clientY - rect.top - 66) + 'px';
        tooltip.innerHTML = `
          <div class="t-month">${monthShort(data.months[i])}</div>
          <div class="t-row"><span>Entradas</span><span style="color:var(--good)">${fmt0(entradas[i])}</span></div>
          <div class="t-row"><span>Saídas</span><span style="color:var(--critical)">${fmt0(saidas[i])}</span></div>
          <div class="t-row"><span>Saldo líquido</span>${moneySpan(entradas[i] + saidas[i])}</div>
          <div class="t-row"><span>Acumulado</span>${moneySpan(saldoAcum[i])}</div>
        `;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    });
  })();

  // ---------- DRE resumida ----------
  (function () {
    const r = data.dre_resumo;
    document.getElementById('dre-sub').textContent =
      monthShort(data.months[REF]) + ' — margem líquida ' + fmt1pct(r.margem_liquida_pct) + ' da receita';

    const kpis = document.getElementById('dre-kpis');
    const rows = [
      ['Receita Líquida', r.receita_liquida, null],
      ['Custos Fixos', r.custos_fixos, r.custos_fixos_pct],
      ['Custos Variáveis', r.custos_variaveis, r.custos_variaveis_pct],
      ['Margem Líquida', r.margem_liquida, r.margem_liquida_pct],
    ];
    rows.forEach(([label, val, pct]) => {
      const el = document.createElement('div');
      el.className = 'dre-kpi';
      el.innerHTML = `
        <div class="label">${label}</div>
        <div class="value">${moneySpan(val)}</div>
        ${pct !== null ? `<div class="pct">${fmt1pct(pct)} da receita</div>` : ''}
      `;
      kpis.appendChild(el);
    });

    const tbody = document.getElementById('dre-detail-body');
    data.dre_detalhe.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.label}</td>
        <td><span class="grupo-chip ${row.grupo}">${row.grupo_label}</span></td>
        <td class="num">${moneySpan(row.valor)}</td>
        <td class="num">${fmt1pct(row.pct_peso)}</td>
      `;
      tbody.appendChild(tr);
    });
  })();

  // ---------- Cartão Obra — parcelas futuras (mini bar chart) ----------
  (function () {
    const svg = document.getElementById('cartao-obra-chart');
    const series = data.cartao_obra_mensal;
    const mesRefValor = abs(series[REF]);
    const receitaMedia = data.months.reduce((s, _, i) => s + data.entradas[i], 0) / N;
    document.getElementById('cartao-obra-sub').textContent =
      `${fmt0(mesRefValor)} em ${monthShort(data.months[REF])} · fonte: Fluxo_Apto_Realizado (linha 55) · pico de ${fmt0(Math.min(...series))} no horizonte`;

    const W = 340, H = 220, ML = 46, MR = 10, MT = 14, MB = 26;
    const plotW = W - ML - MR, plotH = H - MT - MB;
    const maxV = Math.max(receitaMedia, ...series.map(abs)) * 1.1 || 1000;
    const y = (v) => MT + plotH - (v / maxV) * plotH;
    const slotW = plotW / N;
    const x = (i) => ML + slotW * i + slotW / 2;

    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

    [0, 0.5, 1].forEach((f) => {
      const v = maxV * f;
      const gy = y(v);
      svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: gy, y2: gy, stroke: 'var(--gridline)', 'stroke-width': 1 }));
      const lbl = el('text', { x: ML - 6, y: gy + 3, 'text-anchor': 'end', class: 'axis-label' });
      lbl.textContent = v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(0);
      svg.appendChild(lbl);
    });

    const refY = y(receitaMedia);
    svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: refY, y2: refY, class: 'ref-line' }));
    const refLbl = el('text', { x: W - MR, y: refY - 4, 'text-anchor': 'end', class: 'axis-label' });
    refLbl.textContent = 'entradas médias';
    svg.appendChild(refLbl);

    const barW = slotW * 0.55;
    const tooltip = document.getElementById('cartao-obra-tooltip');
    const wrap = svg.parentElement;
    for (let i = 0; i < N; i++) {
      const v = abs(series[i]);
      const barY = y(v);
      const isHeavy = v >= receitaMedia * 0.6;
      const g = el('g', {});
      g.appendChild(el('rect', { x: x(i) - barW / 2, y: barY, width: barW, height: Math.max(MT + plotH - barY, 1), rx: 2, class: isHeavy ? 'bar-critical' : 'bar-neutral' }));
      const hit = el('rect', { x: ML + slotW * i, y: MT, width: slotW, height: plotH, fill: 'transparent' });
      g.appendChild(hit);
      svg.appendChild(g);
      hit.addEventListener('mousemove', (ev) => {
        const rect = wrap.getBoundingClientRect();
        tooltip.style.opacity = 1;
        let left = ev.clientX - rect.left + 14;
        if (left > rect.width - 160) left = ev.clientX - rect.left - 160;
        tooltip.style.left = left + 'px';
        tooltip.style.top = (ev.clientY - rect.top - 40) + 'px';
        tooltip.innerHTML = `<div class="t-month">${monthShort(data.months[i])}</div><div class="t-row"><span>Cartão Obra</span>${moneySpan(-v)}</div>`;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
      if (i % 2 === 0) {
        const lbl = el('text', { x: x(i), y: H - MB + 14, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = monthShort(data.months[i]).split('/')[0];
        svg.appendChild(lbl);
      }
    }
  })();

  // ---------- Financiamento da obra: investimento cobrindo o gap parcela-salário ----------
  (function () {
    const svg = document.getElementById('financiamento-chart');
    const f = data.financiamento_obra;
    const jul27 = data.jul27_index;
    document.getElementById('financiamento-sub').textContent =
      `${fmt0(f.investimento_bloqueado_total)} disponíveis hoje · projeção em ${monthShort(data.months[jul27])}: ${fmt0(f.saldo_investimento[jul27])}`;

    const W = 340, H = 220, ML = 46, MR = 10, MT = 14, MB = 26;
    const plotW = W - ML - MR, plotH = H - MT - MB;
    const series = f.saldo_investimento;
    const allV = series.concat([0, f.investimento_bloqueado_total]);
    let vmin = Math.min(...allV), vmax = Math.max(...allV);
    const pad = (vmax - vmin) * 0.12 || 1000;
    vmin -= pad; vmax += pad;
    const y = (v) => MT + (vmax - v) / (vmax - vmin) * plotH;
    const slotW = plotW / N;
    const x = (i) => ML + slotW * i + slotW / 2;

    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

    [0, 0.5, 1].forEach((frac) => {
      const v = vmin + (vmax - vmin) * frac;
      const gy = y(v);
      svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: gy, y2: gy, stroke: 'var(--gridline)', 'stroke-width': 1 }));
      const lbl = el('text', { x: ML - 6, y: gy + 3, 'text-anchor': 'end', class: 'axis-label' });
      lbl.textContent = (v < 0 ? '(' : '') + (abs(v) >= 1000 ? (abs(v) / 1000).toFixed(0) + 'k' : abs(v).toFixed(0)) + (v < 0 ? ')' : '');
      svg.appendChild(lbl);
    });
    if (vmin < 0 && vmax > 0) {
      svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: y(0), y2: y(0), class: 'zero-line' }));
    }

    let dLine = '';
    for (let i = 0; i < N; i++) dLine += (i === 0 ? 'M' : 'L') + x(i) + ',' + y(series[i]) + ' ';
    const dArea = dLine + `L${x(N - 1)},${y(0)} L${x(0)},${y(0)} Z`;
    svg.appendChild(el('path', { d: dArea, fill: 'var(--accent-soft)', stroke: 'none' }));
    svg.appendChild(el('path', { d: dLine, fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));

    // marca o mês de Jul/27 pedido explicitamente
    svg.appendChild(el('line', { x1: x(jul27), x2: x(jul27), y1: MT, y2: MT + plotH, class: 'ref-line' }));

    const tooltip = document.getElementById('financiamento-tooltip');
    const wrap = svg.parentElement;
    for (let i = 0; i < N; i++) {
      const isMarked = i === jul27 || i === N - 1;
      const r = isMarked ? 4.5 : 2;
      svg.appendChild(el('circle', { cx: x(i), cy: y(series[i]), r, fill: series[i] < 0 ? 'var(--critical)' : 'var(--accent)' }));
      if (i % 2 === 0) {
        const lbl = el('text', { x: x(i), y: H - MB + 14, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = monthShort(data.months[i]).split('/')[0];
        svg.appendChild(lbl);
      }
      const hit = el('rect', { x: ML + slotW * i, y: MT, width: slotW, height: plotH, fill: 'transparent' });
      svg.appendChild(hit);
      hit.addEventListener('mousemove', (ev) => {
        const rect = wrap.getBoundingClientRect();
        tooltip.style.opacity = 1;
        let left = ev.clientX - rect.left + 14;
        if (left > rect.width - 170) left = ev.clientX - rect.left - 170;
        tooltip.style.left = left + 'px';
        tooltip.style.top = (ev.clientY - rect.top - 54) + 'px';
        tooltip.innerHTML = `
          <div class="t-month">${monthShort(data.months[i])}</div>
          <div class="t-row"><span>Saldo do investimento</span>${moneySpan(series[i])}</div>
          <div class="t-row"><span>Saque no mês</span>${moneySpan(-f.saque_mensal[i])}</div>
        `;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    }
    const jul27Lbl = el('text', { x: x(jul27), y: y(series[jul27]) + (series[jul27] < 0 ? 16 : -10), 'text-anchor': 'middle', fill: series[jul27] < 0 ? 'var(--critical)' : 'var(--accent)', 'font-weight': 600, 'font-size': 11 });
    jul27Lbl.textContent = fmt0(series[jul27]);
    svg.appendChild(jul27Lbl);
  })();

  // ---------- Obra ----------
  (function () {
    const o = data.obra;
    document.getElementById('obra-sub').textContent =
      fmt0(o.previsto) + ' previstos · ' + fmt1pct(obraPctPago) + ' pago até o momento';

    const p = data.pagamentos;
    const tiles = document.getElementById('pagamentos-tiles');
    [
      ['Pago até agora (Pix + Cartão)', p.pago_total],
      ['Pix pendente a realizar', p.pix_pendente],
      ['Cartão a vencer (parcelas futuras)', p.cartao_futuro],
    ].forEach(([label, val]) => {
      const el = document.createElement('div');
      el.className = 'stat-tile';
      el.innerHTML = `<div class="label">${label}</div><div class="value">${fmt0(val)}</div>`;
      tiles.appendChild(el);
    });

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
        <td class="num">${fmt0(r.previsto)}</td>
        <td class="num">${fmt0(r.pago)}</td>
        <td class="num">${fmt0(r.pendente)}</td>
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

  // ---------- Gastos por Tipo: Fixo Mensal / Parcelado / Discricionário, com subtotais ----------
  (function () {
    const container = document.getElementById('natureza-groups');
    const grandTotal = data.gastos_por_natureza.reduce((s, g) => s + g.total, 0) || 1;
    document.getElementById('tipo-sub').textContent = 'Fatura atual do cartão — total de ' + fmt0(grandTotal);

    data.gastos_por_natureza.forEach((g, gi) => {
      const group = document.createElement('div');
      group.className = 'natureza-group';
      group.innerHTML = `<div class="natureza-head"><span class="name">${g.natureza}</span><span class="val">${fmt0(g.total)} · ${g.pct.toFixed(1)}%</span></div>`;
      const list = document.createElement('div');
      list.className = 'bar-list';
      g.tipos.forEach((t, i) => {
        const color = `var(--cat-${((gi * 2 + i) % 5) + 1})`;
        const row = document.createElement('div');
        row.className = 'bar-list-row';
        const pctOfGroup = g.total ? (t.total / g.total * 100) : 0;
        row.innerHTML = `
          <span class="name">${t.tipo}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${pctOfGroup}%; background:${color}"></span></span>
          <span class="val">${fmt0(t.total)}</span>
        `;
        list.appendChild(row);
      });
      group.appendChild(list);
      container.appendChild(group);
    });
  })();

  // ---------- Composição de Despesas do Mês (a partir da DRE, linhas Fixo+Variável) ----------
  (function () {
    const items = data.dre_detalhe
      .filter((r) => r.grupo === 'FIXO' || r.grupo === 'VARIAVEL')
      .sort((a, b) => abs(b.valor) - abs(a.valor))
      .slice(0, 7);
    const total = items.reduce((s, r) => s + abs(r.valor), 0) || 1;
    document.getElementById('composicao-sub').textContent =
      monthShort(data.months[REF]) + ' — principais linhas de saída (Fixo + Variável)';

    const list = document.getElementById('composicao-list');
    items.forEach((r, i) => {
      const pct = abs(r.valor) / total * 100;
      const color = `var(--cat-${(i % 5) + 1})`;
      const row = document.createElement('div');
      row.className = 'bar-list-row';
      row.innerHTML = `
        <span class="name">${r.label}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${pct}%; background:${color}"></span></span>
        <span class="val">${moneySpan(r.valor)}</span>
      `;
      list.appendChild(row);
    });
  })();

  // ---------- alertas ----------
  (function () {
    const list = document.getElementById('alert-list');
    if (!data.alerts || data.alerts.length === 0) {
      list.innerHTML = '<div class="alert-empty">Sem alertas hoje.</div>';
      return;
    }
    data.alerts.forEach((a) => {
      const el = document.createElement('div');
      el.className = 'alert-item';
      el.innerHTML = `<span class="icon">${a.icon || '⚠️'}</span><span>${a.text}</span>`;
      list.appendChild(el);
    });
  })();

  // ---------- footnotes ----------
  document.getElementById('footnotes').innerHTML = `
    <div><b>Mês de referência</b> para os indicadores mensais e distribuição de parcelas de cartão: ${monthShort(data.months[REF])}.</div>
    <div><b>Moradia Saúde</b> (aluguel + condomínio + Enel + internet + cartão da casa) passou a ser paga diretamente pela Gabi — informativa, não entra nas saídas. A moradia do apartamento novo (VM) continua nos Custos Fixos.</div>
    <div><b>Cartão Obra</b> usa o valor mensal já projetado em Fluxo_Apto_Realizado (linha 55 — Cartão), classificado como despesa Variável na DRE.</div>
    <div><b>Financiamento da obra</b>: quando a parcela do cartão da obra supera o salário líquido do mês, a diferença é retirada do investimento (${fmt0(data.financiamento_obra.investimento_bloqueado_total)} hoje) para o caixa nunca fechar negativo — projeção até ${monthShort(data.months[N - 1])}.</div>
    <div><b>Cartão pessoal</b> detalhado a partir de ${data.n_itens_cartao_pessoal} itens de Contas!Cartão Pessoal; ${data.n_itens_obra_cartao} itens marcados "Obra Apto" aparecem em Gastos por Tipo mas o valor mensal de obra usado na DRE vem de Fluxo_Apto_Realizado, não deste cadastro.</div>
    <div>Fonte: planilha Google Sheets FL_2024 — abas DRE_Mensal, Obra_Consolidado, Fluxo_Caixa e Gastos_Por_Tipo. Regenerar com <code>daily_update.py</code>.</div>
  `;
})();
