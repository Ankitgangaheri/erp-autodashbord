/**
 * AutoERP — Main JavaScript
 * Handles flash dismiss, sidebar toggle, line items, autocomplete, charts.
 */

// ── Flash dismiss ──
document.querySelectorAll('.alert-close').forEach(btn => {
  btn.addEventListener('click', () => btn.closest('.alert').remove());
});
document.querySelectorAll('.alert-success').forEach(el => {
  setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity .4s'; setTimeout(()=>el.remove(),400); }, 4000);
});

// ── Mobile sidebar ──
const menuBtn  = document.querySelector('.mobile-menu-btn');
const sidebar  = document.querySelector('.sidebar');
const overlay  = document.querySelector('.sidebar-overlay');
if (menuBtn && sidebar && overlay) {
  menuBtn.addEventListener('click', () => { sidebar.classList.toggle('open'); overlay.classList.toggle('open'); });
  overlay.addEventListener('click', () => { sidebar.classList.remove('open'); overlay.classList.remove('open'); });
}

// ── Active nav link ──
const currentPath = window.location.pathname;
document.querySelectorAll('.nav-item').forEach(item => {
  const href = item.getAttribute('href');
  if (!href) return;
  if (href === '/' && currentPath === '/') { item.classList.add('active'); return; }
  if (href !== '/' && currentPath.startsWith(href)) item.classList.add('active');
});

// ── data-confirm dialogs ──
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', e => { if (!confirm(el.dataset.confirm)) e.preventDefault(); });
});

// ── data-post-url (POST via hidden form) ──
document.querySelectorAll('[data-post-url]').forEach(btn => {
  btn.addEventListener('click', e => {
    e.preventDefault();
    if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
    const f = document.createElement('form');
    f.method = 'POST'; f.action = btn.dataset.postUrl;
    document.body.appendChild(f); f.submit();
  });
});

// ── Dynamic Line Items ──
function initLineItems(tableId, addBtnId, searchUrl, priceField) {
  const table  = document.getElementById(tableId);
  const addBtn = document.getElementById(addBtnId);
  if (!table || !addBtn) return;

  function createRow() {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="width:38%">
        <div class="autocomplete-wrap">
          <input type="hidden" name="product_id[]" class="pid-input">
          <input type="text"   class="form-control prod-search" placeholder="Type to search product…" autocomplete="off">
          <div class="autocomplete-dropdown"></div>
        </div>
      </td>
      <td style="width:9%"><input type="text" class="form-control sku-display" readonly placeholder="SKU" tabindex="-1"></td>
      <td style="width:12%"><input type="number" name="quantity[]" class="form-control qty-inp" min="1" value="1" required></td>
      <td style="width:14%"><input type="number" name="unit_price[]" class="form-control price-inp" step="0.01" min="0" value="0" required></td>
      <td style="width:13%" class="row-total mono text-right">₹0.00</td>
      <td style="width:9%"><input type="text" class="form-control stock-display" readonly placeholder="Stock" tabindex="-1"></td>
      <td style="width:5%"><button type="button" class="line-item-remove" title="Remove">✕</button></td>
    `;
    wireRow(tr);
    return tr;
  }

  function wireRow(tr) {
    const pidInp    = tr.querySelector('.pid-input');
    const searchInp = tr.querySelector('.prod-search');
    const skuDisp   = tr.querySelector('.sku-display');
    const qtyInp    = tr.querySelector('.qty-inp');
    const priceInp  = tr.querySelector('.price-inp');
    const stockDisp = tr.querySelector('.stock-display');
    const dropdown  = tr.querySelector('.autocomplete-dropdown');
    const totalCell = tr.querySelector('.row-total');
    const removeBtn = tr.querySelector('.line-item-remove');

    let debounce;
    searchInp.addEventListener('input', () => {
      clearTimeout(debounce);
      const q = searchInp.value.trim();
      if (q.length < 2) { dropdown.classList.remove('open'); return; }
      debounce = setTimeout(async () => {
        const res   = await fetch(`${searchUrl}?q=${encodeURIComponent(q)}`).catch(()=>null);
        if (!res) return;
        const items = await res.json();
        dropdown.innerHTML = '';
        if (!items.length) {
          dropdown.innerHTML = '<div class="autocomplete-item text-muted">No results</div>';
        } else {
          items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'autocomplete-item';
            div.innerHTML = `<div>${item.name}</div>
              <div style="display:flex;gap:12px;margin-top:2px">
                <span class="autocomplete-item-sku">${item.sku}</span>
                <span class="autocomplete-item-stock">Stock: ${item.quantity} ${item.unit}</span>
              </div>`;
            div.addEventListener('click', () => {
              pidInp.value    = item.id;
              searchInp.value = item.name;
              skuDisp.value   = item.sku;
              priceInp.value  = item[priceField] || 0;
              stockDisp.value = `${item.quantity} ${item.unit}`;
              dropdown.classList.remove('open');
              calcRow();
            });
            dropdown.appendChild(div);
          });
        }
        dropdown.classList.add('open');
      }, 280);
    });

    document.addEventListener('click', e => { if (!tr.contains(e.target)) dropdown.classList.remove('open'); });

    function calcRow() {
      const t = (parseFloat(qtyInp.value)||0) * (parseFloat(priceInp.value)||0);
      totalCell.textContent = '₹' + t.toLocaleString('en-IN', {minimumFractionDigits:2});
      calcGrand();
    }
    qtyInp.addEventListener('input', calcRow);
    priceInp.addEventListener('input', calcRow);
    removeBtn.addEventListener('click', () => { tr.remove(); calcGrand(); });
  }

  function calcGrand() {
    let sub = 0;
    table.querySelectorAll('.row-total').forEach(c => {
      sub += parseFloat(c.textContent.replace(/[^0-9.]/g,'')) || 0;
    });
    const subEl   = document.getElementById('subtotal-display');
    const grandEl = document.getElementById('grand-total');
    if (subEl) subEl.textContent = '₹' + sub.toLocaleString('en-IN',{minimumFractionDigits:2});
    if (grandEl) {
      const disc = parseFloat(document.getElementById('discount-input')?.value||0);
      const taxP = parseFloat(document.getElementById('tax-input')?.value||0);
      const fin  = sub - disc + sub*(taxP/100);
      grandEl.textContent = '₹' + fin.toLocaleString('en-IN',{minimumFractionDigits:2});
    }
  }

  addBtn.addEventListener('click', () => table.querySelector('tbody').appendChild(createRow()));
  ['discount-input','tax-input'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', calcGrand);
  });

  // Start with one empty row
  if (!table.querySelector('tbody tr')) {
    table.querySelector('tbody').appendChild(createRow());
  }
}

// ── Simple bar chart ──
function renderBarChart(containerId, data) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const max = Math.max(...data.map(d=>d.amount), 1);
  el.innerHTML = data.map(d => {
    const h = Math.max(4, (d.amount/max)*100);
    return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px">
      <div style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">${d.amount>0?'₹'+(d.amount/1000).toFixed(1)+'k':''}</div>
      <div style="flex:1;width:100%;display:flex;align-items:flex-end">
        <div style="width:100%;height:${h}%;background:var(--accent);border-radius:3px 3px 0 0;opacity:.75;min-height:4px;transition:opacity .15s" title="${d.date}: ₹${d.amount}" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=.75"></div>
      </div>
      <div style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">${d.date.split(' ')[1]||d.date}</div>
    </div>`;
  }).join('');
}

// ── Form validation highlight ──
document.querySelectorAll('form[data-validate]').forEach(form => {
  form.addEventListener('submit', e => {
    let ok = true;
    form.querySelectorAll('[required]').forEach(f => {
      if (!f.value.trim()) { f.style.borderColor='var(--red)'; ok=false; }
      else f.style.borderColor='';
    });
    if (!ok) { e.preventDefault(); form.querySelector('[required]:invalid,[required][style*="red"]')?.focus(); }
  });
});

// ── Export CSV shortcut ──
document.querySelectorAll('[data-export-csv]').forEach(btn => {
  btn.addEventListener('click', () => {
    const url = new URL(window.location); url.searchParams.set('export','csv'); window.location=url;
  });
});

window.AutoERP = { initLineItems, renderBarChart };
