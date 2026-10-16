// Exercise the page's own script with isolated storage; never changes user reviews.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 2);
const data = JSON.parse(scripts[0][1]);
assert.equal(data.rows.length, 62);
assert.equal(data.rows.filter(r => r.priority).length, 12);

function session(initial = '{}', failStorage = false) {
  const elements = new Map(), downloads = [], storage = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { value: '', textContent: '', src: '', href: '' });
    return elements.get(id);
  };
  element('dataset').textContent = scripts[0][1];
  element('scope').value = 'priority';
  const context = vm.createContext({
    document: { getElementById: element, createElement: () => ({ click() {} }) },
    localStorage: {
      getItem: key => { if (failStorage) throw Error('unavailable'); return storage.get(key) ?? initial; },
      setItem: (key, value) => { if (failStorage) throw Error('unavailable'); storage.set(key, value); }
    },
    Blob,
    URL: { createObjectURL: blob => { downloads.push(blob); return 'blob:test'; }, revokeObjectURL() {} },
    setTimeout: callback => callback()
  });
  vm.runInContext(scripts[1][1], context);
  return { element, context, downloads, storage, records: () => JSON.parse(vm.runInContext('JSON.stringify(records())', context)) };
}

(async () => {
  const s = session();
  assert.equal(s.element('position').textContent, '1 / 12');
  assert.equal(s.records().filter(r => r.final_angle_deg !== null).length, 0);
  assert(s.element('original').src.startsWith('data:image/jpeg;base64,'));
  assert(s.element('zoom').src.startsWith('data:image/jpeg;base64,'));
  s.element('correct').onclick();
  assert.equal(s.records().filter(r => r.review_status !== 'pending').length, 0);
  s.element('correction').value = '0';
  s.element('correct').onclick();
  assert.equal(s.records().find(r => r.review_status === 'corrected').final_angle_deg, 0);
  const saved = [...s.storage.values()][0];
  assert.equal(session(saved).records().find(r => r.review_status === 'corrected').final_angle_deg, 0);
  s.element('unreadable').onclick();
  assert.equal(s.records().find(r => r.review_status === 'unreadable').final_angle_deg, null);
  s.element('confirm').onclick();
  const confirmed = s.records().find(r => r.review_status === 'confirmed');
  assert.equal(confirmed.final_angle_deg, confirmed.human_angle_deg);
  s.element('pending').onclick();
  assert(s.records().every(r => r.final_angle_deg === null));
  s.element('correction').value = '91';
  s.element('correct').onclick();
  assert(s.records().every(r => r.review_status === 'pending'));
  s.element('correction').value = '-8.65';
  s.element('correct').onclick();
  assert.equal(s.records().find(r => r.review_status === 'corrected').final_angle_deg, -8.65);
  s.element('scope').value = 'all'; s.element('scope').onchange();
  assert.equal(s.element('position').textContent, '1 / 62');
  s.element('prev').onclick();
  assert.equal(s.element('position').textContent, '62 / 62');
  s.element('next').onclick();
  assert.equal(s.element('position').textContent, '1 / 62');
  s.element('json').onclick();
  const exported = JSON.parse(await s.downloads[0].text());
  assert.equal(exported.rows.length, 62);
  assert.equal(exported.secondary_training_enabled, false);
  assert(exported.rows.every(r => r.include_in_secondary_training === false));
  assert.equal(exported.rows.find(r => r.review_status === 'corrected').final_angle_deg, -8.65);
  assert(exported.rows.filter(r => r.review_status === 'pending').every(r => r.final_angle_deg === null));
  s.element('csv').onclick();
  const csv = await s.downloads[1].text();
  assert.equal(csv.split('\r\n').length, 63);
  assert(csv.includes('最终复核角度'));
  const isolated = session('{}', true);
  isolated.element('confirm').onclick(); isolated.element('json').onclick();
  assert(isolated.element('message').textContent.includes('导出'));
  assert.equal(JSON.parse(await isolated.downloads[0].text()).rows.filter(r => r.review_status === 'confirmed').length, 1);
  const bad = session(JSON.stringify({ [data.rows[0].id]: { status: 'corrected', final_angle_deg: null } }));
  assert(bad.records().every(r => r.review_status === 'pending'));
  const corrupt = session('{broken');
  assert(corrupt.records().every(r => r.final_angle_deg === null));
  console.log(JSON.stringify({ passed: true, rows: 62, priority: 12,
    checks: ['pending_null', 'confirm_existing_label', 'zero_preserved', 'unreadable_null',
      'undo', 'empty_and_invalid_input', 'decimal_precision', 'navigation', 'storage_reload',
      'storage_failure_export', 'corrupt_storage', 'json_export', 'csv_export', 'training_disabled'],
    browser_visual_check: 'not_run_local_file_URL_blocked' }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
