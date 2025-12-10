# app.py
"""
Главный файл приложения - объединенная платформа обучения
Запуск: python app.py
"""
from flask import Flask, render_template, redirect, url_for, session, request, abort, flash
from flask_wtf.csrf import generate_csrf
from config import config, BASE_DIR
from models import db, bcrypt, User
from routes import register_blueprints
from utils import init_demo_data
import logging
import os

# ============================================================================
# ЛОГИРОВАНИЕ
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ============================================================================

def create_app(config_name='development'):
    """
    Фабрика приложения Flask

    Args:
        config_name: Имя конфигурации ('development' или 'production')

    Returns:
        Flask приложение
    """
    app = Flask(__name__)

    # Загрузка конфигурации
    app.config.from_object(config[config_name])

    # Инициализация расширений
    db.init_app(app)
    bcrypt.init_app(app)

    # CSRF защита
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    # Rate Limiting - отключаем для разработки или делаем очень мягким
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    # В режиме разработки делаем очень мягкие лимиты или отключаем
    if config_name == 'development':
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["10000 per day", "1000 per hour", "100 per minute"],
            storage_uri="memory://",
            default_limits_exempt_when=lambda: True  # Отключаем для разработки
        )
    else:
        def exempt_static():
            """Исключение статических файлов и служебных маршрутов из rate limiting"""
            from flask import request
            return (request.path.startswith('/static') or 
                    request.path.startswith('/health') or
                    request.path.startswith('/robots.txt'))

        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["1000 per day", "200 per hour", "30 per minute"],
            storage_uri="memory://",
            default_limits_exempt_when=exempt_static
        )

    # Регистрация Blueprint'ов
    register_blueprints(app)

    # Контекстный процессор
    @app.context_processor
    def inject_user():
        """Внедрение текущего пользователя в шаблоны"""
        # Не делаем запросы к БД для статических файлов
        if request.path.startswith('/static'):
            return dict(current_user=None, csrf_token=generate_csrf)
        
        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user:
                return dict(current_user=user, csrf_token=generate_csrf)
        return dict(current_user=None, csrf_token=generate_csrf)

    # ========================================================================
    # ПРОВЕРКА АВТОРИЗАЦИИ ДЛЯ ВСЕХ МАРШРУТОВ
    # ========================================================================

    @app.before_request
    def require_login():
        """
        Проверка авторизации для всех маршрутов, кроме исключений
        """
        # Исключения: страницы авторизации, статические файлы, служебные маршруты
        # ВАЖНО: проверяем статические файлы ПЕРВЫМИ, чтобы не делать лишних проверок
        if request.path.startswith('/static'):
            return None
        
        excluded_paths = [
            '/auth/login',
            '/auth/register',
            '/health',
            '/robots.txt',
            '/favicon.ico'
        ]
        
        # Проверяем, не является ли текущий путь исключением
        if request.path in excluded_paths:
            return None
        
        # Проверяем, начинается ли путь с /auth (для всех маршрутов авторизации)
        if request.path.startswith('/auth'):
            return None
        
        # Для всех остальных маршрутов требуется авторизация
        if 'user_id' not in session:
            # Сохраняем URL, на который пользователь пытался зайти
            session['next_url'] = request.url
            return redirect(url_for('auth.login'))
        
        # Проверяем существование пользователя (только если есть user_id в сессии)
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

    # ========================================================================
    # ГЛАВНЫЕ МАРШРУТЫ
    # ========================================================================

    @app.route('/')
    def home():
        """Главная страница - редирект на страницу авторизации или список курсов"""
        # Если пользователь не авторизован, редирект на страницу авторизации
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        
        # Если пользователь авторизован, редирект на список курсов
        user = db.session.get(User, session['user_id'])
        if user and user.approved:
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('courses.list'))
        
        # Если аккаунт не подтвержден, редирект на авторизацию
        return redirect(url_for('auth.login'))

    @app.route('/about')
    def about():
        """О платформе"""
        # Авторизация проверяется в before_request
        return render_template('about.html')

    @app.route('/contact')
    def contact():
        """Контакты"""
        # Авторизация проверяется в before_request
        return render_template('contact.html')

    # ========================================================================
    # ОБРАБОТЧИКИ ОШИБОК
    # ========================================================================

    @app.errorhandler(403)
    def forbidden_error(error):
        """Ошибка 403 - Доступ запрещен"""
        logger.warning(f"[403] Доступ запрещен: {request.url}")
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        """Ошибка 404 - Страница не найдена"""
        logger.warning(f"[404] Страница не найдена: {request.url}")
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Ошибка 500 - Внутренняя ошибка сервера"""
        db.session.rollback()
        logger.error(f"[500] Внутренняя ошибка: {error}")
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Ошибка 429 - Слишком много запросов"""
        logger.warning(f"[429] Rate limit: {request.remote_addr}")
        return render_template('errors/429.html'), 429

    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Ошибка 413 - Файл слишком большой"""
        logger.warning(f"[413] Файл слишком большой: {request.url}")
        return render_template('errors/413.html'), 413

    # ========================================================================
    # СЛУЖЕБНЫЕ МАРШРУТЫ
    # ========================================================================

    @app.route('/health')
    def health_check():
        """Проверка работоспособности приложения"""
        try:
            # Проверка подключения к БД
            db.session.execute(db.text('SELECT 1'))
            return {'status': 'ok', 'database': 'connected'}, 200
        except Exception as e:
            logger.error(f"[HEALTH] Ошибка: {e}")
            return {'status': 'error', 'message': str(e)}, 500

    @app.route('/robots.txt')
    def robots():
        """Файл robots.txt для поисковых роботов"""
        return """User-agent: *
Disallow: /admin/
Disallow: /auth/
Disallow: /uploads/
""", 200, {'Content-Type': 'text/plain'}

    # ========================================================================
    # ФИЛЬТРЫ JINJA2
    # ========================================================================

    @app.template_filter('datetime')
    def format_datetime(value, format='%d.%m.%Y %H:%M'):
        """Форматирование datetime"""
        if value is None:
            return '—'
        return value.strftime(format)

    @app.template_filter('date')
    def format_date(value):
        """Форматирование даты"""
        if value is None:
            return '—'
        return value.strftime('%d.%m.%Y')

    @app.template_filter('timeago')
    def timeago(value):
        """Относительное время (например: "2 часа назад")"""
        if value is None:
            return '—'

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        # Приводим value к offset-aware, если он offset-naive
        if value.tzinfo is None:
            # Если value без временной зоны, считаем его UTC
            value = value.replace(tzinfo=timezone.utc)
        elif value.tzinfo != timezone.utc:
            # Если value с другой временной зоной, конвертируем в UTC
            value = value.astimezone(timezone.utc)
        
        diff = now - value

        seconds = diff.total_seconds()

        if seconds < 60:
            return 'только что'
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f'{minutes} мин. назад'
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f'{hours} ч. назад'
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f'{days} дн. назад'
        else:
            return value.strftime('%d.%m.%Y')

    return app


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ — РАБОТАЕТ С SQLite, MySQL, PostgreSQL
# ============================================================================

from sqlalchemy import inspect, text

def init_db(app):
    """
    Универсальная инициализация БД + миграции без Alembic
    """
    with app.app_context():
        logger.info("Инициализация базы данных...")

        # 1. Создаём все таблицы из моделей
        db.create_all()

        # 2. Простые миграции "на лету"
        inspector = inspect(db.engine)

        # Миграция: добавляем колонку max_attempts в таблицу tests
        if 'tests' in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns('tests')}
            if 'max_attempts' not in columns:
                logger.info("Миграция: добавляем колонку max_attempts в таблицу tests")
                try:
                    # Универсальный способ через SQLAlchemy Core
                    from sqlalchemy import Column, Integer
                    from sqlalchemy.sql import table, column

                    tests_table = table('tests',
                        column('id', Integer),
                        column('max_attempts', Integer)
                    )

                    with db.engine.connect() as conn:
                        conn.execute(
                            tests_table.update()
                            .where(tests_table.c.max_attempts.is_(None))
                            .values(max_attempts=0)
                        )
                        # Добавляем колонку (диалектозависимо, но SQLAlchemy сам подстроится)
                        conn.execute(text(
                            "ALTER TABLE tests ADD COLUMN max_attempts INTEGER DEFAULT 0 NOT NULL"
                        ))
                        conn.commit()
                    logger.info("Колонка max_attempts успешно добавлена")
                except Exception as e:
                    logger.warning(f"Не удалось добавить колонку max_attempts (возможно, уже существует): {e}")

        # 3. Определяем, пуста ли база (универсально для всех СУБД)
        try:
            user_count = db.session.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        except Exception:
            user_count = 0

        if user_count == 0:
            logger.info("База данных пуста → создаём демо-данные")
            init_demo_data()
        else:
            logger.info(f"В базе уже есть данные ({user_count} пользователей)")
            # Проверяем, есть ли хотя бы один админ
            admin = User.query.filter_by(role='admin').first()
            if not admin:
                logger.warning("Администратор не найден → создаём демо-данные заново")
                init_demo_data()

        logger.info("Инициализация базы данных завершена")


# ============================================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================================

if __name__ == '__main__':
    env = os.environ.get('FLASK_ENV', 'development')
    debug_mode = env == 'development'

    app = create_app(config_name=env)

    # Инициализируем БД только при прямом запуске python app.py
    init_db(app)

    print("\n" + "=" * 80)
    print("ПЛАТФОРМА ОБУЧЕНИЯ - ЗАПУСК")
    print("=" * 80)
    print(f"Режим: {env.upper()}")
    print(f"Debug: {debug_mode}")
    print(f"URL: http://localhost:5000")
    print(f"База: {app.config['SQLALCHEMY_DATABASE_URI'][:50]}...")
    # print("\nДемо-аккаунты:")
    # print("   Администратор: admin@example.com / Admin123!")
    # print("   Преподаватель: teacher@example.com / Teacher123!")
    # print("   Студент:       student@example.com / Student123!")
    # print("\nВАЖНО: Измените пароли в production!")
    print("=" * 80 + "\n")