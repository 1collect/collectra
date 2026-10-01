/* Menus are portalled to the body so table overflow never clips them. */
(function (A) {
  'use strict';
  let current = null;
  function close(restoreFocus = false) {
    if (!current) return;
    const { trigger, menu, marker } = current;
    menu.hidden = true; trigger.setAttribute('aria-expanded', 'false');
    if (marker.parentNode) marker.replaceWith(menu);
    current = null;
    if (restoreFocus && trigger.isConnected) trigger.focus();
  }
  function open(trigger, coordinates) {
    if (current && current.trigger === trigger) { close(true); return; }
    close();
    const id = trigger.getAttribute('aria-controls');
    const menu = document.getElementById(id);
    if (!menu) return;
    const marker = document.createComment('dropdown original position');
    menu.replaceWith(marker);
    // A menu inside a modal must stay inside that modal's top layer.
    (trigger.closest('dialog[open]') || document.body).append(menu);
    menu.hidden = false; trigger.setAttribute('aria-expanded', 'true');
    const rect = trigger.getBoundingClientRect();
    const box = menu.getBoundingClientRect();
    const x = coordinates ? coordinates.x : (trigger.dataset.align === 'end' ? rect.right - box.width : rect.left);
    const y = coordinates ? coordinates.y : rect.bottom + 5;
    menu.style.left = Math.max(8, Math.min(x, innerWidth - box.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, innerHeight - box.height - 8)) + 'px';
    current = { trigger, menu, marker };
    const first = menu.querySelector('button:not([disabled]),a,input:not([disabled])');
    if (first && !menu.classList.contains('column-menu')) first.focus();
  }
  A.dropdown = { open, close };
  A.initDropdowns = function () {
    document.addEventListener('click', event => {
      const trigger = event.target.closest('[data-dropdown]');
      if (trigger) { event.preventDefault(); open(trigger); return; }
      if (!current) return;
      if (!current.menu.contains(event.target)) close();
      else if (event.target.closest('[data-menu-close],a.dropdown-item,button.dropdown-item:not([data-keep-open])')) close();
    });
    document.addEventListener('keydown', event => {
      if (!current) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
      else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) && !event.target.matches('input,textarea,select')) {
        const items = A.$$('button:not([disabled]),a,input:not([disabled])', current.menu).filter(el => el.offsetParent !== null);
        if (!items.length) return;
        event.preventDefault();
        let index = items.indexOf(document.activeElement);
        if (event.key === 'Home') index = 0;
        else if (event.key === 'End') index = items.length - 1;
        else index = (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[index].focus();
      }
    });
    document.addEventListener('focusin', event => {
      if (current && !current.menu.contains(event.target) && current.trigger !== event.target) close();
    });
    document.addEventListener('scroll', event => { if (current && !current.menu.contains(event.target)) close(); }, true);
    window.addEventListener('resize', () => close());
    document.addEventListener('contextmenu', event => {
      const target = event.target.closest('[data-context-menu]');
      if (!target) return;
      event.preventDefault(); open(target, { x: event.clientX, y: event.clientY });
    });
  };
})(window.Admin);
