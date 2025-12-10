# routes/__init__.py
"""
Инициализация и регистрация всех Blueprint'ов
"""
from flask import Flask


def register_blueprints(app: Flask):
    """
    Регистрация всех Blueprint'ов в приложении

    Args:
        app: Flask приложение
    """
    # Импортируем Blueprint'ы
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.courses import courses_bp
    from routes.lessons import lessons_bp
    from routes.tests import tests_bp
    from routes.user import user_bp
    from .assignments import assignments_bp

    # Регистрируем Blueprint'ы с префиксами URL
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(courses_bp, url_prefix='/courses')
    app.register_blueprint(lessons_bp, url_prefix='/lessons')
    app.register_blueprint(tests_bp, url_prefix='/tests')
    app.register_blueprint(assignments_bp, url_prefix='/assignments')
    app.register_blueprint(user_bp, url_prefix='/user')

    print("✅ Blueprint'ы зарегистрированы:")
    print("   - auth_bp      -> /auth/*")
    print("   - admin_bp     -> /admin/*")
    print("   - courses_bp   -> /courses/*")
    print("   - lessons_bp   -> /lessons/*")
    print("   - tests_bp     -> /tests/*")
    print("   - user_bp      -> /user/*")