# decorators.py
"""
Декораторы для проверки прав доступа
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request
from models import db, User
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def login_required(f):
    """
    Декоратор: требуется авторизация

    Проверяет:
    - Наличие user_id в сессии
    - Существование пользователя в БД
    - Подтверждение аккаунта администратором
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходима авторизация', 'warning')
            return redirect(url_for('auth.login'))

        # Проверяем существование пользователя
        user = db.session.get(User, session['user_id'])
        if not user:
            session.clear()
            flash('Пользователь не найден. Войдите снова.', 'error')
            return redirect(url_for('auth.login'))

        # Проверяем подтверждение аккаунта
        if not user.approved:
            session.clear()
            flash('Ваш аккаунт ожидает подтверждения администратора', 'warning')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Декоратор: требуются права администратора

    Автоматически включает @login_required
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходима авторизация', 'warning')
            return redirect(url_for('auth.login'))

        user = db.session.get(User, session['user_id'])

        if not user:
            session.clear()
            flash('Пользователь не найден', 'error')
            return redirect(url_for('auth.login'))

        if user.role != 'admin':
            flash('Доступ запрещен. Требуются права администратора.', 'error')
            logger.warning(f"[SECURITY] Попытка доступа без прав: {user.email} -> {request.path}")
            return redirect(url_for('courses.list'))

        return f(*args, **kwargs)

    return decorated_function


def role_required(*roles):
    """
    Декоратор: требуется одна из указанных ролей

    Args:
        *roles: Список допустимых ролей ('admin', 'teacher', 'student')

    Пример:
        @role_required('admin', 'teacher')
        def create_course():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Необходима авторизация', 'warning')
                return redirect(url_for('auth.login'))

            user = db.session.get(User, session['user_id'])

            if not user:
                session.clear()
                flash('Пользователь не найден', 'error')
                return redirect(url_for('auth.login'))

            if not user.approved:
                flash('Ваш аккаунт ожидает подтверждения', 'warning')
                return redirect(url_for('auth.login'))

            if user.role not in roles:
                flash(f'У вас нет прав для этого действия. Требуется роль: {", ".join(roles)}', 'error')
                logger.warning(f"[SECURITY] Недостаточно прав: {user.email} (role={user.role}) -> {request.path}")
                return redirect(url_for('courses.list'))

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def course_owner_required(f):
    """
    Декоратор: требуется быть владельцем курса или админом

    Ожидает course_id в аргументах функции

    Пример:
        @course_owner_required
        def edit_course(course_id):
            ...
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходима авторизация', 'warning')
            return redirect(url_for('auth.login'))

        # Получаем course_id из kwargs или args
        course_id = kwargs.get('course_id') or (args[0] if args else None)

        if not course_id:
            flash('Неверный запрос', 'error')
            return redirect(url_for('courses.list'))

        from models import Course

        course = db.session.get(Course, course_id)
        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        if not user:
            session.clear()
            flash('Пользователь не найден', 'error')
            return redirect(url_for('auth.login'))

        # Проверяем: владелец курса или администратор
        if course.creator_id != user.id and user.role != 'admin':
            flash('Вы не являетесь владельцем этого курса', 'error')
            logger.warning(f"[SECURITY] Попытка редактирования чужого курса: {user.email} -> course_id={course_id}")
            return redirect(url_for('courses.detail', course_id=course_id))

        return f(*args, **kwargs)

    return decorated_function


def test_owner_required(f):
    """
    Декоратор: требуется быть владельцем теста (через курс) или админом

    Ожидает test_id в аргументах функции
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Необходима авторизация', 'warning')
            return redirect(url_for('auth.login'))

        # Получаем test_id из kwargs или args
        test_id = kwargs.get('test_id') or (args[0] if args else None)

        if not test_id:
            flash('Неверный запрос', 'error')
            return redirect(url_for('courses.list'))

        from models import Test

        test = db.session.get(Test, test_id)
        if not test:
            flash('Тест не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        if not user:
            session.clear()
            flash('Пользователь не найден', 'error')
            return redirect(url_for('auth.login'))

        # Проверяем: владелец курса (в котором тест) или администратор
        if test.course.creator_id != user.id and user.role != 'admin':
            flash('Вы не являетесь владельцем этого теста', 'error')
            logger.warning(f"[SECURITY] Попытка редактирования чужого теста: {user.email} -> test_id={test_id}")
            return redirect(url_for('courses.detail', course_id=test.course_id))

        return f(*args, **kwargs)

    return decorated_function


def anonymous_only(f):
    """
    Декоратор: только для НЕ авторизованных пользователей

    Используется для страниц login/register - если пользователь уже вошел,
    перенаправляет на главную
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user and user.approved:
                flash('Вы уже авторизованы', 'info')

                # Перенаправляем в зависимости от роли
                if user.role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                else:
                    return redirect(url_for('courses.list'))

        return f(*args, **kwargs)

    return decorated_function


def confirmed_required(f):
    """
    Декоратор: требуется подтвержденный аккаунт

    Дополнительная проверка для особо важных действий
    """

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user = db.session.get(User, session['user_id'])

        if not user.approved:
            flash('Ваш аккаунт ожидает подтверждения администратором', 'warning')
            return redirect(url_for('courses.list'))

        return f(*args, **kwargs)

    return decorated_function


def rate_limit_by_user(max_requests=5, window=60):
    """
    Декоратор: ограничение частоты запросов для пользователя

    Args:
        max_requests (int): Максимум запросов
        window (int): Временное окно в секундах

    Простая реализация (для production лучше использовать Redis)
    """
    from datetime import datetime, timedelta

    # Хранилище: {user_id: [(timestamp, timestamp, ...)]}
    request_log = {}

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            now = datetime.utcnow()

            # Инициализация лога для пользователя
            if user_id not in request_log:
                request_log[user_id] = []

            # Удаляем старые записи
            cutoff = now - timedelta(seconds=window)
            request_log[user_id] = [
                ts for ts in request_log[user_id] if ts > cutoff
            ]

            # Проверяем лимит
            if len(request_log[user_id]) >= max_requests:
                flash(f'Слишком много запросов. Попробуйте через {window} секунд.', 'warning')
                logger.warning(f"[RATE_LIMIT] User {user_id} exceeded limit on {request.path}")
                return redirect(request.referrer or url_for('courses.list'))

            # Добавляем текущий запрос
            request_log[user_id].append(now)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def log_access(action):
    """
    Декоратор: логирование действий пользователя

    Args:
        action (str): Описание действия

    Пример:
        @log_access("Создание курса")
        def create_course():
            ...
    """

    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            user = db.session.get(User, session['user_id'])

            logger.info(f"[ACTION] {action} | User: {user.email} | Path: {request.path}")

            return f(*args, **kwargs)

        return decorated_function

    return decorator