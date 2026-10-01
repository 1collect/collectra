(function (A) {
  'use strict';
  A.initTabs = function () {
    A.$$('[data-tabs]').forEach(group => {
      const tabs = A.$$('[role="tab"]', group).filter(tab => tab.closest('[data-tabs]') === group);
      const activate = tab => {
        tabs.forEach(button => {
          const selected = button === tab;
          button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
          const panel = document.getElementById(button.getAttribute('aria-controls'));
          if (panel) panel.hidden = !selected;
        });
      };
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => activate(tab));
        tab.addEventListener('keydown', event => {
          const vertical = tab.closest('[role="tablist"]').getAttribute('aria-orientation') === 'vertical';
          const forward = vertical ? 'ArrowDown' : 'ArrowRight';
          const backward = vertical ? 'ArrowUp' : 'ArrowLeft';
          let target = null;
          if (event.key === forward) target = tabs[(index + 1) % tabs.length];
          else if (event.key === backward) target = tabs[(index - 1 + tabs.length) % tabs.length];
          else if (event.key === 'Home') target = tabs[0];
          else if (event.key === 'End') target = tabs[tabs.length - 1];
          if (target) { event.preventDefault(); activate(target); target.focus(); }
        });
      });
      const hash = location.hash.slice(1);
      activate(tabs.find(tab => tab.getAttribute('aria-controls') === hash) || tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0]);
    });
  };
})(window.Admin);
