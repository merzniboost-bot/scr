document.addEventListener('DOMContentLoaded', function () {
    const forms = document.querySelectorAll('.admin-search-form');
    if (!forms.length) return;

    const debounce = (fn, delay = 350) => {
        let t;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), delay);
        };
    };

    const bindUserActions = () => {
        const userModal = document.getElementById('user-modal');
        if (!userModal) return;
        document.querySelectorAll('.edit-user').forEach(btn => {
            btn.addEventListener('click', function() {
                const userId = this.dataset.userId;
                const fullname = this.dataset.fullname;
                const email = this.dataset.email;
                const groupId = this.dataset.group;
                const role = this.dataset.role;
                
                document.getElementById('user-id').value = userId;
                document.getElementById('user-fullname').value = fullname;
                document.getElementById('user-email').value = email;
                document.getElementById('user-group').value = groupId;
                document.getElementById('user-role').value = role;
                
                const form = document.getElementById('user-form');
                if (form) form.action = `/admin/users/${userId}/update`;
                userModal.classList.add('active');
            });
        });

        document.querySelectorAll('.delete-user').forEach(btn => {
            btn.addEventListener('click', function() {
                const userId = this.dataset.userId;
                const username = this.dataset.username;
                const deleteForm = document.getElementById('delete-form');
                const deleteMessage = document.getElementById('delete-message');
                const deleteModal = document.getElementById('delete-modal');
                if (deleteMessage) {
                    deleteMessage.textContent = `Вы уверены, что хотите удалить пользователя "${username}"? Это действие нельзя отменить.`;
                }
                if (deleteForm) deleteForm.action = `/admin/users/${userId}/delete`;
                if (deleteModal) deleteModal.classList.add('active');
            });
        });
    };

    const updateDOM = (htmlMap, counts) => {
        if (htmlMap.users_html) {
            const tbody = document.getElementById('users-table-body');
            if (tbody) {
                tbody.innerHTML = htmlMap.users_html;
                bindUserActions();
            }
        }
        if (htmlMap.pending_html) {
            const tbody = document.getElementById('pending-table-body');
            if (tbody) {
                tbody.innerHTML = htmlMap.pending_html;
            }
        }
        if (htmlMap.courses_html) {
            const tbody = document.getElementById('courses-table-body');
            if (tbody) {
                tbody.innerHTML = htmlMap.courses_html;
            }
        }
        if (htmlMap.groups_html) {
            const tbody = document.getElementById('groups-table-body');
            if (tbody) {
                tbody.innerHTML = htmlMap.groups_html;
            }
        }

        if (counts) {
            const { users, pending, courses, groups } = counts;
            const setText = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            setText('users-table-count', users);
            setText('pending-table-count', pending);
            setText('courses-table-count', courses);
            setText('groups-table-count', groups);
        }
    };

    const performSearch = debounce((form, input) => {
        const formData = new FormData(form);
        const params = new URLSearchParams(formData);
        params.set('ajax', '1');
        const url = `${form.action}?${params.toString()}`;
        input.classList.add('loading');
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.json())
            .then(data => {
                if (data && data.success) {
                    updateDOM(data, data.counts || {});
                }
            })
            .catch(err => {
                console.error('Admin search error:', err);
            })
            .finally(() => {
                input.classList.remove('loading');
            });
    }, 400);

    forms.forEach(form => {
        const input = form.querySelector('input[type="search"]');
        if (!input) return;
        input.addEventListener('input', () => performSearch(form, input));
    });

    // Первичная привязка действий для уже отрендеренных строк
    bindUserActions();
});
