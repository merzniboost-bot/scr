# routes/auth.py
"""
Маршруты авторизации: вход, выход, регистрация
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from models import db, User
from decorators import anonymous_only
from utils import is_valid_email
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# В routes/auth.py, обновить маршруты:

@auth_bp.route('/login', methods=['GET', 'POST'])
@anonymous_only
def login():
    """Страница входа в систему"""
    if request.method == 'POST':
        login_input = request.form.get('email', '').strip()  # Может быть email или username
        password = request.form.get('password', '')

        logger.info(f"[LOGIN] Попытка входа: {login_input}")

        if not login_input or not password:
            flash('Заполните все поля', 'error')
            return render_template('login.html', mode='login')

        try:
            # Ищем пользователя по email или username
            # Сначала пробуем как email (регистронезависимо)
            user = User.query.filter(
                (User.email.ilike(login_input)) | (User.username.ilike(login_input))
            ).first()

            if not user:
                logger.warning(f"[LOGIN] Пользователь {login_input} не найден")
                flash('Неверные данные для входа', 'error')
                return render_template('login.html', mode='login')

            if not user.check_password(password):
                logger.warning(f"[LOGIN] Неверный пароль для {login_input}")
                flash('Неверные данные для входа', 'error')
                return render_template('login.html', mode='login')

            if not user.approved:
                logger.warning(f"[LOGIN] Пользователь {login_input} не подтвержден")
                flash('Ваша учетная запись ожидает подтверждения администратора', 'warning')
                return render_template('login.html', mode='login')

            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['email'] = user.email
            session['role'] = user.role

            logger.info(f"[LOGIN] ✅ Успешный вход: {user.email} (username={user.username}, role={user.role})")
            flash(f'Добро пожаловать, {user.fullname}!', 'success')

            # Перенаправляем на сохраненный URL или на страницу по умолчанию
            next_url = session.pop('next_url', None)
            if next_url:
                return redirect(next_url)
            
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('courses.list'))

        except Exception as e:
            logger.error(f"[LOGIN] ❌ Ошибка: {e}")
            flash('Произошла ошибка. Попробуйте позже.', 'error')
            return render_template('login.html', mode='login')

    return render_template('login.html', mode='login')


@auth_bp.route('/register', methods=['GET', 'POST'])
@anonymous_only
def register():
    """Страница регистрации"""
    from models import Group

    # Получаем все группы для dropdown
    groups = Group.query.order_by(Group.name).all()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        role = request.form.get('role', 'student')
        group_name = request.form.get('group_name', '').strip()
        position = request.form.get('position', '').strip()

        logger.info(f"[REGISTER] Попытка регистрации: {email}")

        # Валидация
        if len(username) < 3:
            flash('Имя пользователя должно содержать минимум 3 символа', 'error')
            return render_template('login.html', mode='register', groups=groups)

        if not fullname:
            flash('Введите полное имя', 'error')
            return render_template('login.html', mode='register', groups=groups)

        if len(password) < 8:
            flash('Пароль должен содержать минимум 8 символов', 'error')
            return render_template('login.html', mode='register', groups=groups)

        if password != password_confirm:
            flash('Пароли не совпадают', 'error')
            return render_template('login.html', mode='register', groups=groups)

        if not is_valid_email(email):
            flash('Неверный формат email', 'error')
            return render_template('login.html', mode='register', groups=groups)

        if role not in ['student', 'teacher']:
            role = 'student'

        try:
            existing = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()

            if existing:
                flash('Пользователь с таким именем или email уже существует', 'error')
                return render_template('login.html', mode='register', groups=groups)

            # Создание пользователя
            user = User(
                username=username,
                fullname=fullname,
                email=email,
                role=role,
                position=position if position else None,
                approved=False
            )
            user.set_password(password)

            # Назначение группы (если указана)
            if group_name and role == 'student':
                group = Group.query.filter_by(name=group_name).first()
                if group:
                    user.group_id = group.id

            db.session.add(user)
            db.session.commit()

            logger.info(f"[REGISTER] ✅ Новый пользователь: {email} ({role})")
            flash('Регистрация прошла успешно! Ожидайте подтверждения администратора.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[REGISTER] ❌ Ошибка: {e}")
            flash('Произошла ошибка при регистрации. Попробуйте позже.', 'error')
            return render_template('login.html', mode='register', groups=groups)

    return render_template('login.html', mode='register', groups=groups)


@auth_bp.route('/logout')
def logout():
    """Выход из системы"""
    email = session.get('email', 'Unknown')
    session.clear()

    logger.info(f"[LOGOUT] Пользователь {email} вышел")
    flash('Вы успешно вышли из системы', 'info')

    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
def profile():
    """Профиль пользователя (TODO: реализовать)"""
    from decorators import login_required

    @login_required
    def view_profile():
        user = db.session.get(User, session['user_id'])
        return render_template('profile.html', user=user)

    return view_profile()