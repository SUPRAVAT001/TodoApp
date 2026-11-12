/* =============================================
   TODOS JS — client-side interactions
   ============================================= */

// ── Confirm Delete Modal ──────────────────────
const deleteModal = document.getElementById('deleteModal');
let pendingDeleteId = null;

function openDeleteModal(todoId, todoTitle) {
  pendingDeleteId = todoId;
  const titleEl = document.getElementById('deleteItemTitle');
  if (titleEl) titleEl.textContent = `"${todoTitle}"`;
  if (deleteModal) deleteModal.classList.add('show');
}

function closeDeleteModal() {
  pendingDeleteId = null;
  if (deleteModal) deleteModal.classList.remove('show');
}

document.querySelectorAll('.js-delete-todo').forEach((btn) => {
  btn.addEventListener('click', () => {
    openDeleteModal(btn.dataset.todoId, btn.dataset.todoTitle || '');
  });
});

document.getElementById('cancelDeleteBtn')?.addEventListener('click', closeDeleteModal);

document.getElementById('confirmDeleteBtn')?.addEventListener('click', () => {
  if (pendingDeleteId !== null) {
    document.getElementById(`deleteForm_${pendingDeleteId}`)?.submit();
  }
});

deleteModal?.addEventListener('click', (e) => {
  if (e.target === deleteModal) closeDeleteModal();
});

// ── Auto-dismiss alerts ───────────────────────
document.querySelectorAll('.alert[data-auto-dismiss]').forEach((el) => {
  setTimeout(() => {
    el.style.transition = 'opacity .4s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 400);
  }, 4000);
});

// ── Filter buttons ────────────────────────────
const filterEmptyState = document.getElementById('filterEmptyState');
document.querySelectorAll('.filter-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');

    const filter = btn.dataset.filter;
    let visibleCount = 0;
    document.querySelectorAll('.todo-item').forEach((item) => {
      let show = true;
      if (filter === 'done') {
        show = item.classList.contains('complete');
      } else if (filter === 'open') {
        show = !item.classList.contains('complete');
      }
      item.style.display = show ? '' : 'none';
      if (show) visibleCount += 1;
    });

    if (filterEmptyState) {
      filterEmptyState.style.display = visibleCount === 0 ? '' : 'none';
    }
  });
});

// ── Register password match validation ────────
const registerForm = document.getElementById('registerForm');
if (registerForm) {
  registerForm.addEventListener('submit', (e) => {
    const p = document.getElementById('password')?.value || '';
    const cp = document.getElementById('confirm_password')?.value || '';
    const errEl = document.getElementById('registerClientError');
    if (p !== cp) {
      e.preventDefault();
      if (errEl) {
        errEl.textContent = 'Passwords do not match.';
        errEl.style.display = 'flex';
      }
      return;
    }
    if (errEl) errEl.style.display = 'none';
  });
}

// ── Loading indicator on form submit ──────────
document.querySelectorAll('form.js-loading-form').forEach((form) => {
  form.addEventListener('submit', (e) => {
    if (e.defaultPrevented || !form.checkValidity()) return;
    const btn = form.querySelector('button[type="submit"]');
    if (btn) {
      const loadingText = btn.dataset.loadingText || 'Submitting...';
      btn.disabled = true;
      btn.textContent = loadingText;
    }
  });
});
