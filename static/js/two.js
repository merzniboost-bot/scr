 
        // Получаем элементы DOM
        const openModalBtn = document.getElementById('openProfileModal');
        const closeModalBtn = document.getElementById('closeModal');
        const profileModal = document.getElementById('profileModal');
        const uploadBtn = document.getElementById('uploadBtn');
        const avatarInput = document.getElementById('avatarInput');
        const avatarPreview = document.getElementById('avatarPreview');
        const saveProfileBtn = document.getElementById('saveProfile');

        // Открытие модального окна
        openModalBtn.addEventListener('click', function() {
            profileModal.style.display = 'flex';
        });

        // Закрытие модального окна
        closeModalBtn.addEventListener('click', function() {
            profileModal.style.display = 'none';
        });

        // Закрытие модального окна при клике вне его
        window.addEventListener('click', function(event) {
            if (event.target === profileModal) {
                profileModal.style.display = 'none';
            }
        });

        // Обработка загрузки аватара
        uploadBtn.addEventListener('click', function() {
            avatarInput.click();
        });

   

// Модальное окно профиля
const modal = document.getElementById('profileModal');
const openBtn = document.getElementById('openProfileModal');
const closeBtn = document.getElementById('closeModal');

function openModal() {
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
}

openBtn.addEventListener('click', openModal);
closeBtn.addEventListener('click', closeModal);

// Закрытие по клику вне модального окна
modal.addEventListener('click', (e) => {
    if (e.target === modal) {
        closeModal();
    }
});

// Закрытие по ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === 'flex') {
        closeModal();
    }
});

// Загрузка аватара
const uploadBtn = document.getElementById('uploadBtn');
const avatarInput = document.getElementById('avatarInput');
const avatarPreview = document.getElementById('avatarPreview');

uploadBtn.addEventListener('click', () => {
    avatarInput.click();
});

avatarInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            avatarPreview.innerHTML = `<img src="${event.target.result}" alt="Avatar" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
            
            // Также обновляем аватар в карточке профиля
            const userAvatar = document.getElementById('userAvatar');
            userAvatar.innerHTML = `<img src="${event.target.result}" alt="Avatar" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
        };
        reader.readAsDataURL(file);
    }
});


// Закрытие по ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === 'flex') {
        closeModal();
    }
});

// Загрузка аватара (пока только превью)
const uploadBtn = document.getElementById('uploadBtn');
const avatarInput = document.getElementById('avatarInput');
const avatarPreview = document.getElementById('avatarPreview');

uploadBtn.addEventListener('click', () => {
    avatarInput.click();
});

avatarInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
            avatarPreview.innerHTML = `<img src="${event.target.result}" alt="Avatar" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
            
            // Также обновляем аватар в карточке
            const userAvatar = document.getElementById('userAvatar');
            userAvatar.innerHTML = `<img src="${event.target.result}" alt="Avatar" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
        };
        reader.readAsDataURL(file);
    }
});


        avatarInput.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                
                reader.addEventListener('load', function() {
                    // Создаем изображение для предпросмотра
                    const img = document.createElement('img');
                    img.src = reader.result;
                    
                    // Очищаем содержимое и добавляем изображение
                    avatarPreview.innerHTML = '';
                    avatarPreview.appendChild(img);
                });
                
                reader.readAsDataURL(file);
            }
        });

        // Сохранение профиля
        saveProfileBtn.addEventListener('click', function() {
            const fullName = document.getElementById('fullName').value;
            const position = document.getElementById('position').value;
            const bio = document.getElementById('bio').value;
            
            // Обновляем данные в карточке профиля
            document.querySelector('.profile-card h3').textContent = fullName;
            document.querySelector('.profile-card p').textContent = position;
            
            // Обновляем аватар в карточке профиля, если он был изменен
            const avatarImg = avatarPreview.querySelector('img');
            if (avatarImg) {
                const profileAvatar = document.querySelector('.profile-avatar');
                profileAvatar.innerHTML = '';
                const newImg = document.createElement('img');
                newImg.src = avatarImg.src;
                newImg.style.width = '100%';
                newImg.style.height = '100%';
                newImg.style.borderRadius = '50%';
                newImg.style.objectFit = 'cover';
                profileAvatar.appendChild(newImg);
            }
            
            // Закрываем модальное окно
            profileModal.style.display = 'none';
            
            // Показываем уведомление об успешном сохранении
            alert('Профиль успешно обновлен!');
        });
 