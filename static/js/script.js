// script.js - Общий функционал для страницы логина/регистрации

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Автоматическое закрытие flash-сообщений через 5 секунд
    const flashMessages = document.querySelectorAll('.flash-message, .alert');
    flashMessages.forEach(function(message) {
        setTimeout(function() {
            message.style.opacity = '0';
            setTimeout(function() {
                message.remove();
            }, 300);
        }, 5000);
    });

    // Плавная анимация появления форм
    const forms = document.querySelectorAll('.form');
    forms.forEach(function(form) {
        form.style.opacity = '0';
        form.style.transform = 'translateY(20px)';
        setTimeout(function() {
            form.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            form.style.opacity = '1';
            form.style.transform = 'translateY(0)';
        }, 100);
    });

    // Валидация email в реальном времени
    const emailInputs = document.querySelectorAll('input[type="email"]');
    emailInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            const email = this.value;
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (email && !emailRegex.test(email)) {
                this.style.borderColor = '#f44336';
            } else {
                this.style.borderColor = '';
            }
        });
    });

    // Показ/скрытие пароля (если есть кнопка)
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    passwordInputs.forEach(function(input) {
        const toggleBtn = input.parentElement.querySelector('.password-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', function() {
                const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                input.setAttribute('type', type);
                this.textContent = type === 'password' ? '👁️' : '🙈';
            });
        }
    });
});

// Улучшенная валидация паролей
function validatePassword(password) {
    const minLength = 8;
    const hasUpperCase = /[A-Z]/.test(password);
    const hasLowerCase = /[a-z]/.test(password);
    const hasNumbers = /\d/.test(password);
    
    return {
        isValid: password.length >= minLength && hasUpperCase && hasLowerCase && hasNumbers,
        errors: {
            length: password.length < minLength,
            upperCase: !hasUpperCase,
            lowerCase: !hasLowerCase,
            numbers: !hasNumbers
        }
    };
}

// Экспорт функций для использования в других скриптах
if (typeof window !== 'undefined') {
    window.validatePassword = validatePassword;
}

