const verificationForm = document.querySelector('[data-verification-form]');

if (verificationForm) {
  const outcome = verificationForm.elements.status;
  const noteLabel = document.querySelector('#note-label');

  function updateNoteLabel() {
    noteLabel.textContent = outcome.value === 'in_progress'
      ? 'Lý do trả lại'
      : 'Kết quả thực tế';
  }

  outcome.addEventListener('change', updateNoteLabel);
  updateNoteLabel();
}
