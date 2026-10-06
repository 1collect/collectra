(() => {
  const kind = document.getElementById('id_kind');
  const mode = document.getElementById('id_contract_mode');
  const dbz = document.getElementById('id_dbz');
  const count = document.getElementById('id_count');
  function update() {
    const contracts = kind.value === 'contracts';
    document.querySelector('[data-contract-mode]').hidden = !contracts;
    document.querySelector('[data-dbz-label]').textContent = contracts ? 'Префикс ДБЗ' : 'ДБЗ';
    document.querySelector('[data-dbz-help]').textContent = contracts
      ? 'Необязательно. Номера договоров будут сформированы автоматически.'
      : 'ДБЗ должен существовать в системе.';
    dbz.required = !contracts;
    count.min = contracts && mode.value === 'errors' ? count.dataset.minimumErrorRows : '1';
    if (Number(count.value) < Number(count.min)) count.value = count.min;
    document.querySelector('[data-count-help]').textContent = contracts
      ? (mode.value === 'errors' ? `Для всех сценариев ошибок нужно не меньше ${count.min} строк.`
        : 'Каждая строка — новый договор с уникальным ДБЗ и ИИН.')
      : 'Все строки будут созданы для указанного ДБЗ.';
  }
  kind.addEventListener('change', update);
  mode.addEventListener('change', update);
  update();
})();
