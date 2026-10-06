document.addEventListener('change', event => {
  if (event.target.matches('[data-record-page-size]')) event.target.form.requestSubmit();
});
