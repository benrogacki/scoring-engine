/* BRG Tax Engine - JS mirror of brg_tax/engine/taxmath.py (optimiser maths only).
 *
 * Integer pence and basis points throughout, rounding half-up to the penny exactly as the Python
 * engine does. Parameters arrive in the model built by extraction.build_model - nothing here
 * hard-codes a rate. tests/brg_tax/test_brg_parity.py runs this file under Node against the Python
 * engine over a grid of inputs; keep the two in step.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BRGMirror = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function muldiv(amount, num, den) {
    const n = amount * num;
    const sign = n < 0 ? -1 : 1;
    return sign * Math.floor((2 * Math.abs(n) + den) / (2 * den));
  }
  function atRate(amount, rateBp) { return muldiv(amount, rateBp, 10000); }

  // ------------------------------------------------------------------ income tax
  function banded(amount, bands, start) {
    let tax = 0, pos = start || 0, left = Math.max(0, amount);
    const rows = [];
    for (const b of bands) {
      const top = b.upto;
      if (top !== null && pos >= top) continue;
      const room = top === null ? left : Math.min(left, top - pos);
      if (room <= 0) break;
      const t = atRate(room, b.rate_bp);
      rows.push({ band: b.name || "", amount: room, rate_bp: b.rate_bp, tax: t });
      tax += t; pos += room; left -= room;
      if (left <= 0) break;
    }
    return { tax, rows };
  }

  function personalAllowance(totalIncome, ty) {
    let pa = ty.pa;
    const excess = totalIncome - ty.taper;
    if (excess > 0) pa = Math.max(0, pa - Math.floor(excess / 200) * 100);
    return pa;
  }

  function incomeTax(nonsav, div, nsBands, ty) {
    nonsav = Math.max(0, nonsav); div = Math.max(0, div);
    const pa = personalAllowance(nonsav + div, ty);
    const paNs = Math.min(pa, nonsav);
    const paDiv = Math.min(pa - paNs, div);
    const tns = nonsav - paNs, tdiv = div - paDiv;
    const ns = banded(tns, nsBands, 0);
    const nil = Math.min(ty.div_allowance, tdiv);
    let pos = tns + nil, left = tdiv - nil, dtax = 0;
    const drows = [];
    for (let i = 0; i < ty.uk_bands.length; i++) {
      const b = ty.uk_bands[i], top = b.upto;
      if (left <= 0) break;
      if (top !== null && pos >= top) continue;
      const room = top === null ? left : Math.min(left, top - pos);
      const rate = ty.div_bp[Math.min(i, ty.div_bp.length - 1)];
      const t = atRate(room, rate);
      drows.push({ band: b.name || "", amount: room, rate_bp: rate, tax: t });
      dtax += t; pos += room; left -= room;
    }
    return { pa, taxable_nonsav: tns, taxable_div: tdiv, div_nil: nil, tax_nonsav: ns.tax, tax_div: dtax,
             total: ns.tax + dtax, rows_nonsav: ns.rows, rows_div: drows };
  }

  // ------------------------------------------------------------------ NIC
  function class1(salary, ty) {
    const s = Math.max(0, salary);
    const ee = atRate(Math.max(0, Math.min(s, ty.uel) - ty.pt), ty.ee_main_bp) + atRate(Math.max(0, s - ty.uel), ty.ee_add_bp);
    const er = atRate(Math.max(0, s - ty.st), ty.er_bp);
    return { ee, er };
  }
  function class4(profit, ty) {
    const p = Math.max(0, profit);
    return atRate(Math.max(0, Math.min(p, ty.c4_upper) - ty.c4_lower), ty.c4_main_bp) + atRate(Math.max(0, p - ty.c4_upper), ty.c4_add_bp);
  }
  function class2(profit, ty) { return ty.c2_compulsory && profit >= ty.c4_lower ? ty.c2_weekly * 52 : 0; }

  // ------------------------------------------------------------------ corporation tax
  function split(total, parts) {
    const whole = parts.reduce((a, b) => a + b, 0);
    const out = []; let used = 0;
    parts.forEach((d, i) => {
      if (i === parts.length - 1) out.push(total - used);
      else { const v = muldiv(total, d, whole); out.push(v); used += v; }
    });
    return out;
  }

  function ctOnProfit(n, a, sched) {
    const slices = sched.slices;
    if (n <= 0) return { ct: 0, slices: slices.map(s => ({ fy: s.fy, days: s.days, n: 0, a: 0, rate: "nil", tax: 0, mr: 0, ct: 0 })) };
    const days = slices.map(s => s.days);
    const ns = split(n, days), as = split(Math.max(a, n), days);
    let total = 0; const rows = [];
    slices.forEach((s, i) => {
      const ni = ns[i], ai = as[i];
      let tax, mr, rate;
      if (ai <= s.lower) { tax = atRate(ni, s.small_bp); mr = 0; rate = "small"; }
      else if (ai >= s.upper) { tax = atRate(ni, s.main_bp); mr = 0; rate = "main"; }
      else { tax = atRate(ni, s.main_bp); mr = muldiv((s.upper - ai) * ni, s.mr_num, s.mr_den * ai); rate = "marginal"; }
      rows.push({ fy: s.fy, days: s.days, n: ni, a: ai, upper: s.upper, lower: s.lower, rate, tax, mr, ct: tax - mr });
      total += tax - mr;
    });
    return { ct: total, slices: rows };
  }

  // ------------------------------------------------------------------ extraction scenario
  function shares(total, people) {
    const holders = people.filter(p => p.share_bp > 0 && !p.waived);
    const out = {};
    people.forEach(p => { out[p.id] = 0; });
    if (!holders.length || total <= 0) return out;
    const vals = split(total, holders.map(p => p.share_bp));
    holders.forEach((p, i) => { out[p.id] = vals[i]; });
    return out;
  }

  function scenario(model, sc) {
    const ty = model.ty, people = model.people;
    const sal = {}, pen = {}, nic = {};
    people.forEach(p => {
      sal[p.id] = p.director ? (sc.salaries[p.id] || 0) : 0;
      pen[p.id] = p.director ? (sc.pensions[p.id] || 0) : 0;
      nic[p.id] = class1(sal[p.id], ty);
    });
    const sum = o => Object.values(o).reduce((a, b) => a + b, 0);
    const erDir = people.reduce((a, p) => a + nic[p.id].er, 0);
    const aboveSt = people.filter(p => p.director && sal[p.id] > ty.st).length;
    const eaEligible = model.other_employees_above_st > 0 || aboveSt >= 2;
    const erGross = erDir + model.other_employer_nic;
    const eaUsed = eaEligible ? Math.min(ty.ea, erGross) : 0;
    const n = model.profit_before_directors - sum(sal) - sum(pen) - erDir + eaUsed;
    const ct = ctOnProfit(n, n + model.exempt_distributions, model.ct_schedule);
    const pat = n - ct.ct;
    const reserves = model.opening_reserves + pat;
    const dTotal = Math.max(0, sc.dividend_total);
    const divs = shares(dTotal, people);
    let s455 = 0, totalIt = 0, totalEe = 0, value = 0;
    const rows = [];
    people.forEach(p => {
      const id = p.id;
      const itAll = incomeTax(p.other_income + sal[id], divs[id], p.ns_bands, ty);
      const itBase = incomeTax(p.other_income, 0, p.ns_bands, ty);
      const extra = itAll.total - itBase.total;
      const dla = model.dla_overdrawn[id] || 0;
      const cleared = sc.clear_dla ? Math.min(dla, divs[id]) : 0;
      s455 += atRate(Math.max(0, dla - cleared), ty.s455_bp);
      const net = sal[id] + divs[id] - nic[id].ee - extra;
      rows.push({ id, name: p.name, salary: sal[id], pension: pen[id], dividend: divs[id], ee_nic: nic[id].ee, er_nic: nic[id].er,
                  income_tax: extra, tax_on_salary: itAll.tax_nonsav - itBase.tax_nonsav, tax_on_dividends: itAll.tax_div, pa: itAll.pa,
                  net_cash: net, value: net + pen[id], dla_cleared: cleared, qualifying_year: sal[id] >= ty.lel, aa_exceeded: pen[id] > ty.aa });
      totalIt += extra; totalEe += nic[id].ee; value += net + pen[id];
    });
    const erNet = erGross - eaUsed;
    const totalTax = ct.ct + totalIt + totalEe + erNet;
    return { taxable_profit: n, ct: ct.ct, ct_slices: ct.slices, profit_after_tax: pat, reserves, dividend_total: dTotal,
             hard_stop: dTotal > reserves, ea_eligible: eaEligible, ea_used: eaUsed, er_nic_directors: erDir, er_nic_net: erNet,
             ee_nic: totalEe, income_tax: totalIt, total_tax: totalTax, value, retained: reserves - dTotal, s455, people: rows };
  }

  function salaryGrid(ty) {
    const pts = new Set([0, ty.lel, ty.st, ty.pt, ty.uel]);
    for (let k = 0; k <= 100; k++) pts.add(k * 100000);
    return Array.from(pts).sort((a, b) => a - b);
  }
  function dividendFor(model, pat, reserves) {
    return Math.max(0, Math.min(reserves, muldiv(Math.max(0, pat), 100 - model.retain_pct, 100)));
  }
  function optimise(model) {
    let best = null;
    const directors = model.people.filter(p => p.director);
    for (const s of salaryGrid(model.ty)) {
      const salaries = {};
      directors.forEach(p => { salaries[p.id] = s; });
      const sc = { salaries, pensions: Object.assign({}, model.default.pensions), dividend_total: 0, clear_dla: model.default.clear_dla };
      const probe = scenario(model, sc);
      sc.dividend_total = dividendFor(model, probe.profit_after_tax, probe.reserves);
      const r = scenario(model, sc);
      if (best === null || r.value > best.result.value) best = { salary: s, scenario: sc, result: r };
    }
    return best;
  }

  // ------------------------------------------------------------------ sole trader vs company
  function soleTraderTax(profit, cm) {
    const ty = cm.ty;
    const itAll = incomeTax(cm.other_income + profit, 0, cm.ns_bands, ty);
    const itBase = incomeTax(cm.other_income, 0, cm.ns_bands, ty);
    const c4 = class4(profit, ty), c2 = class2(profit, ty);
    const it = itAll.total - itBase.total;
    const total = it + c4 + c2;
    return { income_tax: it, class4: c4, class2: c2, total, net: profit - total };
  }
  function companyModel(profit, cm) {
    return { ty: cm.ty, profit_before_directors: profit - cm.admin_cost, exempt_distributions: 0, ct_schedule: cm.ct_schedule,
             opening_reserves: 0, other_employees_above_st: 0, other_employer_nic: 0, retain_pct: 0, dla_overdrawn: {},
             people: [{ id: "owner", name: "Owner", share_bp: 10000, director: true, other_income: cm.other_income, ns_bands: cm.ns_bands, waived: false }],
             default: { pensions: { owner: 0 }, clear_dla: false } };
  }
  function compareStructures(profit, cm) {
    const st = soleTraderTax(profit, cm);
    const best = optimise(companyModel(profit, cm));
    const r = best.result;
    return { profit, sole_trader: st,
             company: { salary: best.salary, dividend: r.dividend_total, ct: r.ct, income_tax: r.income_tax, ee_nic: r.ee_nic,
                        er_nic: r.er_nic_net, admin_cost: cm.admin_cost, total: r.total_tax + cm.admin_cost, net: r.value },
             difference: r.value - st.net };
  }

  // ------------------------------------------------------------------ VAT schemes
  function vatCompare(v) {
    const standard = v.output_vat - v.input_vat;
    const turnover = v.sales_net + v.output_vat;
    const lct = v.relevant_goods < muldiv(turnover, v.lct_pct_bp, 10000) || v.relevant_goods < v.lct_min;
    let rate = lct ? v.lct_rate_bp : v.sector_bp;
    if (v.first_year) rate -= v.first_year_discount_bp;
    const frs = atRate(turnover, rate);
    return { standard, flat_rate: frs, flat_rate_bp: rate, limited_cost_trader: lct, vat_inclusive_turnover: turnover, saving: standard - frs };
  }

  return { muldiv, atRate, banded, personalAllowance, incomeTax, class1, class4, class2, split, ctOnProfit, shares, scenario,
           salaryGrid, dividendFor, optimise, soleTraderTax, companyModel, compareStructures, vatCompare };
});
