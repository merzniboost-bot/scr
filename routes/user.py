# routes/user.py
"""
Маршруты личного кабинета: прогресс, избранное, статистика
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from models import db, User, Course, Lesson, UserProgress, Favorite, TestResult, Test
from decorators import login_required
from utils import save_file, delete_file, get_course_progress, render_mini_content, is_course_favorite, get_user_statistics, save_data_url, save_avatar
import logging

logger = logging.getLogger(__name__)

user_bp = Blueprint('user', __name__)


@user_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Главная страница личного кабинета
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Для преподавателей и админов - показываем созданные курсы
        # Для студентов - показываем курсы с прогрессом
        if user.role in ['teacher', 'admin']:
            enrolled_courses = db.session.query(Course) \
                .filter(Course.creator_id == user.id) \
                .order_by(Course.created_at.desc()).all()
        else:
            # Для студентов - курсы с прогрессом
            enrolled_courses = db.session.query(Course) \
                .join(UserProgress, Course.id == UserProgress.course_id) \
                .filter(UserProgress.user_id == user.id) \
                .distinct() \
                .order_by(Course.title).all()

        # Избранные курсы
        favorite_courses = db.session.query(Course) \
            .join(Favorite, Course.id == Favorite.course_id) \
            .filter(Favorite.user_id == user.id) \
            .order_by(Favorite.added_at.desc()).all()

        # Статистика по каждому курсу
        course_stats = []
        total_lessons = 0
        completed_lessons = 0

        for course in enrolled_courses:
            # Для преподавателей/админов прогресс не считается
            if user.role in ['teacher', 'admin']:
                # Подсчитываем общее количество уроков в курсе
                total_lessons_in_course = len(course.lessons) if course.lessons else 0
                progress = {
                    'total': total_lessons_in_course,
                    'completed': 0,
                    'percent': 0,
                    'is_completed': False
                }
            else:
                progress = get_course_progress(user.id, course.id)
                total_lessons += progress['total']
                completed_lessons += progress['completed']

            is_fav = is_course_favorite(user.id, course.id)

            course_stats.append({
                'course': course,
                'course_id': course.id,
                'title': course.title,
                'description': course.description or '—',
                'total_lessons': progress['total'],
                'completed_lessons': progress['completed'],
                'progress_percent': progress['percent'],
                'is_completed': progress['is_completed'],
                'is_favorite': is_fav
            })

        # Общая статистика
        overall_percent = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0

        stats = {
            'total_courses': len(enrolled_courses),
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'overall_progress': overall_percent,
            'favorite_count': len(favorite_courses)
        }

        # Последние результаты тестов
        recent_tests = db.session.query(TestResult, Test, Course) \
            .join(Test, TestResult.test_id == Test.id) \
            .join(Course, Test.course_id == Course.id) \
            .filter(TestResult.student_id == user.id) \
            .order_by(TestResult.created_at.desc()) \
            .limit(5).all()

        recent_tests_data = []
        for result, test, course in recent_tests:
            percent = int((result.score / result.total * 100)) if result.total > 0 else 0
            recent_tests_data.append({
                'result': result,
                'test': test,
                'course': course,
                'percent': percent
            })

        return render_template('user/dashboard.html',
                               user=user,
                               course_stats=course_stats,
                               favorite_courses=favorite_courses,
                               stats=stats,
                               recent_tests=recent_tests_data)

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки дашборда: {e}")
        flash('Ошибка загрузки личного кабинета', 'error')
        return redirect(url_for('courses.list'))


@user_bp.route('/progress')
@login_required
def progress():
    """
    Детальный прогресс по всем курсам с фильтрацией
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Фильтры
        filter_type = request.args.get('filter', 'all')
        sort_type = request.args.get('sort', 'default')

        # Все курсы с прогрессом
        progress_data = db.session.query(
            Course.id,
            Course.title,
            Course.description,
            Course.preview_filename,
            db.func.count(UserProgress.id).label('total_progress'),
            db.func.sum(db.case((UserProgress.completed == True, 1), else_=0)).label('completed_count')
        ).join(UserProgress, Course.id == UserProgress.course_id) \
            .filter(UserProgress.user_id == user.id) \
            .group_by(Course.id) \
            .all()

        courses_progress = []
        for row in progress_data:
            from utils import get_lesson_progress_map
            progress = get_course_progress(user.id, row.id)

            course_item = {
                'course_id': row.id,
                'title': row.title,
                'description': row.description,
                'course': db.session.get(Course, row.id),
                'total_lessons': progress['total'],
                'completed_lessons': progress['completed'],
                'progress_percent': progress['percent'],
                'is_completed': progress['is_completed']
            }

            # Применяем фильтр
            if filter_type == 'completed' and not progress['is_completed']:
                continue
            elif filter_type == 'in_progress' and progress['is_completed']:
                continue

            courses_progress.append(course_item)

        # Сортировка
        if sort_type == 'progress':
            courses_progress.sort(key=lambda x: x['progress_percent'], reverse=True)
        elif sort_type == 'name':
            courses_progress.sort(key=lambda x: x['title'])
        elif sort_type == 'date':
            courses_progress.sort(key=lambda x: x['course'].created_at, reverse=True)
        else:
            # По умолчанию: незавершенные сначала, потом по проценту
            courses_progress.sort(key=lambda x: (x['is_completed'], -x['progress_percent']))

        return render_template('user/progress.html',
                               user=user,
                               courses_progress=courses_progress)

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки прогресса: {e}")
        flash('Ошибка загрузки прогресса', 'error')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/favorites')
@login_required
def favorites():
    """
    Избранные курсы
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Получаем избранные курсы с датой добавления
        favorites_data = db.session.query(Course, Favorite.added_at) \
            .join(Favorite, Course.id == Favorite.course_id) \
            .filter(Favorite.user_id == user.id) \
            .order_by(Favorite.added_at.desc()).all()

        favorite_courses = []
        for course, added_at in favorites_data:
            progress = get_course_progress(user.id, course.id)
            favorite_courses.append({
                'course': course,
                'added_at': added_at,
                'progress': progress,
                'lesson_count': len(course.lessons),
                'test_count': len(course.tests)
            })

        return render_template('user/favorites.html',
                               user=user,
                               favorite_courses=favorite_courses)

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки избранного: {e}")
        flash('Ошибка загрузки избранных курсов', 'error')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/statistics')
@login_required
def statistics():
    """
    Детальная статистика обучения
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Получаем общую статистику
        stats = get_user_statistics(user.id)

        # Завершенные курсы
        courses_with_progress = db.session.query(Course) \
            .join(UserProgress, Course.id == UserProgress.course_id) \
            .filter(UserProgress.user_id == user.id) \
            .distinct().all()

        completed_courses = []
        in_progress_courses = []

        for course in courses_with_progress:
            progress = get_course_progress(user.id, course.id)

            course_data = {
                'course': course,
                'progress': progress
            }

            if progress['is_completed']:
                completed_courses.append(course_data)
            else:
                in_progress_courses.append(course_data)

        # Статистика по тестам
        test_results = db.session.query(TestResult, Test, Course) \
            .join(Test, TestResult.test_id == Test.id) \
            .join(Course, Test.course_id == Course.id) \
            .filter(TestResult.student_id == user.id) \
            .order_by(TestResult.created_at.desc()).all()

        tests_data = []
        for result, test, course in test_results:
            percent = int((result.score / result.total * 100)) if result.total > 0 else 0
            tests_data.append({
                'result': result,
                'test': test,
                'course': course,
                'percent': percent
            })

        # Статистика по курсам (топ-5 по прогрессу)
        top_courses = []
        for course in courses_with_progress:
            progress = get_course_progress(user.id, course.id)
            if progress['percent'] > 0:
                top_courses.append({
                    'course': course,
                    'progress': progress
                })

        # Сортируем по проценту завершения
        top_courses.sort(key=lambda x: x['progress']['percent'], reverse=True)
        top_courses = top_courses[:5]

        # Активность по дням (последние завершенные уроки)
        recent_activity = db.session.query(UserProgress, Lesson, Course) \
            .join(Lesson, UserProgress.lesson_id == Lesson.id) \
            .join(Course, Lesson.course_id == Course.id) \
            .filter(
            UserProgress.user_id == user.id,
            UserProgress.completed == True,
            UserProgress.completed_at != None
        ) \
            .order_by(UserProgress.completed_at.desc()) \
            .limit(10).all()

        activity_data = []
        for progress, lesson, course in recent_activity:
            activity_data.append({
                'progress': progress,
                'lesson': lesson,
                'course': course
            })

        return render_template('user/statistics.html',
                               user=user,
                               stats=stats,
                               completed_courses=completed_courses,
                               in_progress_courses=in_progress_courses,
                               tests_data=tests_data,
                               top_courses=top_courses,
                               recent_activity=activity_data)

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки статистики: {e}")
        flash('Ошибка загрузки статистики', 'error')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/course/<int:course_id>/progress')
@login_required
def course_progress(course_id):
    """
    Детальный прогресс по конкретному курсу
    """
    try:
        course = db.session.get(Course, course_id)

        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('user.progress'))

        user = db.session.get(User, session['user_id'])

        # Получаем все уроки с информацией о прогрессе
        lessons_data = []
        for lesson in course.lessons:
            progress = db.session.query(UserProgress).filter_by(
                user_id=user.id,
                lesson_id=lesson.id
            ).first()

            lessons_data.append({
                'lesson': lesson,
                'is_completed': progress and progress.completed,
                'completed_at': progress.completed_at if progress else None
            })

        # Общий прогресс
        overall_progress = get_course_progress(user.id, course_id)

        # Результаты тестов по этому курсу
        test_results = db.session.query(TestResult, Test) \
            .join(Test, TestResult.test_id == Test.id) \
            .filter(
            Test.course_id == course_id,
            TestResult.student_id == user.id
        ) \
            .order_by(TestResult.created_at.desc()).all()

        tests_data = []
        for result, test in test_results:
            percent = int((result.score / result.total * 100)) if result.total > 0 else 0
            tests_data.append({
                'result': result,
                'test': test,
                'percent': percent
            })

        return render_template('user/course_progress.html',
                               course=course,
                               lessons_data=lessons_data,
                               overall_progress=overall_progress,
                               tests_data=tests_data)

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки прогресса курса: {e}")
        flash('Ошибка загрузки прогресса курса', 'error')
        return redirect(url_for('user.progress'))


@user_bp.route('/achievements')
@login_required
def achievements():
    """
    Достижения пользователя (геймификация)
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Получаем статистику
        stats = get_user_statistics(user.id)

        # Определяем достижения
        achievements_list = []

        # Достижение: Первые шаги
        if stats['completed_lessons'] >= 1:
            achievements_list.append({
                'title': '🎯 Первые шаги',
                'description': 'Завершите первый урок',
                'unlocked': True,
                'progress': 100
            })
        else:
            achievements_list.append({
                'title': '🎯 Первые шаги',
                'description': 'Завершите первый урок',
                'unlocked': False,
                'progress': 0
            })

        # Достижение: Студент
        if stats['completed_lessons'] >= 10:
            achievements_list.append({
                'title': '📚 Студент',
                'description': 'Завершите 10 уроков',
                'unlocked': True,
                'progress': 100
            })
        elif stats['completed_lessons'] > 0:
            progress = int((stats['completed_lessons'] / 10) * 100)
            achievements_list.append({
                'title': '📚 Студент',
                'description': f"Завершите 10 уроков ({stats['completed_lessons']}/10)",
                'unlocked': False,
                'progress': progress
            })
        else:
            achievements_list.append({
                'title': '📚 Студент',
                'description': 'Завершите 10 уроков (0/10)',
                'unlocked': False,
                'progress': 0
            })

        # Достижение: Мастер
        if stats['completed_lessons'] >= 50:
            achievements_list.append({
                'title': '🏆 Мастер',
                'description': 'Завершите 50 уроков',
                'unlocked': True,
                'progress': 100
            })
        elif stats['completed_lessons'] > 0:
            progress = int((stats['completed_lessons'] / 50) * 100)
            achievements_list.append({
                'title': '🏆 Мастер',
                'description': f"Завершите 50 уроков ({stats['completed_lessons']}/50)",
                'unlocked': False,
                'progress': progress
            })
        else:
            achievements_list.append({
                'title': '🏆 Мастер',
                'description': 'Завершите 50 уроков (0/50)',
                'unlocked': False,
                'progress': 0
            })

        # Достижение: Первый тест
        if stats['tests_taken'] >= 1:
            achievements_list.append({
                'title': '📝 Первый экзамен',
                'description': 'Пройдите первый тест',
                'unlocked': True,
                'progress': 100
            })
        else:
            achievements_list.append({
                'title': '📝 Первый экзамен',
                'description': 'Пройдите первый тест',
                'unlocked': False,
                'progress': 0
            })

        # Достижение: Отличник
        if stats['avg_score'] >= 90 and stats['tests_taken'] >= 5:
            achievements_list.append({
                'title': '⭐ Отличник',
                'description': 'Средний балл 90%+ по 5 тестам',
                'unlocked': True,
                'progress': 100
            })
        elif stats['tests_taken'] > 0:
            progress = min(int((stats['avg_score'] / 90) * 100), 100)
            achievements_list.append({
                'title': '⭐ Отличник',
                'description': f"Средний балл 90%+ ({stats['avg_score']}%, тестов: {stats['tests_taken']}/5)",
                'unlocked': False,
                'progress': progress
            })
        else:
            achievements_list.append({
                'title': '⭐ Отличник',
                'description': 'Средний балл 90%+ по 5 тестам',
                'unlocked': False,
                'progress': 0
            })

        # Достижение: Завершить курс
        completed_courses_count = db.session.query(db.func.count(db.distinct(UserProgress.course_id))) \
                                      .join(Course, UserProgress.course_id == Course.id) \
                                      .join(Lesson, Course.id == Lesson.course_id) \
                                      .filter(
            UserProgress.user_id == user.id,
            UserProgress.completed == True
        ) \
                                      .group_by(UserProgress.course_id) \
                                      .having(
            db.func.count(UserProgress.id) == db.func.count(Lesson.id)
        ) \
                                      .scalar() or 0

        if completed_courses_count >= 1:
            achievements_list.append({
                'title': '🎓 Выпускник',
                'description': 'Завершите полностью один курс',
                'unlocked': True,
                'progress': 100
            })
        else:
            achievements_list.append({
                'title': '🎓 Выпускник',
                'description': 'Завершите полностью один курс',
                'unlocked': False,
                'progress': stats['overall_progress']
            })

        # Подсчитываем разблокированные
        unlocked_count = sum(1 for a in achievements_list if a['unlocked'])

        return render_template('user/achievements.html',
                               user=user,
                               achievements=achievements_list,
                               unlocked_count=unlocked_count,
                               total_count=len(achievements_list))

    except Exception as e:
        logger.error(f"[USER] ❌ Ошибка загрузки достижений: {e}")
        flash('Ошибка загрузки достижений', 'error')
        return redirect(url_for('user.dashboard'))


@user_bp.route('/profile')
@login_required
def profile():
    # Страница профиля устарела — перенаправляем в личный кабинет
    return redirect(url_for('user.dashboard'))


@user_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Редактирование профиля"""
    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        try:
            fullname = request.form.get('fullname', '').strip()
            position = request.form.get('position', '').strip()
            delete_avatar_flag = request.form.get('delete_avatar') == 'true'
            avatar_file = request.files.get('avatar')
            avatar_data_url = request.form.get('avatar_cropped')

            # Валидация
            if not fullname:
                flash('Введите полное имя', 'error')
                return render_template('user/edit_profile.html', user=user)

            # Обновление основных данных
            user.fullname = fullname
            user.position = position if position else None

            # Удаление аватара по запросу
            if delete_avatar_flag and user.avatar_filename:
                delete_file(user.avatar_filename)
                user.avatar_filename = None

            # Загрузка нового аватара: приоритет data-url (обрезка на клиенте), затем файл
            if avatar_data_url:
                if user.avatar_filename:
                    delete_file(user.avatar_filename)
                saved = save_avatar(avatar_data_url, size=200)
                if saved:
                    user.avatar_filename = saved
                else:
                    flash('Не удалось сохранить изображение профиля', 'warning')

            elif avatar_file and avatar_file.filename:
                filename = avatar_file.filename
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                if ext in {'jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'tiff'}:
                    if user.avatar_filename:
                        delete_file(user.avatar_filename)
                    saved = save_avatar(avatar_file, size=200)
                    if saved:
                        user.avatar_filename = saved
                    else:
                        flash('Не удалось сохранить изображение профиля', 'warning')
                else:
                    flash('Неподдерживаемый формат изображения для фото профиля', 'warning')

            db.session.commit()

            logger.info(f"[USER] ✏️ Профиль обновлен: {user.email}")
            flash('Профиль успешно обновлен', 'success')

            return redirect(url_for('user.dashboard'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[USER] ❌ Ошибка обновления профиля: {e}")
            flash('Ошибка при обновлении профиля', 'error')

    return render_template('user/edit_profile.html', user=user)


@user_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Изменение пароля
    """
    user = db.session.get(User, session['user_id'])

    if request.method == 'POST':
        try:
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            # Валидация
            if not user.check_password(current_password):
                flash('Неверный текущий пароль', 'error')
                return render_template('user/change_password.html')

            if len(new_password) < 8:
                flash('Новый пароль должен содержать минимум 8 символов', 'error')
                return render_template('user/change_password.html')

            if new_password != confirm_password:
                flash('Пароли не совпадают', 'error')
                return render_template('user/change_password.html')

            # Обновление пароля
            user.set_password(new_password)
            db.session.commit()

            logger.info(f"[USER] 🔒 Пароль изменен: {user.email}")
            flash('Пароль успешно изменен', 'success')

            return redirect(url_for('user.profile'))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[USER] ❌ Ошибка изменения пароля: {e}")
            flash('Ошибка при изменении пароля', 'error')

    return render_template('user/change_password.html')