# routes/admin.py
"""
Маршруты админ-панели: управление пользователями, группами, общая статистика
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from models import db, User, Group, Course, Lesson, Test, TestResult, UserProgress
from decorators import admin_required
import logging

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Главная страница админ-панели
    Отображает общую статистику и ожидающих подтверждения пользователей
    """
    from models import Course
    try:
        # Получаем текущего админа
        admin_user = db.session.get(User, session['user_id'])

        # Все пользователи
        all_users = User.query.order_by(User.created_at.desc()).all()

        # Пользователи, ожидающие подтверждения
        pending_users = User.query.filter_by(approved=False).order_by(User.created_at.desc()).all()

        # Все группы (с поиском если есть)
        group_search = request.args.get('group_search', '').strip()
        groups_query = Group.query
        
        if group_search:
            groups_query = groups_query.filter(
                (Group.name.ilike(f'%{group_search}%')) |
                (Group.description.ilike(f'%{group_search}%'))
            )
        
        all_groups = groups_query.order_by(Group.name).all()

        # Статистика
        stats = {
            'total_users': User.query.count(),
            'approved_users': User.query.filter_by(approved=True).count(),
            'pending_users': User.query.filter_by(approved=False).count(),
            'admins': User.query.filter_by(role='admin').count(),
            'teachers': User.query.filter_by(role='teacher').count(),
            'students': User.query.filter_by(role='student').count(),
            'total_courses': Course.query.count(),
            'total_lessons': Lesson.query.count(),
            'total_tests': Test.query.count(),
            'total_groups': Group.query.count(),
        }

        # Получаем курсы для отображения (с поиском если есть)
        course_search = request.args.get('course_search', '').strip()
        courses_query = Course.query
        
        if course_search:
            courses_query = courses_query.filter(
                (Course.title.ilike(f'%{course_search}%')) |
                (Course.description.ilike(f'%{course_search}%'))
            )
        
        recent_courses = courses_query.order_by(Course.created_at.desc()).limit(20).all()

        return render_template('admin/dashboard.html',
                               user=admin_user,
                               users=all_users,
                               pending_users=pending_users,
                               groups=all_groups,
                               stats=stats,
                               recent_courses=recent_courses)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Ошибка загрузки панели: {e}")
        flash('Ошибка загрузки данных', 'error')
        return redirect(url_for('courses.list'))


@admin_bp.route('/users')
@admin_required
def users_list():
    """
    Список всех пользователей с фильтрацией
    """
    try:
        # Фильтры
        role_filter = request.args.get('role', '')
        status_filter = request.args.get('status', '')
        search = request.args.get('search', '').strip()

        # Базовый запрос
        query = User.query

        # Применяем фильтры
        if role_filter and role_filter in ['admin', 'teacher', 'student']:
            query = query.filter_by(role=role_filter)

        if status_filter == 'approved':
            query = query.filter_by(approved=True)
        elif status_filter == 'pending':
            query = query.filter_by(approved=False)

        if search:
            query = query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.fullname.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%'))
            )

        users = query.order_by(User.created_at.desc()).all()

        return render_template('admin/users_list.html',
                               users=users,
                               role_filter=role_filter,
                               status_filter=status_filter,
                               search=search)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Ошибка загрузки пользователей: {e}")
        flash('Ошибка загрузки списка пользователей', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_user(user_id):
    """
    Подтверждение пользователя
    """
    try:
        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        if user.approved:
            flash(f'Пользователь {user.fullname} уже подтвержден', 'info')
            return redirect(url_for('admin.dashboard'))

        user.approved = True
        db.session.commit()

        logger.info(f"[ADMIN] ✅ Пользователь {user.email} подтвержден")
        flash(f'Пользователь {user.fullname} успешно подтвержден', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка подтверждения: {e}")
        flash('Ошибка при подтверждении пользователя', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/users/<int:user_id>/revoke', methods=['POST'])
@admin_required
def revoke_user(user_id):
    """
    Отзыв подтверждения пользователя
    """
    try:
        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        if user.role == 'admin':
            flash('Нельзя отозвать подтверждение администратора', 'error')
            return redirect(url_for('admin.dashboard'))

        user.approved = False
        db.session.commit()

        logger.info(f"[ADMIN] ⚠️ Подтверждение отозвано: {user.email}")
        flash(f'Подтверждение пользователя {user.fullname} отозвано', 'warning')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка отзыва: {e}")
        flash('Ошибка при отзыве подтверждения', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """
    Удаление пользователя
    """
    try:
        # Защита от удаления самого себя
        if user_id == session['user_id']:
            flash('Вы не можете удалить свой аккаунт', 'error')
            return redirect(url_for('admin.dashboard'))

        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        # Защита от удаления других админов
        if user.role == 'admin':
            flash('Невозможно удалить администратора', 'error')
            return redirect(url_for('admin.dashboard'))

        fullname = user.fullname
        email = user.email

        # Удаление (каскадное удаление настроено в моделях)
        db.session.delete(user)
        db.session.commit()

        logger.info(f"[ADMIN] 🗑️ Пользователь удален: {email}")
        flash(f'Пользователь {fullname} успешно удален', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка удаления: {e}")
        flash('Ошибка при удалении пользователя', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/users/<int:user_id>/change-role', methods=['POST'])
@admin_required
def change_user_role(user_id):
    """
    Изменение роли пользователя
    """
    try:
        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        new_role = request.form.get('role')

        if new_role not in ['admin', 'teacher', 'student']:
            flash('Неверная роль', 'error')
            return redirect(url_for('admin.dashboard'))

        # Защита от изменения своей роли
        if user_id == session['user_id']:
            flash('Вы не можете изменить свою роль', 'error')
            return redirect(url_for('admin.dashboard'))

        old_role = user.role
        user.role = new_role
        db.session.commit()

        logger.info(f"[ADMIN] 🔄 Роль изменена: {user.email} ({old_role} -> {new_role})")
        flash(f'Роль пользователя {user.fullname} изменена: {old_role} → {new_role}', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка изменения роли: {e}")
        flash('Ошибка при изменении роли', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/users/<int:user_id>/update', methods=['POST'])
@admin_required
def update_user(user_id):
    """
    Универсальное обновление пользователя
    """
    try:
        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        # Защита от изменения самого себя для некоторых полей
        if user_id == session['user_id'] and request.form.get('role') != user.role:
            flash('Вы не можете изменить свою роль', 'error')
            return redirect(url_for('admin.dashboard'))

        # Обновление полей
        fullname = request.form.get('fullname', '').strip()
        role = request.form.get('role')
        group_id = request.form.get('group_id')

        if fullname:
            user.fullname = fullname

        # Изменение роли
        if role and role in ['admin', 'teacher', 'student']:
            if user.role != role and user_id != session['user_id']:
                old_role = user.role
                user.role = role
                logger.info(f"[ADMIN] 🔄 Роль изменена: {user.email} ({old_role} -> {role})")

        # Изменение группы
        if group_id == '':
            user.group_id = None
        elif group_id:
            group = db.session.get(Group, int(group_id))
            if group:
                user.group_id = int(group_id)

        db.session.commit()

        logger.info(f"[ADMIN] ✏️ Пользователь обновлен: {user.email}")
        flash(f'Пользователь {user.fullname} успешно обновлен', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка обновления пользователя: {e}")
        flash('Ошибка при обновлении пользователя', 'error')

    return redirect(url_for('admin.dashboard'))


# ============================================================================
# УПРАВЛЕНИЕ ГРУППАМИ
# ============================================================================

@admin_bp.route('/groups')
@admin_required
def groups_list():
    """
    Список всех групп
    """
    try:
        groups = Group.query.order_by(Group.name).all()

        # Добавляем количество студентов в каждой группе
        groups_data = []
        for group in groups:
            student_count = User.query.filter_by(group_id=group.id).count()
            groups_data.append({
                'group': group,
                'student_count': student_count
            })

        return render_template('admin/groups_list.html', groups_data=groups_data)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Ошибка загрузки групп: {e}")
        flash('Ошибка загрузки списка групп', 'error')
        return redirect(url_for('admin.dashboard'))


@admin_bp.route('/groups/add', methods=['POST'])
@admin_required
def add_group():
    """
    Создание новой группы
    """
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Введите название группы', 'error')
            return redirect(url_for('admin.dashboard'))

        # Проверка существования
        existing = Group.query.filter_by(name=name).first()
        if existing:
            flash('Группа с таким названием уже существует', 'error')
            return redirect(url_for('admin.dashboard'))

        # Создание группы
        group = Group(name=name, description=description)
        db.session.add(group)
        db.session.commit()

        logger.info(f"[ADMIN] ✅ Группа создана: {name}")
        flash(f'Группа "{name}" успешно создана', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка создания группы: {e}")
        flash('Ошибка при создании группы', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/groups/<int:group_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_group(group_id):
    """
    Редактирование группы
    """
    group = db.session.get(Group, group_id)

    if not group:
        flash('Группа не найдена', 'error')
        return redirect(url_for('admin.groups_list'))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()

            if not name:
                flash('Введите название группы', 'error')
                return render_template('admin/edit_group.html', group=group)

            # Проверка дубликатов (кроме себя)
            existing = Group.query.filter(
                Group.name == name,
                Group.id != group_id
            ).first()

            if existing:
                flash('Группа с таким названием уже существует', 'error')
                return render_template('admin/edit_group.html', group=group)

            group.name = name
            group.description = description
            db.session.commit()

            logger.info(f"[ADMIN] ✏️ Группа отредактирована: {name}")
            flash(f'Группа "{name}" успешно обновлена', 'success')
            return redirect(url_for('admin.groups_list'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[ADMIN] ❌ Ошибка редактирования группы: {e}")
            flash('Ошибка при редактировании группы', 'error')

    return render_template('admin/edit_group.html', group=group)


@admin_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@admin_required
def delete_group(group_id):
    """
    Удаление группы
    """
    try:
        group = db.session.get(Group, group_id)

        if not group:
            flash('Группа не найдена', 'error')
            return redirect(url_for('admin.dashboard'))

        # Проверяем наличие студентов
        student_count = User.query.filter_by(group_id=group_id).count()

        if student_count > 0:
            flash(f'Невозможно удалить группу "{group.name}". В ней {student_count} студент(ов).', 'error')
            return redirect(url_for('admin.dashboard'))

        name = group.name
        db.session.delete(group)
        db.session.commit()

        logger.info(f"[ADMIN] 🗑️ Группа удалена: {name}")
        flash(f'Группа "{name}" успешно удалена', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка удаления группы: {e}")
        flash('Ошибка при удалении группы', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


@admin_bp.route('/groups/<int:group_id>/students')
@admin_required
def group_students(group_id):
    """
    Просмотр студентов группы
    """
    try:
        group = db.session.get(Group, group_id)

        if not group:
            flash('Группа не найдена', 'error')
            return redirect(url_for('admin.groups_list'))

        students = User.query.filter_by(group_id=group_id).order_by(User.fullname).all()

        return render_template('admin/group_students.html', group=group, students=students)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Ошибка загрузки студентов группы: {e}")
        flash('Ошибка загрузки студентов', 'error')
        return redirect(url_for('admin.groups_list'))


@admin_bp.route('/users/<int:user_id>/assign-group', methods=['POST'])
@admin_required
def assign_user_to_group(user_id):
    """
    Назначение пользователя в группу
    """
    try:
        user = db.session.get(User, user_id)

        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('admin.dashboard'))

        group_id = request.form.get('group_id')

        if group_id == 'none':
            # Убрать из группы
            user.group_id = None
            db.session.commit()
            flash(f'{user.fullname} убран из группы', 'success')
        else:
            group_id = int(group_id)
            group = db.session.get(Group, group_id)

            if not group:
                flash('Группа не найдена', 'error')
                return redirect(url_for('admin.dashboard'))

            user.group_id = group_id
            db.session.commit()

            logger.info(f"[ADMIN] 👥 Пользователь {user.email} назначен в группу {group.name}")
            flash(f'{user.fullname} назначен в группу "{group.name}"', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ADMIN] ❌ Ошибка назначения в группу: {e}")
        flash('Ошибка при назначении в группу', 'error')

    return redirect(request.referrer or url_for('admin.dashboard'))


# ============================================================================
# СТАТИСТИКА И ОТЧЕТЫ
# ============================================================================

@admin_bp.route('/statistics')
@admin_required
def statistics():
    """
    Детальная статистика платформы
    """
    try:
        # Статистика по пользователям
        user_stats = {
            'total': User.query.count(),
            'approved': User.query.filter_by(approved=True).count(),
            'pending': User.query.filter_by(approved=False).count(),
            'by_role': {
                'admin': User.query.filter_by(role='admin').count(),
                'teacher': User.query.filter_by(role='teacher').count(),
                'student': User.query.filter_by(role='student').count(),
            }
        }

        # Статистика по курсам
        course_stats = {
            'total': Course.query.count(),
            'total_lessons': Lesson.query.count(),
            'total_tests': Test.query.count(),
            'avg_lessons_per_course': db.session.query(
                db.func.avg(db.func.count(Lesson.id))
            ).select_from(Course).join(Lesson).scalar() or 0
        }

        # Статистика по прогрессу
        progress_stats = {
            'total_completions': UserProgress.query.filter_by(completed=True).count(),
            'active_students': db.session.query(
                db.func.count(db.distinct(UserProgress.user_id))
            ).scalar() or 0
        }

        # Статистика по тестам
        test_stats = {
            'total_attempts': TestResult.query.count(),
            'avg_score': db.session.query(
                db.func.avg(TestResult.score * 100.0 / TestResult.total)
            ).scalar() or 0
        }

        # Топ-5 самых популярных курсов (по количеству прогресса)
        popular_courses = db.session.query(
            Course.title,
            db.func.count(db.distinct(UserProgress.user_id)).label('student_count')
        ).join(UserProgress, Course.id == UserProgress.course_id) \
            .group_by(Course.id) \
            .order_by(db.desc('student_count')) \
            .limit(5).all()

        return render_template('admin/statistics.html',
                               user_stats=user_stats,
                               course_stats=course_stats,
                               progress_stats=progress_stats,
                               test_stats=test_stats,
                               popular_courses=popular_courses)

    except Exception as e:
        logger.error(f"[ADMIN] ❌ Ошибка загрузки статистики: {e}")
        flash('Ошибка загрузки статистики', 'error')
        return redirect(url_for('admin.dashboard'))