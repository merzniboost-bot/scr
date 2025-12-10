// ============================================================================
// ПЕРЕКЛЮЧЕНИЕ ТЕМЫ — КРАСИВАЯ АНИМАЦИЯ БЕЗ ВРАЩЕНИЯ
// ============================================================================

document.addEventListener('DOMContentLoaded', function () {
    const themeToggle = document.getElementById('themeToggle');
    if (!themeToggle) return;

    const themeIcon = themeToggle.querySelector('.theme-icon');
    const themeText  = themeToggle.querySelector('.theme-text');

    // Загружаем сохранённую тему
    const savedTheme = localStorage.getItem('theme') || 'dark';
    applyTheme(savedTheme);

    themeToggle.addEventListener('click', function (e) {
        e.preventDefault();

        const isLight = document.body.classList.contains('light-theme');
        const newTheme = isLight ? 'dark' : 'light';

        // Добавляем класс анимации
        themeToggle.classList.add('theme-switching');

        // Меняем тему через 300 мс (в середине анимации — выглядит максимально плавно)
        setTimeout(() => {
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        }, 300);

        // Убираем класс анимации после завершения
        setTimeout(() => {
            themeToggle.classList.remove('theme-switching');
        }, 600);
    });

    function applyTheme(theme) {
        if (theme === 'light') {
            document.body.classList.add('light-theme');
            document.body.classList.remove('dark-theme');
            if (themeIcon) themeIcon.textContent = '';
            if (themeText)  themeText.textContent  = 'Светлая';
        } else {
            document.body.classList.add('dark-theme');
            document.body.classList.remove('light-theme');
            if (themeIcon) themeIcon.textContent = '';
            if (themeText)  themeText.textContent  = 'Тёмная';
        }
    }

    // ========================================================================
    // ВЫПАДАЮЩЕЕ МЕНЮ ПРОФИЛЯ
    // ========================================================================
    
    const profileBtn = document.getElementById('profileBtn');
    const profileDropdown = document.getElementById('profileDropdown');
    
    if (profileBtn && profileDropdown) {
        // Открытие/закрытие меню по клику на иконку
        profileBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            e.preventDefault();
            profileDropdown.classList.toggle('show');
        });
        
        // Закрытие меню при клике вне его
        document.addEventListener('click', function(e) {
            if (!profileDropdown.contains(e.target) && !profileBtn.contains(e.target)) {
                profileDropdown.classList.remove('show');
            }
        });
        
        // Закрытие меню при клике на ссылку
        const dropdownLinks = profileDropdown.querySelectorAll('.dropdown-link');
        dropdownLinks.forEach(link => {
            link.addEventListener('click', function() {
                profileDropdown.classList.remove('show');
            });
        });
        
        // Закрытие меню при нажатии Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                profileDropdown.classList.remove('show');
            }
        });
    }

    // ========================================================================
    // ПЛАВНАЯ ПРОКРУТКА ДЛЯ ЯКОРНЫХ ССЫЛОК
    // ========================================================================
    
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href.length > 1) {
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
    
    // ========================================================================
    // АНИМАЦИЯ ПОЯВЛЕНИЯ ЭЛЕМЕНТОВ ПРИ ПРОКРУТКЕ
    // ========================================================================
    
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);
    
    // Применяем анимацию к карточкам курсов
    document.querySelectorAll('.course-card').forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(card);
    });
    
    // ========================================================================
    // ИЗБРАННОЕ ЧЕРЕЗ AJAX
    // ========================================================================
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    window.toggleFavoriteAjax = function(courseId, button) {
        const csrfToken = document.querySelector('input[name=csrf_token]')?.value || '';
        
        fetch(`/courses/${courseId}/favorite/toggle`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `csrf_token=${encodeURIComponent(csrfToken)}`,
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                button.textContent = data.is_favorite ? '★' : '☆';
                button.style.color = data.is_favorite ? '#FFD700' : '#999';
                button.title = data.is_favorite ? 'Убрать из избранного' : 'Добавить в избранное';
            }
        })
        .catch(error => {
            console.error('Ошибка обновления избранного:', error);
            // При ошибке отправляем форму обычным способом
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `/courses/${courseId}/favorite/toggle`;
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = csrfToken;
            form.appendChild(csrfInput);
            document.body.appendChild(form);
            form.submit();
        });
    };
    
    // ========================================================================
    // СОЗДАНИЕ КАРТОЧКИ КУРСА
    // ========================================================================
    
    function createCourseCard(course) {
        const previewImg = course.preview_filename 
            ? `<img src="/lessons/upload/${course.preview_filename}" alt="${escapeHtml(course.title)}" style="width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s ease;">`
            : `<div style="width: 100%; height: 100%; background: linear-gradient(135deg, #12A0F4 0%, #0A5D8E 100%); display: flex; align-items: center; justify-content: center; font-size: 64px;">📚</div>`;
        
        const progressHtml = course.progress_percent > 0 
            ? `<div class="course-progress" style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px;">
                    <span style="color: #666; font-weight: 600;">Прогресс</span>
                    <span style="color: #12A0F4; font-weight: 700;">${course.progress_percent}%</span>
                </div>
                <div style="height: 8px; background: #e8f4f8; border-radius: 10px; overflow: hidden;">
                    <div class="progress-fill" style="height: 100%; background: linear-gradient(90deg, #12A0F4, #0A5D8E); width: ${course.progress_percent}%; border-radius: 10px; transition: width 0.8s ease-out;"></div>
                </div>
                <p style="font-size: 12px; color: #999; margin-top: 5px;">${course.progress_completed} из ${course.progress_total} уроков завершено</p>
            </div>`
            : '';
        
        const favoriteStar = course.is_favorite ? '★' : '☆';
        const favoriteColor = course.is_favorite ? '#FFD700' : '#999';
        
        return `
        <div class="course-card" style="background: white; border-radius: 20px; overflow: hidden; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12); transition: all 0.3s ease; position: relative;">
            <div style="position: relative; overflow: hidden; height: 220px;">
                ${previewImg}
                <div style="position: absolute; top: 15px; right: 15px; z-index: 10;">
                    <button type="button" onclick="toggleFavoriteAjax(${course.id}, this)" style="background: rgba(255, 255, 255, 0.9); border: none; border-radius: 50%; width: 45px; height: 45px; font-size: 22px; cursor: pointer; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2); transition: all 0.3s ease; color: ${favoriteColor};" title="${course.is_favorite ? 'Убрать из избранного' : 'Добавить в избранное'}">
                        ${favoriteStar}
                    </button>
                </div>
            </div>
            <div style="padding: 25px;">
                <h3 class="course-title" style="font-size: 22px; font-weight: 700; color: #081844; margin-bottom: 12px; line-height: 1.3;">${escapeHtml(course.title)}</h3>
                <p class="course-description" style="color: #666; font-size: 14px; line-height: 1.6; margin-bottom: 20px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${escapeHtml(course.description || 'Описание отсутствует')}</p>
                <div class="course-meta" style="display: flex; gap: 20px; margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0; font-size: 14px; color: #666;">
                    <span style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 18px;">📖</span>
                        <span><strong>${course.lesson_count}</strong> урок${course.lesson_count !== 1 ? 'ов' : ''}</span>
                    </span>
                    ${course.test_count > 0 ? `<span style="display: flex; align-items: center; gap: 6px;"><span style="font-size: 18px;">📝</span><span><strong>${course.test_count}</strong> тест${course.test_count !== 1 ? 'ов' : ''}</span></span>` : ''}
                </div>
                ${progressHtml}
                <div class="course-footer" style="display: flex; gap: 10px; align-items: center;">
                    <a href="${course.detail_url}" class="enroll-btn" style="flex: 1; padding: 14px 20px; background: linear-gradient(135deg, #0A5D8E, #12A0F4); color: white; text-align: center; border-radius: 12px; text-decoration: none; font-weight: 600; font-size: 15px; transition: all 0.3s ease; display: flex; align-items: center; justify-content: center; gap: 8px;">
                        ${course.progress_percent > 0 ? '<span>Продолжить</span><span>→</span>' : '<span>Перейти к курсу</span><span>→</span>'}
                    </a>
                </div>
            </div>
        </div>
        `;
    }
    
    // ========================================================================
    // ОБНОВЛЕНИЕ КОНТЕЙНЕРА КУРСОВ
    // ========================================================================
    
    function updateCoursesContainer(courses, container) {
        container.style.opacity = '0.5';
        container.style.transition = 'opacity 0.3s ease';
        
        setTimeout(() => {
            if (courses.length === 0) {
                container.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 100px 20px; background: rgba(255, 255, 255, 0.95); border-radius: 20px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1); margin: 40px auto; max-width: 600px; grid-column: 1 / -1;">
                        <div style="font-size: 80px; margin-bottom: 30px;">🔍</div>
                        <h2 style="font-size: 32px; color: #081844; margin-bottom: 15px; font-weight: 700;">Ничего не найдено</h2>
                        <p style="color: #666; font-size: 18px; margin-bottom: 40px; line-height: 1.6;">Попробуйте изменить поисковый запрос</p>
                    </div>
                `;
            } else {
                container.innerHTML = courses.map(course => createCourseCard(course)).join('');
            }
            
            container.style.opacity = '1';
            
            const newCards = container.querySelectorAll('.course-card');
            newCards.forEach((card, index) => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                setTimeout(() => {
                    card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }, index * 50);
            });
        }, 150);
    }
    
    function showSearchError(container) {
        container.innerHTML = `
            <div class="error-state" style="text-align: center; padding: 100px 20px; background: rgba(255, 255, 255, 0.95); border-radius: 20px; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1); margin: 40px auto; max-width: 600px; grid-column: 1 / -1;">
                <div style="font-size: 80px; margin-bottom: 30px;">⚠️</div>
                <h2 style="font-size: 32px; color: #081844; margin-bottom: 15px; font-weight: 700;">Ошибка поиска</h2>
                <p style="color: #666; font-size: 18px; margin-bottom: 40px; line-height: 1.6;">Попробуйте обновить страницу</p>
            </div>
        `;
    }
    
    // ========================================================================
    // AJAX ПОИСК
    // ========================================================================
    
    const searchInputs = document.querySelectorAll('.search-box input[type="text"], input[name="search"], input[type="search"]');
    searchInputs.forEach(searchInput => {
        const form = searchInput.closest('form');
        if (!form) return;
        
        const coursesContainer = document.querySelector('.courses-container');
        if (!coursesContainer) return;
        
        let searchTimeout;
        let isSearching = false;
        const formAction = form.getAttribute('action') || window.location.pathname;
        
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            const buttonText = submitButton.textContent.trim();
            if (buttonText.includes('Поиск') || buttonText.includes('🔍') || buttonText === '') {
                submitButton.style.display = 'none';
            }
        }
        
        const loadingIndicator = document.createElement('span');
        loadingIndicator.className = 'search-loading';
        loadingIndicator.style.cssText = 'display: none; margin-left: 10px; color: #12A0F4; font-size: 18px;';
        loadingIndicator.textContent = '⏳';
        searchInput.parentElement.style.position = 'relative';
        searchInput.parentElement.appendChild(loadingIndicator);
        
        function performSearch(searchTerm) {
            if (isSearching) return;
            isSearching = true;
            
            searchInput.classList.add('searching');
            loadingIndicator.style.display = 'inline-block';
            
            const url = new URL(formAction, window.location.origin);
            url.searchParams.set('search', searchTerm);
            url.searchParams.set('ajax', '1');
            
            fetch(url.toString(), {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                },
                credentials: 'same-origin'
            })
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    updateCoursesContainer(data.courses, coursesContainer);
                } else {
                    console.error('Ошибка поиска:', data.error);
                    showSearchError(coursesContainer);
                }
            })
            .catch(error => {
                console.error('Ошибка AJAX запроса:', error);
                form.submit();
            })
            .finally(() => {
                isSearching = false;
                searchInput.classList.remove('searching');
                loadingIndicator.style.display = 'none';
            });
        }
        
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            const searchTerm = this.value.trim();
            
            searchTimeout = setTimeout(() => {
                if (searchTerm.length >= 2 || searchTerm.length === 0) {
                    performSearch(searchTerm);
                }
            }, 500);
        });
        
        searchInput.addEventListener('search', function() {
            if (this.value === '') {
                clearTimeout(searchTimeout);
                performSearch('');
            }
        });
        
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(searchTimeout);
                performSearch(this.value.trim());
            }
        });
    });
    
    // ========================================================================
    // АНИМАЦИЯ ПРОГРЕСС-БАРОВ
    // ========================================================================
    
    document.querySelectorAll('.progress-fill').forEach(bar => {
        // Сохраняем целевую ширину из инлайн-стиля
        const targetWidth = bar.style.width || '0%';
        
        // Если ширина уже задана (например 70%), просто оставляем как есть
        if (parseFloat(targetWidth) > 0) {
            // Добавляем лёгкую задержку только для красоты
            bar.style.transition = 'none';
            bar.style.width = '0%';
            bar.offsetHeight; // магия: заставляет браузер перерисовать
            bar.style.transition = 'width 1.4s cubic-bezier(0.4, 0, 0.2, 1)';
            requestAnimationFrame(() => {
                bar.style.width = targetWidth;
            });
        }
    });
    
    // ========================================================================
    // ФЛЕШ-СООБЩЕНИЯ
    // ========================================================================
    
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach((flash, index) => {
        setTimeout(() => {
            flash.style.opacity = '1';
            flash.style.transform = 'translateX(0)';
        }, index * 100);
        
        const isImportant = flash.classList.contains('flash-error') || flash.classList.contains('flash-warning');
        const autoHideDelay = isImportant ? 7000 : 5000;
        
        const autoHideTimeout = setTimeout(() => {
            hideFlashMessage(flash);
        }, autoHideDelay);
        
        const closeBtn = flash.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                if (flash.dataset.autoHideTimeout) {
                    clearTimeout(parseInt(flash.dataset.autoHideTimeout));
                }
                hideFlashMessage(flash);
            });
        }
        
        flash.dataset.createdAt = Date.now();
        flash.dataset.autoHideTimeout = autoHideTimeout;
        
        flash.addEventListener('mouseenter', () => {
            if (flash.dataset.autoHideTimeout) {
                clearTimeout(parseInt(flash.dataset.autoHideTimeout));
            }
        });
        
        flash.addEventListener('mouseleave', () => {
            const elapsed = Date.now() - parseInt(flash.dataset.createdAt);
            const remainingTime = autoHideDelay - elapsed;
            if (remainingTime > 0) {
                const newTimeout = setTimeout(() => {
                    hideFlashMessage(flash);
                }, remainingTime);
                flash.dataset.autoHideTimeout = newTimeout;
            }
        });
    });
    
    function hideFlashMessage(flash) {
        if (flash.classList.contains('hiding')) return;
        
        flash.classList.add('hiding');
        setTimeout(() => {
            flash.remove();
            const remainingMessages = document.querySelectorAll('.flash:not(.hiding)');
            remainingMessages.forEach((msg, index) => {
                msg.style.transition = 'transform 0.3s ease';
                msg.style.transform = 'translateX(0)';
            });
        }, 300);
    }
    
    // ========================================================================
    // RIPPLE ЭФФЕКТ НА КНОПКАХ
    // ========================================================================
    
    document.querySelectorAll('.btn, .enroll-btn, button[type="submit"]').forEach(button => {
        button.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px;
                height: ${size}px;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.5);
                left: ${x}px;
                top: ${y}px;
                transform: scale(0);
                animation: ripple 0.6s ease-out;
                pointer-events: none;
            `;
            
            if (!this.style.position || this.style.position === 'static') {
                this.style.position = 'relative';
                this.style.overflow = 'hidden';
            }
            
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });
    
    // CSS для анимации ripple
    if (!document.querySelector('#ripple-style')) {
        const style = document.createElement('style');
        style.id = 'ripple-style';
        style.textContent = `
            @keyframes ripple {
                to {
                    transform: scale(4);
                    opacity: 0;
                }
            }
            
            .theme-toggle-btn.switching {
                animation: themeSwitch 0.6s ease;
            }
            
            @keyframes themeSwitch {
                0% { transform: scale(1) rotate(0deg); }
                50% { transform: scale(1.1) rotate(180deg); }
                100% { transform: scale(1) rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
});