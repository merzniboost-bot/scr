// admin.js - Функционал для админ-панели

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Автоматическое закрытие уведомлений
    const notifications = document.querySelectorAll('.notification, .flash-message');
    notifications.forEach(function(notification) {
        setTimeout(function() {
            notification.style.opacity = '0';
            setTimeout(function() {
                notification.remove();
            }, 300);
        }, 5000);
    });

    // Плавная анимация таблиц
    const tables = document.querySelectorAll('table');
    tables.forEach(function(table) {
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(function(row, index) {
            row.style.opacity = '0';
            row.style.transform = 'translateX(-20px)';
            setTimeout(function() {
                row.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                row.style.opacity = '1';
                row.style.transform = 'translateX(0)';
            }, index * 50);
        });
    });

    // Подтверждение опасных действий
    const dangerousButtons = document.querySelectorAll('.btn-danger, [data-danger="true"]');
    dangerousButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Вы уверены, что хотите выполнить это действие?')) {
                e.preventDefault();
                return false;
            }
        });
    });

    // Поиск в таблицах (если есть поле поиска)
    const searchInputs = document.querySelectorAll('input[type="search"], input[data-search]');
    searchInputs.forEach(function(input) {
        input.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const table = this.closest('.container').querySelector('table');
            if (table) {
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(function(row) {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchTerm) ? '' : 'none';
                });
            }
        });
    });

    // Автосохранение форм (опционально)
    const forms = document.querySelectorAll('form[data-autosave]');
    forms.forEach(function(form) {
        const formId = form.id || 'form-' + Math.random().toString(36).substr(2, 9);
        const inputs = form.querySelectorAll('input, textarea, select');
        
        // Загрузка сохраненных данных
        inputs.forEach(function(input) {
            const savedValue = localStorage.getItem(formId + '-' + input.name);
            if (savedValue && !input.value) {
                input.value = savedValue;
            }
        });

        // Сохранение при изменении
        inputs.forEach(function(input) {
            input.addEventListener('change', function() {
                localStorage.setItem(formId + '-' + input.name, this.value);
            });
        });

        // Очистка при успешной отправке
        form.addEventListener('submit', function() {
            inputs.forEach(function(input) {
                localStorage.removeItem(formId + '-' + input.name);
            });
        });
    });
});

// Функция для показа уведомлений
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = 'notification notification-' + type;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? '#4caf50' : type === 'error' ? '#f44336' : '#2196f3'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(function() {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(function() {
            notification.remove();
        }, 300);
    }, 3000);
}

// Функция для подтверждения действий
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Экспорт функций для использования в других скриптах
if (typeof window !== 'undefined') {
    window.showNotification = showNotification;
    window.confirmAction = confirmAction;
}

// Добавление стилей для анимаций
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
`;
document.head.appendChild(style);

