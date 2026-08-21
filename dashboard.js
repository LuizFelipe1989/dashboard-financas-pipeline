(function () {
  const data = JSON.parse(document.getElementById('dash-data').textContent);
  const REF = data.ref_month_index;
  const N = data.months.length;
  const abs = Math.abs;

  // ---------- formatting: parentheses + red for negatives, everywhere ----------
  const fmtNum = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  function fmt0(v) {
    const s = 'R$ ' + fmtNum.format(abs(v));
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
    label: 'Receita do mês', value: fmt0(receitaMes),
    foot: 'Salário líquido + aportes',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Despesas do mês', value: fmt0(despesasMes),
    foot: `Fixos + variáveis + obra · moradia (${fmt0(data.moradia_gabi[REF])}) paga pela Gabi`,
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Resultado do mês', value: (resultadoMes >= 0 ? '+' : '') + fmt0(resultadoMes),
    deltaText: resultadoMes >= 0 ? 'Superavitário' : 'Deficitário',
    deltaClass: resultadoMes >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saldo projetado · ' + monthShort(data.months[N - 1]), value: fmt0(saldoFinal),
    deltaText: saldoFinal >= 0 ? 'Acumulado positivo' : 'Acumulado negativo',
    deltaClass: saldoFinal >= 0 ? 'good' : 'critical',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Obra — % pago', value: fmt1pct(obraPctPago),
    meter: Math.min(obraPctPago, 100),
    foot: fmt0(data.obra.pago) + ' de ' + fmt0(data.obra.previsto),
  }));

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
      label.textContent = (v < 0 ? '(' : '') + (abs(v) >= 1000 ? (abs(v) / 1000).toFixed(0) + 'k' : abs(v).toFixed(0)) + (v < 0 ? ')' : '');
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
        rx: 2, class: v >= 0 ? 'bar-good' : 'bar-critical',
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
    finalLabel.textContent = fmt0(saldoAcum[N - 1]);
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
          <div class="t-row"><span>Resultado</span><span style="color:${saldoMes[i] >= 0 ? 'var(--good)' : 'var(--critical)'}">${fmt0(saldoMes[i])}</span></div>
          <div class="t-row"><span>Acumulado</span><span>${fmt0(saldoAcum[i])}</span></div>
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
      ['Obra', r.obra, r.obra_pct],
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
        <td><span class="grupo-chip ${row.grupo}">${row.grupo.replace('_', ' ')}</span></td>
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
    const receitaMedia = data.months.reduce((s, _, i) => s + (data.receita_liquida[i] + data.outras_receitas[i]), 0) / N;
    document.getElementById('cartao-obra-sub').textContent =
      `${fmt0(mesRefValor)} em ${monthShort(data.months[REF])} · pico de ${fmt0(Math.min(...series))} no horizonte`;

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
    refLbl.textContent = 'receita média';
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
        tooltip.innerHTML = `<div class="t-month">${monthShort(data.months[i])}</div><div class="t-row"><span>Cartão Obra</span><span>${fmt0(v)}</span></div>`;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
      if (i % 2 === 0) {
        const lbl = el('text', { x: x(i), y: H - MB + 14, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = monthShort(data.months[i]).split('/')[0];
        svg.appendChild(lbl);
      }
    }
  })();

  // ---------- Financiamento da obra (saldo total disponível vs investimento bloqueado) ----------
  (function () {
    const svg = document.getElementById('financiamento-chart');
    const f = data.financiamento_obra;
    document.getElementById('financiamento-sub').textContent =
      `${fmt0(f.investimento_bloqueado_total)} bloqueado como garantia do cartão · ${fmt0(f.saldo_disponivel_imediato)} disponível hoje`;

    const W = 340, H = 220, ML = 46, MR = 10, MT = 14, MB = 26;
    const plotW = W - ML - MR, plotH = H - MT - MB;
    const maxV = Math.max(...f.saldo_total_disponivel) * 1.1 || 1000;
    const y = (v) => MT + plotH - (v / maxV) * plotH;
    const slotW = plotW / N;
    const x = (i) => ML + slotW * i + slotW / 2;

    const ns = 'http://www.w3.org/2000/svg';
    const el = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

    [0, 0.5, 1].forEach((frac) => {
      const v = maxV * frac;
      const gy = y(v);
      svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: gy, y2: gy, stroke: 'var(--gridline)', 'stroke-width': 1 }));
      const lbl = el('text', { x: ML - 6, y: gy + 3, 'text-anchor': 'end', class: 'axis-label' });
      lbl.textContent = v >= 1000 ? (v / 1000).toFixed(0) + 'k' : v.toFixed(0);
      svg.appendChild(lbl);
    });

    // área liberada (accent) empilhada sobre o saldo imediato (neutro)
    let dTop = '', dBase = '';
    for (let i = 0; i < N; i++) {
      dTop += (i === 0 ? 'M' : 'L') + x(i) + ',' + y(f.saldo_total_disponivel[i]) + ' ';
    }
    for (let i = N - 1; i >= 0; i--) {
      dBase += 'L' + x(i) + ',' + y(f.saldo_disponivel_imediato) + ' ';
    }
    svg.appendChild(el('path', { d: dTop + dBase + 'Z', fill: 'var(--accent-soft)', stroke: 'none' }));
    svg.appendChild(el('path', { d: dTop, fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));
    svg.appendChild(el('line', { x1: ML, x2: W - MR, y1: y(f.saldo_disponivel_imediato), y2: y(f.saldo_disponivel_imediato), class: 'ref-line' }));

    for (let i = 0; i < N; i++) {
      const r = (i === N - 1) ? 4.5 : 2;
      svg.appendChild(el('circle', { cx: x(i), cy: y(f.saldo_total_disponivel[i]), r, fill: 'var(--accent)' }));
      if (i % 2 === 0) {
        const lbl = el('text', { x: x(i), y: H - MB + 14, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = monthShort(data.months[i]).split('/')[0];
        svg.appendChild(lbl);
      }
    }
    const finalLbl = el('text', { x: x(N - 1) - 6, y: y(f.saldo_total_disponivel[N - 1]) - 10, 'text-anchor': 'end', fill: 'var(--accent)', 'font-weight': 600, 'font-size': 11 });
    finalLbl.textContent = fmt0(f.saldo_total_disponivel[N - 1]);
    svg.appendChild(finalLbl);

    const tooltip = document.getElementById('financiamento-tooltip');
    const wrap = svg.parentElement;
    for (let i = 0; i < N; i++) {
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
          <div class="t-row"><span>Saldo total disponível</span><span>${fmt0(f.saldo_total_disponivel[i])}</span></div>
          <div class="t-row"><span>Investimento liberado</span><span>${fmt0(f.investimento_liberado_acumulado[i])}</span></div>
          <div class="t-row"><span>Ainda bloqueado</span><span>${fmt0(f.investimento_ainda_bloqueado[i])}</span></div>
        `;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    }
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

  // ---------- Gastos por Tipo ----------
  (function () {
    const list = document.getElementById('tipo-list');
    const total = data.gastos_por_tipo.reduce((s, t) => s + t.total, 0) || 1;
    document.getElementById('tipo-sub').textContent = 'Fatura atual do cartão pessoal — total de ' + fmt0(total);
    data.gastos_por_tipo.forEach((t, i) => {
      const color = `var(--cat-${(i % 5) + 1})`;
      const row = document.createElement('div');
      row.className = 'bar-list-row';
      row.innerHTML = `
        <span class="name">${t.tipo}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${t.pct}%; background:${color}"></span></span>
        <span class="val">${fmt0(t.total)}</span>
      `;
      list.appendChild(row);
    });
  })();

  // ---------- Composição de Despesas do Mês ----------
  (function () {
    const cats = [
      { name: 'Custos Fixos', value: abs(data.custos_fixos[REF]) },
      { name: 'Custos Variáveis', value: abs(data.custos_variaveis[REF]) },
      { name: 'Obra (Pix)', value: abs(data.obra_pix[REF]) },
      { name: 'Cartão Obra (parcelas)', value: abs(data.cartao_obra_mensal[REF]) },
    ];
    const total = cats.reduce((s, c) => s + c.value, 0) || 1;
    document.getElementById('composicao-sub').textContent =
      monthShort(data.months[REF]) + ' — total de ' + fmt0(total);

    const list = document.getElementById('composicao-list');
    cats.sort((a, b) => b.value - a.value).forEach((c, i) => {
      const pct = c.value / total * 100;
      const color = `var(--cat-${(i % 5) + 1})`;
      const row = document.createElement('div');
      row.className = 'bar-list-row';
      row.innerHTML = `
        <span class="name">${c.name}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${pct}%; background:${color}"></span></span>
        <span class="val">${fmt0(c.value)}</span>
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
    <div><b>Moradia (Financiamento, Condomínio, IPTU, Energia, Gás, Internet)</b> passou a ser paga diretamente pela Gabi — informativa na DRE, não entra mais na margem líquida.</div>
    <div><b>Financiamento da obra</b>: ${fmt0(data.financiamento_obra.investimento_bloqueado_total)} em RF Ref DI Plus Ágil ficam bloqueados como garantia do limite do cartão e são liberados conforme as parcelas de obra no cartão são pagas — saldo do extrato BB em 20/08/2026.</div>
    <div><b>Cartão pessoal</b> detalhado a partir de ${data.n_itens_cartao_pessoal} itens de Contas!Cartão Pessoal; ${data.n_itens_obra_cartao} itens marcados "Obra Apto" não entram no total de despesas pessoais — já contabilizados em Obra_Consolidado.</div>
    <div>Fonte: planilha Google Sheets FL_2024 — abas DRE_Mensal, Obra_Consolidado, Fluxo_Caixa e Gastos_Por_Tipo. Regenerar com os scripts <code>build_dre.py</code>, <code>build_obra.py</code>, <code>build_fluxo_caixa.py</code>, <code>build_gastos_tipo.py</code>.</div>
  `;
})();
