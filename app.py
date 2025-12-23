# app.py
"""
Главный файл приложения - объединенная платформа обучения
Запуск: python app.py
"""
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
from flask import Flask, render_template, redirect, url_for, session, request, abort, flash
from flask_wtf.csrf import generate_csrf
from config import config, BASE_DIR
from models import db, bcrypt, User
from routes import register_blueprints
# from utils import init_demo_data
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

        # КЛЮЧЕВАЯ СТРОКА: принудительно обновляем метаданные из реальной БД
        db.metadata.reflect(bind=db.engine, views=False)  # Обновляем структуру
        logger.info("Метаданные таблиц обновлены из базы данных")

        # 1. Создаём все таблицы из моделей (если чего-то нет — создаст)
        db.create_all()

        # 2. Простые миграции "на лету"
        inspector = inspect(db.engine)

        # Добавляем новые колонки из новой версии models.py
        if 'courses' in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns('courses')}
            if 'category_id' not in columns:
                logger.info("Миграция: добавляем category_id в courses")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE courses ADD COLUMN category_id INT NULL AFTER preview_filename"))
                    conn.execute(text("ALTER TABLE courses ADD INDEX idx_category_id (category_id)"))
                    conn.commit()

            if 'updated_at' not in columns:
                logger.info("Миграция: добавляем updated_at в courses")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE courses ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at"))
                    conn.commit()

        if 'lessons' in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns('lessons')}
            if 'module_id' not in columns:
                logger.info("Миграция: добавляем module_id в lessons")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE lessons ADD COLUMN module_id INT NULL AFTER course_id"))
                    conn.execute(text("ALTER TABLE lessons ADD INDEX idx_module_id (module_id)"))
                    conn.commit()
            if 'open_at' not in columns:
                logger.info("Миграция: добавляем open_at в lessons")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE lessons ADD COLUMN open_at DATETIME NULL"))
                    conn.commit()

        if 'tests' in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns('tests')}
            if 'module_id' not in columns:
                logger.info("Миграция: добавляем module_id в tests")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE tests ADD COLUMN module_id INT NULL AFTER course_id"))
                    conn.execute(text("ALTER TABLE tests ADD INDEX idx_module_id (module_id)"))
                    conn.commit()
            if 'open_at' not in columns:
                logger.info("Миграция: добавляем open_at в tests")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE tests ADD COLUMN open_at DATETIME NULL AFTER max_attempts"))
                    conn.commit()
            if 'order' not in columns:
                logger.info("Миграция: добавляем order в tests")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE tests ADD COLUMN `order` INT NOT NULL DEFAULT 1"))
                    conn.commit()
            if 'updated_at' not in columns:
                logger.info("Миграция: добавляем updated_at в tests")
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE tests ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
                    conn.commit()

        # Создаём таблицу categories, если её нет
        if 'categories' not in inspector.get_table_names():
            logger.info("Миграция: создаём таблицу categories")
            with db.engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE categories (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL UNIQUE,
                        description VARCHAR(255) DEFAULT '',
                        color VARCHAR(7) DEFAULT '#12A0F4',
                        icon VARCHAR(50) DEFAULT '📚',
                        is_active TINYINT(1) DEFAULT 1,
                        created_by INT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        CONSTRAINT fk_category_creator FOREIGN KEY (created_by) REFERENCES users(id)
                    ) ENGINE=InnoDB
                """))
                conn.commit()

        # Создаём таблицу modules, если её нет
        if 'modules' not in inspector.get_table_names():
            logger.info("Миграция: создаём таблицу modules")
            with db.engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE modules (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        course_id INT NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        `order` INT DEFAULT 0,
                        is_visible TINYINT(1) DEFAULT 1,
                        open_at DATETIME NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT fk_module_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB
                """))
                conn.commit()

        # Создаём категорию по умолчанию
        try:
            from models import Category
            default_cat = db.session.execute(text("SELECT id FROM categories WHERE name = 'Общие'")).fetchone()
            if not default_cat:
                logger.info("Создаём категорию по умолчанию")
                db.session.execute(text("""
                    INSERT INTO categories (name, description, color, icon, created_by, is_active)
                    VALUES ('Общие', 'Курсы без категории', '#12A0F4', '📚', 1, 1)
                """))
                db.session.commit()
                default_cat_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()
            else:
                default_cat_id = default_cat[0]

            # Привязываем все курсы к категории по умолчанию
            db.session.execute(text(f"UPDATE courses SET category_id = {default_cat_id} WHERE category_id IS NULL"))
            db.session.commit()
        except Exception as e:
            logger.warning(f"Не удалось создать категорию по умолчанию: {e}")

        logger.info("Инициализация базы данных завершена")


# ============================================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================================

# Создаём приложение глобально — это нужно и для gunicorn, и для flask run
app = create_app(os.environ.get('FLASK_ENV', 'production'))

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False   # пока без HTTPS

# Инициализируем БД один раз при старте (только если запускаем напрямую)
if __name__ == '__main__':
    with app.app_context():
        init_db(app)
    print("\n" + "="*80)
    print("ПЛАТФОРМА ОБУЧЕНИЯ - ЗАПУСК")
    print("="*80)
    print(f"Режим: {os.environ.get('FLASK_ENV', 'production').upper()}")
    print(f"URL: http://localhost:5000")
    print("="*80 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
