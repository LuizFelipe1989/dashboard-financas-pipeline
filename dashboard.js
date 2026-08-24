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
    return `<span class="sv${v < 0 ? ' neg' : ''}">${fmt0(v)}</span>`;
  }
  function fmt1pct(v) {
    const s = abs(v).toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 }) + '%';
    return v < 0 ? `(${s})` : s;
  }
  const monthShort = (m) => { const [mon, yr] = m.split('./'); return mon.charAt(0).toUpperCase() + mon.slice(1) + '/' + yr; };

  // Envolve qualquer "R$ ..." solto num texto narrativo (alerta, rodapé, subtítulo)
  // numa <span class="sv"> pra entrar no modo privacidade — mais simples e robusto
  // que caçar cada interpolação de fmt0()/fmt_brl() individualmente pelo arquivo.
  function wrapMoney(html) {
    return html.replace(/\(?R\$\s?\(?-?[\d][\d.,]*\)?\)?/g, (m) => `<span class="sv">${m}</span>`);
  }

  // ---------- modo privacidade (ocultar valores) ----------
  (function () {
    const btn = document.getElementById('privacy-toggle');
    const iconEye = document.getElementById('privacy-icon-eye');
    const iconEyeOff = document.getElementById('privacy-icon-eye-off');
    const label = document.getElementById('privacy-label');
    function apply(on) {
      document.body.classList.toggle('privacy-on', on);
      btn.setAttribute('aria-pressed', String(on));
      iconEye.style.display = on ? 'none' : '';
      iconEyeOff.style.display = on ? '' : 'none';
      label.textContent = on ? 'Mostrar valores' : 'Ocultar valores';
    }
    let saved = false;
    try { saved = localStorage.getItem('dash_privacy_on') === '1'; } catch (e) {}
    apply(saved);
    btn.addEventListener('click', () => {
      const on = !document.body.classList.contains('privacy-on');
      apply(on);
      try { localStorage.setItem('dash_privacy_on', on ? '1' : '0'); } catch (e) {}
    });
  })();

  // ---------- meta ----------
  document.getElementById('meta-ref').textContent = 'Próximo mês (fatura 10/' + data.months[REF].split('./')[0] + '): ' + monthShort(data.months[REF]);
  document.getElementById('meta-horizon').textContent = 'Horizonte: ' + monthShort(data.months[0]) + ' – ' + monthShort(data.months[N - 1]);

  // ---------- KPI row ----------
  const receitaMes = data.entradas[REF];
  const despesasMes = data.saidas[REF];
  const resultadoMes = data.saldo_liquido[REF];
  const saldoFinal = data.saldo_acumulado[N - 1];
  const obraPctPago = data.obra.previsto ? (data.obra.pago / data.obra.previsto * 100) : 0;

  function donutSvg(pct, colorVar, size, stroke) {
    size = size || 56; stroke = stroke || 7;
    const p = Math.max(0, Math.min(100, pct));
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    const offset = c * (1 - p / 100);
    const cx = size / 2, cy = size / 2;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--neutral-track)" stroke-width="${stroke}" />
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colorVar}" stroke-width="${stroke}"
        stroke-dasharray="${c}" stroke-dashoffset="${offset}" stroke-linecap="round"
        transform="rotate(-90 ${cx} ${cy})" />
    </svg>`;
  }

  function kpiTile({ label, value, deltaText, deltaClass, foot, meter, donut }) {
    const el = document.createElement('div');
    el.className = 'kpi-tile' + (donut ? ' has-donut' : '');
    const body = wrapMoney(`
      <div class="label">${label}</div>
      ${donut ? '' : `<div class="value">${value}</div>`}
      ${deltaText ? `<span class="delta ${deltaClass}">${deltaText}</span>` : ''}
      ${meter !== undefined ? `<div class="meter-track"><div class="meter-fill" style="width:${meter}%"></div></div>` : ''}
      ${foot ? `<div class="foot">${foot}</div>` : ''}
    `);
    if (donut) {
      const size = donut.size || 56;
      el.innerHTML = `
        <div class="donut-wrap" style="width:${size}px;height:${size}px">
          ${donutSvg(donut.pct, donut.color || 'var(--accent)', size, donut.stroke)}
          <div class="donut-value" style="font-size:${size <= 48 ? 10.5 : 12}px;color:${donut.color || 'var(--accent)'}">${fmt1pct(donut.pct)}</div>
        </div>
        <div class="kpi-body">${body}</div>
      `;
    } else {
      el.innerHTML = body;
    }
    return el;
  }

  const kpiRow = document.getElementById('kpi-row');
  kpiRow.appendChild(kpiTile({
    label: 'Entradas do mês', value: fmt0(receitaMes),
    foot: 'Salário líquido',
  }));
  kpiRow.appendChild(kpiTile({
    label: 'Saídas do mês', value: moneySpan(despesasMes),
    foot: 'Fixos + variáveis (com obra)',
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
    label: 'Obra — % pago',
    donut: { pct: obraPctPago, color: 'var(--accent)' },
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
        const lbl = el('text', { x: x(i), y: H - MB + 16, 'text-anchor': 'middle', class: 'axis-label', 'font-size': 9.5 });
        lbl.textContent = monthShort(data.months[i]);
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
        tooltip.innerHTML = wrapMoney(`
          <div class="t-month">${monthShort(data.months[i])}</div>
          <div class="t-row"><span>Entradas</span><span style="color:var(--good)">${fmt0(entradas[i])}</span></div>
          <div class="t-row"><span>Saídas</span><span style="color:var(--critical)">${fmt0(saidas[i])}</span></div>
          <div class="t-row"><span>Saldo líquido</span>${moneySpan(entradas[i] + saidas[i])}</div>
          <div class="t-row"><span>Acumulado</span>${moneySpan(saldoAcum[i])}</div>
        `);
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    });
  })();

  // ---------- DRE resumida ----------
  (function () {
    const r = data.dre_resumo;
    document.getElementById('dre-sub').textContent =
      monthShort(data.months[REF]) + ' — margem líquida (sem obra) ' + fmt1pct(r.margem_liquida_pct) + ' da receita';

    const kpis = document.getElementById('dre-kpis');
    const rows = [
      ['Receita Líquida', r.receita_liquida, null, false],
      ['Custo Fixo', r.custos_fixos, r.custos_fixos_pct, false],
      ['Custo Variável', r.custos_variaveis, r.custos_variaveis_pct, false],
      ['Margem Líquida', r.margem_liquida, r.margem_liquida_pct, false],
      ['Custo Obra', r.custo_obra, r.custo_obra_pct, true],
    ];
    rows.forEach(([label, val, pct, isObra]) => {
      const el = document.createElement('div');
      el.className = 'dre-kpi' + (isObra ? ' is-obra' : '');
      const showDonut = label === 'Margem Líquida' || label === 'Custo Obra';
      const donutColor = isObra ? 'var(--warning)' : (val >= 0 ? 'var(--good)' : 'var(--critical)');
      el.innerHTML = `
        <div class="label">${label}</div>
        <div class="dre-kpi-row">
          <div class="kpi-body">
            <div class="value">${moneySpan(val)}</div>
            ${pct !== null ? `<div class="pct">${fmt1pct(pct)} da receita</div>` : ''}
          </div>
          ${showDonut && pct !== null ? `<div class="donut-wrap" style="width:38px;height:38px">${donutSvg(pct, donutColor, 38, 5)}</div>` : ''}
        </div>
      `;
      kpis.appendChild(el);
    });

    // Tabela mês a mês (jul./26 – ago./27), mesma estrutura seccionada da DRE_Mensal —
    // Custo Obra segue nas linhas normais (Variável Obra), separado só nos KPIs acima.
    const thead = document.getElementById('dre-detail-head');
    const headCells = ['Linha'].concat(data.months.map(monthShort)).concat(['Total']);
    thead.innerHTML = `<tr>${headCells.map((h, i) => `<th${i > 0 ? ' class="num"' : ''}>${h}</th>`).join('')}</tr>`;

    const tbody = document.getElementById('dre-detail-body');
    data.dre_detalhe.forEach((row) => {
      const tr = document.createElement('tr');
      if (row.kind === 'HEADER') {
        tr.className = 'row-header';
        tr.innerHTML = `<td colspan="${headCells.length}">${row.label}</td>`;
      } else {
        tr.className = row.kind === 'SUBTOTAL' ? 'row-subtotal' : 'row-line';
        const total = row.vals.reduce((s, v) => s + v, 0);
        const cells = row.vals.map((v) => `<td class="num">${moneySpan(v)}</td>`).join('');
        tr.innerHTML = `<td>${row.label}</td>${cells}<td class="num">${moneySpan(total)}</td>`;
      }
      tbody.appendChild(tr);
    });
  })();

  // ---------- Cartão Obra — parcelas futuras (mini bar chart) ----------
  (function () {
    const svg = document.getElementById('cartao-obra-chart');
    const series = data.cartao_obra_mensal;
    const mesRefValor = abs(series[REF]);
    const receitaMedia = data.months.reduce((s, _, i) => s + data.entradas[i], 0) / N;
    document.getElementById('cartao-obra-sub').innerHTML = wrapMoney(
      `${fmt0(mesRefValor)} em ${monthShort(data.months[REF])} · fonte: Fluxo_Apto_Realizado (linha 55) · pico de ${fmt0(Math.min(...series))} no horizonte`);

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
      const g = el('g', {});
      g.appendChild(el('rect', { x: x(i) - barW / 2, y: barY, width: barW, height: Math.max(MT + plotH - barY, 1), rx: 2, class: 'bar-critical' }));
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

  // ---------- Financiamento da obra: salário paga o cartão primeiro, fundo cobre o resto ----------
  (function () {
    const svg = document.getElementById('financiamento-chart');
    const f = data.financiamento_obra;
    const jul27 = data.jul27_index;
    document.getElementById('financiamento-sub').innerHTML = wrapMoney(
      `${fmt0(f.investimento_bloqueado_total)} disponíveis hoje · projeção em ${monthShort(data.months[jul27])}: ${fmt0(f.saldo_investimento[jul27])}`);

    // Ponte histórica: um ponto "Início" com a posição bruta do fundo antes de ser
    // consumido pela obra (~R$144k em jul./26), antes da série modelada (que já parte
    // do saldo atual, ~R$73,7k). Não há granularidade mensal real entre os dois — é
    // um único segmento ilustrando "o fundo caiu de X pra Y ajudado pelo salário",
    // não uma projeção mês a mês. Array local (labels + série) só pra este gráfico,
    // não mexe no N/data.months compartilhado pelos outros gráficos.
    const localLabels = ['Início', ...data.months];
    const series = [f.posicao_inicial, ...f.saldo_investimento];
    const localN = series.length;
    const localJul27 = jul27 + 1;

    const W = 340, H = 220, ML = 46, MR = 10, MT = 14, MB = 26;
    const plotW = W - ML - MR, plotH = H - MT - MB;
    const allV = series.concat([0, f.investimento_bloqueado_total]);
    let vmin = Math.min(...allV), vmax = Math.max(...allV);
    const pad = (vmax - vmin) * 0.12 || 1000;
    vmin -= pad; vmax += pad;
    const y = (v) => MT + (vmax - v) / (vmax - vmin) * plotH;
    const slotW = plotW / localN;
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
    for (let i = 0; i < localN; i++) dLine += (i === 0 ? 'M' : 'L') + x(i) + ',' + y(series[i]) + ' ';
    const dArea = dLine + `L${x(localN - 1)},${y(0)} L${x(0)},${y(0)} Z`;
    svg.appendChild(el('path', { d: dArea, fill: 'var(--accent-soft)', stroke: 'none' }));
    // segmento histórico (Início -> primeiro mês real) tracejado, pra deixar claro que
    // é uma ponte ilustrativa e não dado mensal real
    svg.appendChild(el('path', { d: `M${x(0)},${y(series[0])} L${x(1)},${y(series[1])}`, fill: 'none', stroke: 'var(--ink-muted)', 'stroke-width': 2, 'stroke-dasharray': '4 3' }));
    svg.appendChild(el('path', { d: dLine.replace(/^M[^L]*L/, 'M') , fill: 'none', stroke: 'var(--accent)', 'stroke-width': 2 }));

    // marca o mês de Jul/27 pedido explicitamente
    svg.appendChild(el('line', { x1: x(localJul27), x2: x(localJul27), y1: MT, y2: MT + plotH, class: 'ref-line' }));

    const tooltip = document.getElementById('financiamento-tooltip');
    const wrap = svg.parentElement;
    for (let i = 0; i < localN; i++) {
      const isMarked = i === 0 || i === localJul27 || i === localN - 1;
      const r = isMarked ? 4.5 : 2;
      svg.appendChild(el('circle', { cx: x(i), cy: y(series[i]), r, fill: series[i] < 0 ? 'var(--critical)' : 'var(--accent)' }));
      if (i === 0 || i % 2 === 1) {
        const lbl = el('text', { x: x(i), y: H - MB + 14, 'text-anchor': 'middle', class: 'axis-label' });
        lbl.textContent = i === 0 ? 'Início' : monthShort(data.months[i - 1]).split('/')[0];
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
        tooltip.innerHTML = i === 0
          ? `
          <div class="t-month">Início (${monthShort(f.posicao_inicial_mes || data.months[0])})</div>
          <div class="t-row"><span>Posição inicial do fundo</span>${moneySpan(series[0])}</div>
          `
          : `
          <div class="t-month">${monthShort(data.months[i - 1])}</div>
          <div class="t-row"><span>Saldo do investimento</span>${moneySpan(series[i])}</div>
          <div class="t-row"><span>Saque no mês</span>${moneySpan(-f.saque_mensal[i - 1])}</div>
        `;
      });
      hit.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });
    }
    const jul27Lbl = el('text', { x: x(localJul27), y: y(series[localJul27]) + (series[localJul27] < 0 ? 16 : -10), 'text-anchor': 'middle', class: 'sv', fill: series[localJul27] < 0 ? 'var(--critical)' : 'var(--accent)', 'font-weight': 600, 'font-size': 11 });
    jul27Lbl.textContent = fmt0(series[localJul27]);
    svg.appendChild(jul27Lbl);
  })();

  // ---------- Obra ----------
  (function () {
    const o = data.obra;
    document.getElementById('obra-sub').innerHTML = wrapMoney(
      fmt0(o.previsto) + ' previstos · ' + fmt1pct(obraPctPago) + ' pago até o momento');

    const p = data.pagamentos;
    const tiles = document.getElementById('pagamentos-tiles');
    [
      ['Pago até agora (Pix + Cartão)', p.pago_total],
      ['Pix pendente a realizar', p.pix_pendente_total],
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
      <div style="width:${o.futuro / lancado * 100}%; background: var(--future)"></div>
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
        <td class="num">${fmt1pct(pct)}</td>
        <td class="num">${fmt0(r.pendente_pix)}</td>
        <td class="num">${fmt0(r.pendente_cartao)}</td>
        <td><div class="mini-bar">
          <div style="width:${r.pago / denom * 100}%; background: var(--good)"></div>
          <div style="width:${r.pendente / denom * 100}%; background: var(--warning)"></div>
          <div style="width:${r.futuro / denom * 100}%; background: var(--future)"></div>
        </div></td>
      `;
      tbody.appendChild(tr);
    });

    const totalDenom = (o.pago + o.pendente + o.futuro) || 1;
    const totalTr = document.createElement('tr');
    totalTr.className = 'row-total';
    totalTr.innerHTML = `
      <td>Total</td>
      <td class="num">${fmt0(o.previsto)}</td>
      <td class="num">${fmt0(o.pago)}</td>
      <td class="num">${fmt1pct(obraPctPago)}</td>
      <td class="num">${fmt0(p.pix_pendente_total)}</td>
      <td class="num">${fmt0(p.cartao_futuro)}</td>
      <td><div class="mini-bar">
        <div style="width:${o.pago / totalDenom * 100}%; background: var(--good)"></div>
        <div style="width:${o.pendente / totalDenom * 100}%; background: var(--warning)"></div>
        <div style="width:${o.futuro / totalDenom * 100}%; background: var(--future)"></div>
      </div></td>
    `;
    tbody.appendChild(totalTr);
  })();

  // ---------- Investimentos: posição atual, cotação ao vivo e highlights ----------
  (function () {
    const inv = data.investimentos;
    if (!inv) return;
    const t = inv.total;
    const ra = inv.rent_ativa;
    const fmtShare = (v) => 'R$ ' + abs(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    document.getElementById('invest-sub').textContent = 'Posição atual — aba Investimentos';

    const tiles = document.getElementById('invest-tiles');
    [
      ['Total Investido', fmt0(t.valor_atual)],
      ['Rentabilidade (posições ativas)', ra.rent_pct !== null ? moneySpan(ra.rent_rs) : '—'],
      ['Rentabilidade (posições ativas) %', ra.rent_pct !== null ? fmt1pct(ra.rent_pct) : '—'],
    ].forEach(([label, value]) => {
      const el = document.createElement('div');
      el.className = 'stat-tile';
      el.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
      tiles.appendChild(el);
    });

    function rentCell(item) {
      if (item.liquidado) return '<span class="invest-tag">Liquidado</span>';
      if (item.started_zero) return '<span class="invest-tag">Novo em 2026</span>';
      return `${moneySpan(item.rent_acum_rs)} <span style="color:var(--ink-muted)">(${fmt1pct(item.rent_acum_pct)})</span>`;
    }

    function renderGroup(container, group, openByDefault) {
      const details = document.createElement('details');
      details.className = 'invest-group';
      if (openByDefault) details.open = true;
      const summary = document.createElement('summary');
      summary.innerHTML = wrapMoney(`<span class="name">${group.nome}</span><span class="meta">${fmt0(group.valor_atual)} · ${fmt1pct(group.pct_part)}</span>`);
      details.appendChild(summary);

      const wrap = document.createElement('div');
      wrap.className = 'wide-scroll';
      const table = document.createElement('table');
      table.className = 'detail-table';
      table.innerHTML = `<thead><tr><th>Ativo</th><th class="num">Qtd</th><th class="num">Aquisição</th><th class="num">Cotação</th><th class="num">Valor Atual</th><th class="num">Rentabilidade</th></tr></thead>`;
      const tbody = document.createElement('tbody');
      group.itens.forEach((it) => {
        const cotacao = it.ticker ? inv.cotacoes[it.ticker] : null;
        const tr = document.createElement('tr');
        tr.className = 'row-line';
        tr.innerHTML = `
          <td>${it.nome}${it.ticker ? ` <span style="color:var(--ink-muted)">(${it.ticker})</span>` : ''}</td>
          <td class="num">${it.qtd ? it.qtd : '—'}</td>
          <td class="num">${it.pm ? fmtShare(it.pm) : '—'}</td>
          <td class="num">${cotacao ? fmtShare(cotacao) : '—'}</td>
          <td class="num">${fmt0(it.valor_atual)}</td>
          <td class="num">${rentCell(it)}</td>
        `;
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      details.appendChild(wrap);
      container.appendChild(details);
    }

    const groupsEl = document.getElementById('invest-groups');
    inv.categorias.forEach((cat) => renderGroup(groupsEl, cat, false));

    const highlights = document.getElementById('invest-highlights');
    if (!inv.highlights || inv.highlights.length === 0) {
      highlights.innerHTML = '<div class="alert-empty">Sem observações hoje.</div>';
    } else {
      inv.highlights.forEach((h) => {
        const el = document.createElement('div');
        el.className = 'alert-item';
        el.innerHTML = wrapMoney(`<span class="icon">${h.icon || 'ℹ️'}</span><span>${h.text}</span>`);
        highlights.appendChild(el);
      });
    }
  })();

  // ---------- Gastos por Tipo: Fixo Mensal / Parcelado / Discricionário, com subtotais ----------
  (function () {
    const container = document.getElementById('natureza-groups');
    const grandTotal = data.gastos_por_natureza.reduce((s, g) => s + g.total, 0) || 1;
    document.getElementById('tipo-sub').textContent = 'Fatura atual do cartão';
    document.getElementById('tipo-total').textContent = fmt0(grandTotal);

    const summaryTiles = document.getElementById('tipo-summary-tiles');
    data.gastos_por_natureza.forEach((g) => {
      const el = document.createElement('div');
      el.className = 'stat-tile';
      el.innerHTML = `<div class="label">${g.natureza}</div><div class="value">${fmt0(g.total)}</div>`;
      summaryTiles.appendChild(el);
    });

    data.gastos_por_natureza.forEach((g, gi) => {
      const group = document.createElement('div');
      group.className = 'natureza-group';
      group.innerHTML = wrapMoney(`<div class="natureza-head"><span class="name">${g.natureza}</span><span class="val">${fmt0(g.total)} · ${g.pct.toFixed(1)}%</span></div>`);
      const list = document.createElement('div');
      list.className = 'bar-list';
      g.tipos.forEach((t, i) => {
        const color = `var(--cat-${((gi * 2 + i) % 5) + 1})`;
        const row = document.createElement('div');
        row.className = 'bar-list-row';
        const pctOfGroup = g.total ? (t.total / g.total * 100) : 0;
        row.innerHTML = wrapMoney(`
          <span class="name">${t.tipo}</span>
          <span class="bar-track"><span class="bar-fill" style="width:${pctOfGroup}%; background:${color}"></span></span>
          <span class="val">${fmt0(t.total)}</span>
        `);
        list.appendChild(row);
      });
      group.appendChild(list);
      container.appendChild(group);
    });
  })();

  // ---------- Composição de Despesas do Mês (a partir da DRE, linhas Fixo+Variável) ----------
  // Selecionável por mês — inclui a projeção de meses futuros (ex: jan./27), não só o
  // mês de referência.
  (function () {
    const select = document.getElementById('composicao-month');
    data.months.forEach((m, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = monthShort(m);
      select.appendChild(opt);
    });
    select.value = REF;

    function render(monthIdx) {
      const items = data.dre_detalhe
        .filter((r) => r.kind === 'LINE' && (r.grupo === 'FIXO' || r.grupo === 'VARIAVEL'))
        .map((r) => ({ label: r.label, valor: r.vals[monthIdx] }))
        .sort((a, b) => abs(b.valor) - abs(a.valor));
      const total = items.reduce((s, r) => s + r.valor, 0);
      document.getElementById('composicao-sub').textContent = 'Linhas de saída (Fixo + Variável)';
      document.getElementById('composicao-total').innerHTML = moneySpan(total);

      const list = document.getElementById('composicao-list');
      list.innerHTML = '';
      items.forEach((r) => {
        const row = document.createElement('div');
        row.className = 'plain-list-row';
        row.innerHTML = `<span class="name">${r.label}</span><span class="val">${moneySpan(r.valor)}</span>`;
        list.appendChild(row);
      });
    }

    select.addEventListener('change', () => render(Number(select.value)));
    render(REF);
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
      el.innerHTML = wrapMoney(`<span class="icon">${a.icon || '⚠️'}</span><span>${a.text}</span>`);
      list.appendChild(el);
    });
  })();

  // ---------- janela de pagamento (mês em foco) — agrupada por Pix / Cartão ----------
  (function () {
    const jp = data.janela_pagamento;
    if (!jp) return;
    document.getElementById('janela-title').textContent = 'Janela de Pagamento — ' + monthShort(jp.mes);
    const pixFonteTxt = jp.pix_fonte === 'manual' ? 'Pix com datas reais (planilha)' : 'Pix por cor de célula (sem data)';
    document.getElementById('janela-sub').textContent =
      `Itens com valor lançado em ${monthShort(jp.mes)} · ${pixFonteTxt} · Cartão por cor de célula · ${jp.itens.length} itens`;
    document.getElementById('janela-total').innerHTML = moneySpan(-jp.total);

    const statusClass = { PAGO: 'pago', PENDENTE: 'pendente', FUTURO: 'futuro' };
    const statusLabel = { PAGO: 'Pago', PENDENTE: 'Pendente', FUTURO: 'Futuro' };
    const tbody = document.getElementById('janela-table-body');

    // Resumo (tiles) sempre visível, igual à DRE Resumida — o detalhamento item a item
    // fica escondido atrás do <details>, só abre quando o usuário quer conferir.
    const pixSubtotal = jp.itens.filter((it) => it.modalidade.toLowerCase() === 'pix').reduce((s, it) => s + it.valor, 0);
    const cartaoSubtotal = jp.itens.filter((it) => it.modalidade.toLowerCase() === 'cartão').reduce((s, it) => s + it.valor, 0);
    const tiles = document.getElementById('janela-tiles');
    [
      ['Subtotal Pix', pixSubtotal],
      ['Subtotal Cartão', cartaoSubtotal],
      ['Total (Pix + Cartão)', jp.total],
    ].forEach(([label, val]) => {
      const el = document.createElement('div');
      el.className = 'stat-tile';
      el.innerHTML = `<div class="label">${label}</div><div class="value">${fmt0(-val)}</div>`;
      tiles.appendChild(el);
    });
    document.getElementById('janela-detail-summary').textContent = `Ver detalhamento (${jp.itens.length} itens)`;

    function addItemRow(it) {
      const tr = document.createElement('tr');
      tr.className = 'row-line';
      tr.innerHTML = `
        <td>${it.item}</td>
        <td>${it.classificacao}</td>
        <td>${it.modalidade}</td>
        <td class="num">${fmt0(-it.valor)}</td>
        <td>${it.data || '—'}</td>
        <td><span class="status-badge ${statusClass[it.status] || 'futuro'}">${statusLabel[it.status] || it.status}</span></td>
      `;
      tbody.appendChild(tr);
    }
    function addSubtotalRow(label, total) {
      const tr = document.createElement('tr');
      tr.className = 'row-subtotal';
      tr.innerHTML = `<td colspan="3">${label}</td><td class="num">${fmt0(-total)}</td><td colspan="2"></td>`;
      tbody.appendChild(tr);
    }

    const pix = jp.itens.filter((it) => it.modalidade.toLowerCase() === 'pix');
    const cartao = jp.itens.filter((it) => it.modalidade.toLowerCase() === 'cartão');
    const outros = jp.itens.filter((it) => !['pix', 'cartão'].includes(it.modalidade.toLowerCase()));

    if (pix.length) {
      pix.forEach(addItemRow);
      addSubtotalRow('Subtotal Pix', pix.reduce((s, it) => s + it.valor, 0));
    }
    if (cartao.length) {
      cartao.forEach(addItemRow);
      addSubtotalRow('Subtotal Cartão', cartao.reduce((s, it) => s + it.valor, 0));
    }
    outros.forEach(addItemRow);

    if (jp.itens.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="foot">Nenhum item lançado neste mês.</td></tr>';
    } else {
      const totalTr = document.createElement('tr');
      totalTr.className = 'row-total';
      totalTr.innerHTML = `<td colspan="3">Total (Pix + Cartão)</td><td class="num">${fmt0(-jp.total)}</td><td colspan="2"></td>`;
      tbody.appendChild(totalTr);
    }
  })();

  // ---------- footnotes ----------
  document.getElementById('footnotes').innerHTML = wrapMoney(`
    <div><b>Mês em foco</b> (indicadores, DRE Resumida, janela de pagamento, distribuição de parcelas de cartão): ${monthShort(data.months[REF])} — o próximo mês a acontecer. O saldo real conhecido é ancorado em ${monthShort(data.months[data.anchor_month_index])}, que já foi realizado.</div>
    <div><b>Janela de pagamento</b> lista os itens da Obra (Fluxo_Apto_Realizado) com valor lançado no mês em foco. Pix usa a tabela "Janela de Pagamentos" com datas reais quando ela existe pro mês (senão cai para o mês inteiro, por cor de célula); Cartão sempre por cor de célula — só dá o mês, a parcela específica não tem dia marcado.</div>
    <div><b>Apto Saúde</b> devolvido em ago./26 — a partir de set./26 restou só o Cartão Crédito Casa, projetado mês a mês pelas parcelas pendentes em Despesas_Casa (aba própria); as demais linhas (aluguel/condomínio/Enel/internet) zeram. Informativo, paga a Gabi, não entra nas saídas.</div>
    <div><b>Cartão Obra</b> usa o valor mensal já projetado em Fluxo_Apto_Realizado (linha 55 — Cartão); a Margem Líquida da DRE Resumida separa esse custo (Custo Obra) por ter prazo pra terminar — a versão que inclui a obra continua na tabela de detalhamento.</div>
    <div><b>Financiamento da obra</b>: o salário líquido (livre de custos fixos, que a Gabriela assume 100%) paga primeiro o cartão da obra; o fundo (${fmt0(data.financiamento_obra.investimento_bloqueado_total)} hoje) cobre só o Pix inteiro mais a parte do cartão que sobrar do salário — a partir do mês seguinte ao de referência. Quando o fundo esgota, o restante passa a sair do caixa corrente — projeção até ${monthShort(data.months[N - 1])}. O ponto "Início" no gráfico é a posição bruta do fundo antes da obra consumi-lo (${fmt0(data.financiamento_obra.posicao_inicial)} em ${monthShort(data.financiamento_obra.posicao_inicial_mes)}) — a linha tracejada até o primeiro mês é uma ponte ilustrativa (sem dado mensal real no meio), não projeção.</div>
    <div><b>Cartão pessoal</b> detalhado a partir de ${data.n_itens_cartao_pessoal} itens de Contas!Cartão Pessoal; ${data.n_itens_obra_cartao} itens marcados "Obra Apto" aparecem em Gastos por Tipo mas o valor mensal de obra usado na DRE vem de Fluxo_Apto_Realizado, não deste cadastro.</div>
    <div>Fonte: planilha Google Sheets FL_2024 — abas DRE_Mensal, Obra_Consolidado, Fluxo_Caixa, Gastos_Por_Tipo e Despesas_Casa. Regenerar com <code>daily_update.py</code>.</div>
  `);
})();
