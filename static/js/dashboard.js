/* SVG charts intentionally use fixed synthetic values, not live business data. */
(function (A) {
  'use strict';
  function chartMarkup(period) {
    const values = period === '7' ? [34, 52, 41, 68, 55, 84, 73] : [24, 33, 29, 46, 37, 51, 45, 63, 57, 79, 66, 91];
    const comparison = values.map((value, index) => Math.max(9, value - 14 + (index % 3) * 5));
    const x = index => 43 + index * (603 / (values.length - 1));
    const y = value => 145 - value * 1.26;
    const path = data => data.map((value, index) => (index ? 'L' : 'M') + x(index).toFixed(1) + ',' + y(value).toFixed(1)).join(' ');
    const labels = period === '7' ? ['24 Sep', '25 Sep', '26 Sep', '27 Sep', '28 Sep', '29 Sep', '30 Sep'] : ['01 Sep', '03 Sep', '06 Sep', '09 Sep', '12 Sep', '15 Sep', '18 Sep', '21 Sep', '24 Sep', '26 Sep', '28 Sep', '30 Sep'];
    return `<svg class="chart" viewBox="0 0 680 179" role="img" aria-label="Synthetic activity chart, September 2026. Current period values ${values.join(', ')}."><title>Illustrative activity, not live data</title>${[0,25,50,75,100].map(value => `<line class="chart-gridline" x1="42" x2="651" y1="${y(value)}" y2="${y(value)}"/><text x="29" y="${y(value)+3}" text-anchor="end">${value}</text>`).join('')}<path d="${path(values)} L646,145 L43,145 Z" fill="var(--primary-soft)"/><path d="${path(comparison)}" fill="none" stroke="var(--border-strong)" stroke-width="2" stroke-dasharray="4 4"/><path d="${path(values)}" fill="none" stroke="var(--primary)" stroke-width="2"/>${values.map((value,index) => `<circle cx="${x(index)}" cy="${y(value)}" r="2.8" fill="var(--bg-panel)" stroke="var(--primary)" stroke-width="1.5"><title>${labels[index]}: ${value} actions</title></circle>`).join('')}${labels.map((label,index) => index % (period === '7' ? 1 : 2) === 0 || index === labels.length-1 ? `<text x="${x(index)}" y="166" text-anchor="middle">${label}</text>` : '').join('')}</svg>`;
  }
  function timeLabel(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' }).format(date);
  }
  A.initDashboard = function () {
    const renderMetrics = () => {
      const users = A.data.users();
      const counts = { total: users.length, active: users.filter(user => user.status === 'active').length, pending: users.filter(user => user.status === 'pending').length, departments: new Set(users.map(user => user.department)).size };
      A.$$('[data-metric]').forEach(node => { node.textContent = counts[node.dataset.metric] ?? 0; });
      A.$$('[data-department-breakdown]').forEach(container => {
        container.innerHTML = A.data.departments.map(department => {
          const count = users.filter(user => user.department === department).length;
          const width = users.length ? count / users.length * 100 : 0;
          return `<a class="department-row" href="${A.pageHref('users')}?department=${encodeURIComponent(department)}"><span class="dept-icon">${A.icon('building')}</span><div class="dept-info"><strong>${department}</strong><span class="progress progress-sm"><span class="progress-bar" style="--progress:${width}%"></span></span></div><span class="dept-count">${count}</span></a>`;
        }).join('');
      });
      A.$$('[data-department-count]').forEach(node => { node.textContent = users.filter(user => user.department === node.dataset.departmentCount).length; });
    };
    const renderLogs = () => {
      const query = A.$('[data-log-search]')?.value.toLowerCase() || '';
      A.$$('[data-audit-table]').forEach(container => {
        let logs = A.data.logs().filter(log => [log.user, log.action, log.entity, log.ip].join(' ').toLowerCase().includes(query));
        if (container.dataset.logLimit) logs = logs.slice(0, Number(container.dataset.logLimit));
        container.innerHTML = `<div class="table-container" tabindex="0" role="region" aria-label="Activity log"><table class="table table-compact"><thead><tr><th scope="col">Time</th><th scope="col">User</th><th scope="col">Action</th><th scope="col">Entity</th>${container.dataset.fullLog ? '<th scope="col">IP / source</th>' : ''}</tr></thead><tbody>${logs.length ? logs.map(log => `<tr><td><span class="font-mono">${A.escape(timeLabel(log.time))}</span>${container.dataset.fullLog ? '<small class="text-muted"> ' + A.escape(A.formatDate(log.time)) + '</small>' : ''}</td><td>${A.escape(log.user)}</td><td>${A.escape(log.action)}</td><td><code>${A.escape(log.entity)}</code></td>${container.dataset.fullLog ? '<td class="font-mono text-muted">' + A.escape(log.ip) + '</td>' : ''}</tr>`).join('') : '<tr><td colspan="5"><div class="empty-state">No matching activity.</div></td></tr>'}</tbody></table></div>`;
      });
    };
    A.$$('[data-demo-chart]').forEach(container => { container.innerHTML = chartMarkup('7'); });
    document.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-chart-period')) {
        const panel = button.closest('.chart-panel');
        A.$('[data-demo-chart]', panel).innerHTML = chartMarkup(button.dataset.chartPeriod);
        A.$$('[data-chart-period]', panel).forEach(item => item.setAttribute('aria-pressed', String(item === button)));
        const total = A.$('[data-chart-total]', panel); if (total) total.textContent = button.dataset.chartPeriod === '7' ? '407' : '661';
      }
      if (button.hasAttribute('data-report-export')) {
        const kind = button.dataset.reportExport;
        if (kind === 'users') {
          const users = A.data.users(); A.downloadCSV('employee-directory.csv', ['ID','Name','Email','Department','Status','Created'], users.map(row => [row.id,row.name,row.email,row.department,row.status,row.created]));
        } else if (kind === 'departments') {
          const users = A.data.users(); A.downloadCSV('departments.csv', ['Department','Employees','Active','Pending'], A.data.departments.map(department => { const rows = users.filter(row => row.department === department); return [department,rows.length,rows.filter(row => row.status === 'active').length,rows.filter(row => row.status === 'pending').length]; }));
        } else {
          A.downloadCSV('activity-log.csv', ['Time','User','Action','Entity','Source'], A.data.logs().map(row => [row.time,row.user,row.action,row.entity,row.ip]));
        }
        A.data.log('Exported report', kind);
      }
    });
    A.$('[data-log-search]')?.addEventListener('input', renderLogs);
    document.addEventListener('demo:users-changed', renderMetrics);
    document.addEventListener('demo:logs-changed', renderLogs);
    renderMetrics(); renderLogs();
  };
})(window.Admin);
