"""
Маршруты для управления категориями курсов
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify
from models import db, Category, User, Course
from decorators import login_required, admin_required
import logging

logger = logging.getLogger(__name__)

categories_bp = Blueprint('categories', __name__)


@categories_bp.route('/admin/categories')
@login_required
@admin_required
def list_categories():
    """
    Список всех категорий (только для админов)
    """
    try:
        categories = Category.query.order_by(Category.name).all()
        
        # Статистика по каждой категории
        for category in categories:
            category.course_count = category.courses.count()
            category.creator_name = User.query.get(category.created_by).fullname if User.query.get(category.created_by) else 'Неизвестно'
        
        return render_template('categories/list.html', categories=categories)
        
    except Exception as e:
        logger.error(f"[CATEGORIES] ❌ Ошибка загрузки категорий: {e}")
        flash('Ошибка при загрузке категорий', 'error')
        return redirect(url_for('courses.list'))


@categories_bp.route('/admin/categories/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_category():
    """
    Создание новой категории (только для админов)
    """
    try:
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            color = request.form.get('color', '#12A0F4').strip()
            icon = request.form.get('icon', '📚').strip()
            
            # Валидация
            if not name:
                flash('Введите название категории', 'error')
                return render_template('categories/create.html')
            
            if len(name) < 3:
                flash('Название категории должно содержать минимум 3 символа', 'error')
                return render_template('categories/create.html')
            
            # Проверка уникальности
            existing_category = Category.query.filter_by(name=name).first()
            if existing_category:
                flash('Категория с таким названием уже существует', 'error')
                return render_template('categories/create.html')
            
            # Создание категории
            category = Category(
                name=name,
                description=description,
                color=color,
                icon=icon,
                created_by=session['user_id']
            )
            
            db.session.add(category)
            db.session.commit()
            
            logger.info(f"[CATEGORIES] ✅ Категория создана: {name} (ID={category.id})")
            flash(f'Категория "{name}" успешно создана!', 'success')
            return redirect(url_for('categories.list_categories'))
        
        # GET запрос
        return render_template('categories/create.html')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[CATEGORIES] ❌ Ошибка создания категории: {e}")
        flash('Ошибка при создании категории', 'error')
        return render_template('categories/create.html')


@categories_bp.route('/admin/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    """
    Редактирование категории (только для админов)
    """
    try:
        category = Category.query.get_or_404(category_id)
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            color = request.form.get('color', '#12A0F4').strip()
            icon = request.form.get('icon', '📚').strip()
            is_active = request.form.get('is_active', 'false') == 'true'
            
            # Валидация
            if not name:
                flash('Введите название категории', 'error')
                return render_template('categories/edit.html', category=category)
            
            # Проверка уникальности (исключая текущую)
            existing = Category.query.filter(
                Category.name == name,
                Category.id != category_id
            ).first()
            
            if existing:
                flash('Категория с таким названием уже существует', 'error')
                return render_template('categories/edit.html', category=category)
            
            # Обновление
            category.name = name
            category.description = description
            category.color = color
            category.icon = icon
            category.is_active = is_active
            
            db.session.commit()
            
            logger.info(f"[CATEGORIES] ✏️ Категория обновлена: {name} (ID={category_id})")
            flash(f'Категория "{name}" успешно обновлена!', 'success')
            return redirect(url_for('categories.list_categories'))
        
        # GET запрос
        return render_template('categories/edit.html', category=category)
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[CATEGORIES] ❌ Ошибка редактирования категории: {e}")
        flash('Ошибка при редактировании категории', 'error')
        return render_template('categories/edit.html', category=category)


@categories_bp.route('/admin/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    """
    Удаление категории (только для админов)
    """
    try:
        category = Category.query.get_or_404(category_id)
        category_name = category.name
        
        # Проверка использования в курсах
        course_count = category.courses.count()
        if course_count > 0:
            flash(f'Невозможно удалить категорию "{category_name}", так как она используется в {course_count} курсах. Сначала переназначьте курсы.', 'error')
            return redirect(url_for('categories.list_categories'))
        
        db.session.delete(category)
        db.session.commit()
        
        logger.info(f"[CATEGORIES] 🗑️ Категория удалена: {category_name} (ID={category_id})")
        flash(f'Категория "{category_name}" успешно удалена!', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[CATEGORIES] ❌ Ошибка удаления категории: {e}")
        flash('Ошибка при удалении категории', 'error')
    
    return redirect(url_for('categories.list_categories'))


@categories_bp.route('/api/categories')
def get_categories_api():
    """
    API для получения списка категорий (используется в форме создания курса)
    """
    try:
        categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
        
        categories_list = []
        for category in categories:
            categories_list.append({
                'id': category.id,
                'name': category.name,
                'color': category.color,
                'icon': category.icon
            })
        
        return jsonify({'success': True, 'categories': categories_list})
        
    except Exception as e:
        logger.error(f"[CATEGORIES] ❌ Ошибка API категорий: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@categories_bp.route('/admin/categories/<int:category_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_category(category_id):
    """
    Активация/деактивация категории
    """
    try:
        category = Category.query.get_or_404(category_id)
        category.is_active = not category.is_active
        db.session.commit()
        
        status = "активирована" if category.is_active else "деактивирована"
        logger.info(f"[CATEGORIES] 🔄 Категория {status}: {category.name} (ID={category_id})")
        flash(f'Категория "{category.name}" {status}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"[CATEGORIES] ❌ Ошибка переключения категории: {e}")
        flash('Ошибка при изменении статуса категории', 'error')
    
    return redirect(url_for('categories.list_categories'))