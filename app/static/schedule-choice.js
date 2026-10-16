/* Progressive, accessible schedule choice UI; server validates everything. */
(() => {
  'use strict';
  const initial = document.querySelectorAll('[data-schedule-choice]');
  for (const field of initial) {
    const select = field.querySelector('select[name="schedule_choice"]');
    const custom = field.querySelector('[data-schedule-custom]');
    if (!select) continue;
    const refresh = () => {
      if (!custom) return;
      const selected = select.value === 'custom';
      custom.hidden = !selected;
      custom.querySelectorAll('input').forEach(input => { input.disabled = !selected; });
    };
    select.addEventListener('change', refresh);
    refresh();
  }
  // Library pages choose the target Pi at send time; the template itself
  // carries no scheduling metadata, and this is only a convenient preview.
  const data = document.querySelector('[data-library-schedule-map]');
  if (!data) return;
  let mapping;
  try { mapping = JSON.parse(data.dataset.libraryScheduleMap || '{}'); }
  catch (_) { return; }
  for (const group of document.querySelectorAll('[data-library-device-schedule]')) {
    const form = group.closest('form');
    const target = form?.querySelector('select[name="device"]');
    const select = group.querySelector('select[name="schedule_choice"]');
    const description = group.querySelector('[data-device-default-label]');
    if (!target || !select) continue;
    const render = () => {
      const chosen = select.value;
      const device = mapping[target.value] || {profiles:[],default:null};
      while (select.options.length > 2) select.remove(2);
      for (const rule of device.profiles || []) {
        const option = document.createElement('option');
        option.value = rule.id;
        option.textContent = rule.name + ' · ' + rule.start + '–' + rule.end + ' Uhr';
        select.appendChild(option);
      }
      if (chosen && [...select.options].some(option => option.value === chosen)) {
        select.value = chosen;
      } else {
        select.value = 'default';
      }
      const defaultRule = (device.profiles || []).find(x => x.id === device.default);
      description.textContent = 'Standard auf diesem Pi: ' +
        (defaultRule ? defaultRule.name + ' (' + defaultRule.start + '–' + defaultRule.end + ')' : 'ohne Zeitplan');
    };
    target.addEventListener('change', render);
    render();
  }
})();
