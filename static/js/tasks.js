(function (A) {
  'use strict';
  A.initTasks = function () {
    const containers = A.$$('[data-task-list]');
    let filter = 'all', query = '';
    const render = () => {
      const tasks = A.data.tasks();
      containers.forEach(container => {
        let rows = tasks.filter(task => (filter === 'all' || (filter === 'completed' ? task.done : !task.done)) && task.title.toLowerCase().includes(query));
        if (container.dataset.taskLimit) rows = rows.slice(0, Number(container.dataset.taskLimit));
        container.innerHTML = rows.length ? rows.map(task => `<div class="task-item ${task.done ? 'is-complete' : ''}"><label class="check"><input type="checkbox" data-task-check="${task.id}" ${task.done ? 'checked' : ''} aria-label="Complete ${A.escape(task.title)}"></label><div class="flex-1 min-w-0"><div class="task-title">${A.escape(task.title)}</div><div class="task-meta"><span>${A.escape(task.assignee)}</span><span>&middot;</span><span>${A.escape(A.formatDate(task.due))}</span></div></div><span class="badge badge-${task.priority === 'high' ? 'danger' : task.priority === 'medium' ? 'warning' : 'neutral'}">${A.escape(task.priority)}</span>${container.dataset.taskDelete ? `<button class="btn btn-icon btn-sm btn-ghost" data-task-delete="${task.id}" aria-label="Delete task ${A.escape(task.title)}">${A.icon('trash')}</button>` : ''}</div>`).join('') : '<div class="empty-state">' + A.icon('check-square') + '<h3>No tasks in this view</h3><p>Add a task or choose another filter.</p></div>';
      });
      A.$$('[data-task-pending]').forEach(node => { node.textContent = tasks.filter(task => !task.done).length; });
      A.$$('[data-task-total]').forEach(node => { node.textContent = tasks.length; });
    };
    document.addEventListener('change', event => {
      if (!event.target.matches('[data-task-check]')) return;
      const id = Number(event.target.dataset.taskCheck);
      const done = event.target.checked;
      A.data.saveTasks(A.data.tasks().map(task => task.id === id ? { ...task, done } : task));
      A.data.log(done ? 'Completed task' : 'Reopened task', 'TSK-' + id);
    });
    document.addEventListener('click', async event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-task-filter')) {
        filter = button.dataset.taskFilter;
        A.$$('[data-task-filter]').forEach(item => item.setAttribute('aria-pressed', String(item === button))); render();
      }
      if (button.hasAttribute('data-task-delete')) {
        const id = Number(button.dataset.taskDelete);
        if (await A.confirm({ title: 'Delete task?', message: 'Remove this task from local demonstration data?', label: 'Delete task', danger: true })) {
          A.data.saveTasks(A.data.tasks().filter(task => task.id !== id)); A.data.log('Deleted task', 'TSK-' + id);
          A.toast('success', 'Task removed', 'The local task list was updated.');
        }
      }
    });
    A.$('[data-task-search]')?.addEventListener('input', event => { query = event.target.value.toLowerCase(); render(); });
    const form = A.$('#task-editor form');
    if (form) form.addEventListener('submit', event => {
      event.preventDefault(); if (!A.forms.validate(form)) return;
      const values = Object.fromEntries(new FormData(form).entries());
      const tasks = A.data.tasks();
      const task = { id: Math.max(0, ...tasks.map(item => item.id)) + 1, title: values.title.trim(), priority: values.priority, due: values.due, assignee: values.assignee.trim(), done: false };
      A.data.saveTasks([...tasks, task]); A.data.log('Created task', 'TSK-' + task.id);
      A.modal.close(form.closest('dialog')); form.reset(); A.toast('success', 'Task added', task.title);
    });
    document.addEventListener('demo:tasks-changed', render); render();
  };
})(window.Admin);
