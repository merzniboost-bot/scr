# create_admin.py
"""
Скрипт для создания администратора
Использование: python create_admin.py
"""
from app import create_app, db
from models import User

# Создаем приложение в контексте
app = create_app('development')

with app.app_context():
    # Проверяем, существует ли уже пользователь с именем admin
    admin = User.query.filter_by(username='admin').first()
    
    if admin:
        print("Администратор с именем 'admin' уже существует!")
    else:
        # Создаем нового администратора
        admin = User(
            username='admin',
            fullname='Administrator',
            email='admin@example.com',
            role='admin',
            approved=True
        )
        admin.set_password('123123')  # Устанавливаем пароль
        
        db.session.add(admin)
        db.session.commit()
        print("Администратор успешно создан!")
        print("Логин: admin")
        print("Пароль: 123123")
        print("Роль: admin")
        
    # Выводим список всех администраторов
    admins = User.query.filter_by(role='admin').all()
    print("\nТекущие администраторы в системе:")
    for i, admin in enumerate(admins, 1):
        print(f"{i}. {admin.username} ({admin.email})")
