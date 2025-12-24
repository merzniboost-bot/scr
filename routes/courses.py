# routes/courses.py
"""
Маршруты курсов: список, просмотр, создание, редактирование, удаление
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify
from models import db, Course, Lesson, Test, Question, User, UserProgress, Favorite, TestResult, Assignment, Submission, Category
from decorators import login_required, role_required, course_owner_required
from utils import (
    save_file,
    delete_file,
    allowed_file,
    get_course_progress,
    is_course_favorite,
    get_lesson_progress_map,
    render_mini_content,
    sanitize_html_description,
    html_to_plain_text,
)
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

courses_bp = Blueprint('courses', __name__)


@courses_bp.route('/')
@courses_bp.route('/list')
@login_required
def list():
    """
    Список всех доступных курсов с поиском и фильтрацией
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Параметры фильтрации
        search = request.args.get('search', '').strip()
        filter_by = request.args.get('filter', 'all')  # all, my, favorites

        # Базовый запрос
        query = Course.query

        # Применяем фильтры
        if filter_by == 'my' and user.role in ['teacher', 'admin']:
            query = query.filter_by(creator_id=user.id)
        elif filter_by == 'favorites':
            query = query.join(Favorite, Course.id == Favorite.course_id) \
                .filter(Favorite.user_id == user.id)

        # Поиск по названию и описанию (поддержка русского и английского)
        if search:
            query = query.filter(
                (Course.title.ilike(f'%{search}%')) |
                (Course.description.ilike(f'%{search}%'))
            )

        # Получаем курсы
        courses = query.order_by(Course.updated_at.desc()).all()

        # Добавляем информацию о прогрессе и избранном для каждого курса
        courses_data = []
        for course in courses:
            progress = get_course_progress(user.id, course.id) if user.role == 'student' else None
            is_fav = is_course_favorite(user.id, course.id)

            # Безопасный подсчет тестов (на случай ошибки с max_attempts)
            try:
                test_count = len(course.tests)
            except Exception:
                # Если ошибка при загрузке тестов, используем прямой запрос
                from sqlalchemy import text
                result = db.session.execute(
                    text('SELECT COUNT(*) FROM tests WHERE course_id = :course_id'),
                    {'course_id': course.id}
                ).scalar()
                test_count = result or 0

            courses_data.append({
                'course': course,
                'progress': progress,
                'is_favorite': is_fav,
                'lesson_count': len(course.lessons),
                'test_count': test_count
            })

        # Если это AJAX запрос, возвращаем JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
            courses_json = []
            for item in courses_data:
                courses_json.append({
                    'id': item['course'].id,
                    'title': item['course'].title,
                    'description': html_to_plain_text(item['course'].description) if item['course'].description else '',
                    'preview_filename': item['course'].preview_filename,
                    'lesson_count': item['lesson_count'],
                    'test_count': item['test_count'],
                    'progress_percent': item['progress']['percent'] if item['progress'] else 0,
                    'progress_completed': item['progress']['completed'] if item['progress'] else 0,
                    'progress_total': item['progress']['total'] if item['progress'] else 0,
                    'is_favorite': item['is_favorite'],
                    'created_at': item['course'].created_at.isoformat() if item['course'].created_at else None,
                    'detail_url': url_for('courses.detail', course_id=item['course'].id),
                    'favorite_url': url_for('courses.toggle_favorite', course_id=item['course'].id)
                })
            return jsonify({
                'success': True,
                'courses': courses_json,
                'count': len(courses_json)
            })

        return render_template('courses/list.html',
                               courses_data=courses_data,
                               search=search,
                               filter_by=filter_by)

    except Exception as e:
        logger.error(f"[COURSES] ❌ Ошибка загрузки курсов: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('ajax') == '1':
            return jsonify({'success': False, 'error': str(e)}), 500
        flash('Ошибка загрузки списка курсов. Возможно, требуется обновление базы данных.', 'error')
        # Не делаем редирект на home, чтобы избежать бесконечного цикла
        # Вместо этого показываем страницу с ошибкой
        return render_template('errors/500.html'), 500


@courses_bp.route('/<int:course_id>')
@login_required
def detail(course_id):
    """
    Детальная страница курса с уроками и тестами
    """
    try:
        course = db.session.get(Course, course_id)

        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Прогресс пользователя (теперь включает тесты!)
        progress = get_course_progress(user.id, course.id)

        # Избранное
        is_fav = is_course_favorite(user.id, course.id)

        # Карта завершенных уроков
        lesson_progress = get_lesson_progress_map(user.id, course.id)
        
        # Карта завершенных тестов (НОВОЕ!)
        from utils import get_test_progress_map
        test_progress = get_test_progress_map(user.id, course.id)

        # Проверяем права на редактирование
        can_edit = (user.role == 'admin' or course.creator_id == user.id)
        
        # Получаем тесты безопасно
                # === ОБЪЕДИНЁННЫЙ СПИСОК МАТЕРИАЛОВ ===
        materials = []

        # 1. Добавляем уроки (сортируем по order)
        for lesson in sorted(course.lessons, key=lambda l: l.order):
            materials.append({
                'type': 'lesson',
                'id': lesson.id,
                'title': lesson.title,
                'description': render_mini_content(
                    lesson.content[:300] + '...' if lesson.content and len(lesson.content) > 300 else (lesson.content or 'Нет описания')
                ),
                'created_at': lesson.created_at,
                'order': lesson.order,
                'video_filename': lesson.video_filename,
                'file_filename': lesson.file_filename,
                'open_at': lesson.open_at,
            })

        # 2. Добавляем тесты
        try:
            tests_list = list(course.tests)
        except Exception:
            tests_list = Test.query.filter_by(course_id=course_id).all()

        for test in tests_list:
            try:
                questions_count = len(test.questions)
            except Exception:
                questions_count = 0

            materials.append({
                'type': 'test',
                'id': test.id,
                'title': test.title,
                'description': f'Тест из {questions_count} вопрос{"ов" if questions_count != 1 else "а"}',
                'created_at': test.created_at,
                'max_attempts': test.max_attempts,
                'open_at': test.open_at,
                'questions_count': questions_count,
                'order': test.order or 999999,
            })

        # 3. Сортировка: уроки по order, тесты вставляются по дате создания
        # Для этого создаём ключ сортировки: (приоритет типа, значение)
        # Уроки имеют приоритет 0 и сортируются по order
        # Тесты имеют приоритет 1 и сортируются по created_at

        materials.sort(key=lambda x: x['order'])

        from datetime import datetime
        from utils import get_next_incomplete_material
        next_material = get_next_incomplete_material(user.id, course.id)
        
        return render_template('courses/detail.html',
                               course=course,
                               progress=progress,
                               is_favorite=is_fav,
                               lesson_progress=lesson_progress,
                               test_progress=test_progress,
                               materials=materials,  # ← передаём новый список
                               can_edit=can_edit,
                               now=datetime.utcnow(),
                               next_material=next_material)

    except Exception as e:
        logger.error(f"[COURSES] ❌ Ошибка загрузки курса: {e}")
        flash('Ошибка загрузки курса', 'error')
        return redirect(url_for('courses.list'))


@courses_bp.route('/create', methods=['GET', 'POST'])
@role_required('admin', 'teacher')
def create():
    """
    Создание нового курса
    """
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = sanitize_html_description(request.form.get('description', ''))
            category_id = request.form.get('category_id', '').strip()

            # Валидация
            if not title:
                flash('Введите название курса', 'error')
                categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
                return render_template('courses/create.html', categories=categories)

            if len(title) < 5:
                flash('Название курса должно содержать минимум 5 символов', 'error')
                return render_template('courses/create.html')

            # Обработка превью (опционально)
            preview_filename = None
            if 'preview' in request.files:
                preview = request.files['preview']
                if preview and preview.filename and allowed_file(preview.filename):
                    preview_filename = save_file(preview, prefix='preview')

            # Создание курса
            course = Course(
                title=title,
                description=description,
                preview_filename=preview_filename,
                creator_id=session['user_id'],
                category_id=int(category_id) if category_id else None
            )

            db.session.add(course)
            db.session.commit()

            logger.info(f"[COURSES] ✅ Курс создан: {title} (ID={course.id})")
            flash(f'Курс "{title}" успешно создан!', 'success')

            return redirect(url_for('courses.detail', course_id=course.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[COURSES] ❌ Ошибка создания курса: {e}")
            flash('Ошибка при создании курса', 'error')
            return render_template('courses/create.html')

    # GET запрос - показываем форму с категориями
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    return render_template('courses/create.html', categories=categories)


@courses_bp.route('/<int:course_id>/edit', methods=['GET', 'POST'])
@course_owner_required
def edit(course_id):
    """
    Редактирование курса
    """
    course = db.session.get(Course, course_id)

    if not course:
        flash('Курс не найден', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = sanitize_html_description(request.form.get('description', ''))
            category_id = request.form.get('category_id', '').strip()

            # Валидация
            if not title:
                flash('Введите название курса', 'error')
                lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order).all()
                tests = Test.query.filter_by(course_id=course_id).order_by(Test.created_at).all()
                return render_template('courses/edit.html', course=course, lessons=lessons, tests=tests)

            if len(title) < 5:
                flash('Название курса должно содержать минимум 5 символов', 'error')
                lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order).all()
                tests = Test.query.filter_by(course_id=course_id).order_by(Test.created_at).all()
                return render_template('courses/edit.html', course=course, lessons=lessons, tests=tests)

            # Обработка превью
            if 'preview' in request.files:
                preview = request.files['preview']
                if preview and preview.filename and allowed_file(preview.filename):
                    # Удаляем старое превью
                    if course.preview_filename:
                        delete_file(course.preview_filename)

                    course.preview_filename = save_file(preview, prefix='preview')

            # Удаление превью
            if request.form.get('delete_preview') == 'true' and course.preview_filename:
                delete_file(course.preview_filename)
                course.preview_filename = None

            # Обновление данных
            course.title = title
            course.description = description
            course.category_id = int(category_id) if category_id else None
            course.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            logger.info(f"[COURSES] ✏️ Курс отредактирован: {title} (ID={course_id})")
            flash(f'Курс "{title}" успешно обновлен', 'success')

            return redirect(url_for('courses.detail', course_id=course_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[COURSES] ❌ Ошибка редактирования курса: {e}")
            flash('Ошибка при редактировании курса', 'error')

    # Получаем уроки и тесты курса, отсортированные по порядку
    lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order).all()
    tests = Test.query.filter_by(course_id=course_id).order_by(Test.created_at).all()
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    
    return render_template('courses/edit.html', 
                         course=course, 
                         lessons=lessons, 
                         tests=tests,
                         categories=categories)


@courses_bp.route('/<int:course_id>/delete', methods=['POST'])
@course_owner_required
def delete(course_id):
    """
    Удаление курса
    """
    try:
        course = db.session.get(Course, course_id)

        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        title = course.title

        # Удаляем превью
        if course.preview_filename:
            delete_file(course.preview_filename)

        # Удаляем файлы уроков
        for lesson in course.lessons:
            if lesson.video_filename:
                delete_file(lesson.video_filename)
            if lesson.file_filename:
                delete_file(lesson.file_filename)

        # Удаляем курс (каскадное удаление уроков, тестов и т.д.)
        db.session.delete(course)
        db.session.commit()

        logger.info(f"[COURSES] 🗑️ Курс удален: {title} (ID={course_id})")
        flash(f'Курс "{title}" успешно удален', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[COURSES] ❌ Ошибка удаления курса: {e}")
        flash('Ошибка при удалении курса', 'error')

    return redirect(url_for('courses.my_courses'))


@courses_bp.route('/my-courses')
@role_required('admin', 'teacher')
def my_courses():
    """
    Список курсов текущего преподавателя
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Получаем курсы пользователя
        courses = Course.query.filter_by(creator_id=user.id) \
            .order_by(Course.updated_at.desc()).all()

        # Добавляем статистику
        courses_data = []
        for course in courses:
            # Количество студентов, изучающих курс
            student_count = db.session.query(
                db.func.count(db.distinct(UserProgress.user_id))
            ).filter_by(course_id=course.id).scalar() or 0

            # Безопасный подсчет тестов
            try:
                test_count = len(course.tests)
            except Exception:
                from sqlalchemy import text
                result = db.session.execute(
                    text('SELECT COUNT(*) FROM tests WHERE course_id = :course_id'),
                    {'course_id': course.id}
                ).scalar()
                test_count = result or 0

            courses_data.append({
                'course': course,
                'lesson_count': len(course.lessons),
                'test_count': test_count,
                'student_count': student_count
            })

        return render_template('courses/my_courses.html',
                               courses_data=courses_data)

    except Exception as e:
        logger.error(f"[COURSES] ❌ Ошибка загрузки моих курсов: {e}")
        flash('Ошибка загрузки ваших курсов', 'error')
        return redirect(url_for('courses.list'))


@courses_bp.route('/<int:course_id>/favorite/toggle', methods=['POST'])
@login_required
def toggle_favorite(course_id):
    """
    Добавить/убрать курс из избранного
    """
    try:
        course = db.session.get(Course, course_id)

        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        user_id = session['user_id']

        # Проверяем существование
        existing = db.session.query(Favorite).filter_by(
            user_id=user_id,
            course_id=course_id
        ).first()

        if existing:
            # Убираем из избранного
            db.session.delete(existing)
            db.session.commit()
            logger.info(f"[FAVORITE] ⭐ Убран из избранного: курс {course_id} пользователем {user_id}")
            is_favorite = False
            message = f'Курс "{course.title}" удален из избранного'
            flash(message, 'info')
        else:
            # Добавляем в избранное
            favorite = Favorite(user_id=user_id, course_id=course_id)
            db.session.add(favorite)
            db.session.commit()
            logger.info(f"[FAVORITE] ⭐ Добавлен в избранное: курс {course_id} пользователем {user_id}")
            is_favorite = True
            message = f'Курс "{course.title}" добавлен в избранное'
            flash(message, 'success')

        # Если это AJAX запрос, возвращаем JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'is_favorite': is_favorite,
                'message': message
            })

    except Exception as e:
        db.session.rollback()
        logger.error(f"[FAVORITE] ❌ Ошибка: {e}")
        error_message = 'Ошибка при обновлении избранного'
        flash(error_message, 'error')
        
        # Если это AJAX запрос, возвращаем JSON с ошибкой
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_message
            }), 500

    return redirect(request.referrer or url_for('courses.detail', course_id=course_id))


@courses_bp.route('/<int:course_id>/students')
@course_owner_required
def course_students(course_id):
    """
    Список студентов, изучающих курс (для преподавателя)
    """
    try:
        course = db.session.get(Course, course_id)

        if not course:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        # Собираем всех студентов, у которых есть прогресс по урокам или тестам курса
        lesson_user_ids = db.session.query(UserProgress.user_id).filter_by(course_id=course_id).distinct().all()
        lesson_user_ids = {row[0] for row in lesson_user_ids}

        from sqlalchemy import select
        test_ids_subq = select(Test.id).filter_by(course_id=course_id)
        test_user_ids = db.session.query(TestResult.student_id).filter(TestResult.test_id.in_(test_ids_subq)).distinct().all()
        test_user_ids = {row[0] for row in test_user_ids}

        all_user_ids = lesson_user_ids | test_user_ids

        if not all_user_ids:
            students = []
        else:
            users = User.query.filter(User.id.in_(all_user_ids)).order_by(User.fullname).all()

            # Загружаем задания курса
            assignment_ids = [
                a.id for a in db.session.query(Assignment.id)
                .join(Lesson, Assignment.lesson_id == Lesson.id)
                .filter(Lesson.course_id == course_id)
                .all()
            ]

            # Подтягиваем все сдачи по курсу одним запросом
            submissions = []
            if assignment_ids:
                submissions = Submission.query.filter(
                    Submission.assignment_id.in_(assignment_ids),
                    Submission.student_id.in_(all_user_ids)
                ).all()

            submissions_by_student = {}
            for s in submissions:
                submissions_by_student.setdefault(s.student_id, []).append(s)

            # Результаты тестов по курсу
            test_results = TestResult.query.join(Test, TestResult.test_id == Test.id) \
                .filter(Test.course_id == course_id, TestResult.student_id.in_(all_user_ids)).all()

            tests_by_student = {}
            for tr in test_results:
                tests_by_student.setdefault(tr.student_id, []).append(tr)

            students = []
            for user in users:
                progress = get_course_progress(user.id, course.id)
                students.append({
                    'user': user,
                    'completed': progress['completed'],
                    'total': progress['total'],
                    'percent': progress['percent'],
                    'lessons_completed': progress['lessons_completed'],
                    'lessons_total': progress['lessons_total'],
                    'tests_completed': progress['tests_completed'],
                    'tests_total': progress['tests_total'],
                    'submissions': submissions_by_student.get(user.id, []),
                    'test_results': tests_by_student.get(user.id, []),
                })

        return render_template('courses/students.html',
                               course=course,
                               students=students)

    except Exception as e:
        logger.error(f"[COURSES] ❌ Ошибка загрузки студентов: {e}")
        flash('Ошибка загрузки списка студентов', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))


@courses_bp.route('/<int:course_id>/duplicate', methods=['POST'])
@role_required('admin', 'teacher')
def duplicate(course_id):
    """
    Дублирование курса (создание копии)
    """
    try:
        original = db.session.get(Course, course_id)

        if not original:
            flash('Курс не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Проверяем права (только владелец или админ)
        if original.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для дублирования этого курса', 'error')
            return redirect(url_for('courses.detail', course_id=course_id))

        # Создаем копию курса
        new_course = Course(
            title=f"{original.title} (Копия)",
            description=original.description,
            creator_id=user.id
        )
        db.session.add(new_course)
        db.session.flush()  # Получаем ID нового курса

        # Копируем уроки
        for original_lesson in original.lessons:
            new_lesson = Lesson(
                course_id=new_course.id,
                title=original_lesson.title,
                content=original_lesson.content,
                order=original_lesson.order
                # Файлы не копируем (нужно будет загрузить заново)
            )
            db.session.add(new_lesson)

        # Копируем тесты (безопасная загрузка)
        try:
            tests_to_copy = original.tests
        except Exception:
            # Если ошибка при загрузке тестов, используем прямой SQL запрос
            from sqlalchemy import text
            from models import Test
            result = db.session.execute(
                text('SELECT id, title FROM tests WHERE course_id = :course_id'),
                {'course_id': original.id}
            ).fetchall()
            # Создаем временные объекты для копирования
            tests_to_copy = []
            for row in result:
                test_obj = type('TempTest', (), {'id': row[0], 'title': row[1], 'max_attempts': 0})()
                tests_to_copy.append(test_obj)
        
        for original_test in tests_to_copy:
            # Получаем max_attempts безопасно
            max_attempts = getattr(original_test, 'max_attempts', 0)
            # Получаем title безопасно
            title = getattr(original_test, 'title', 'Тест')
            # Получаем id теста
            original_test_id = getattr(original_test, 'id', None)
            
            new_test = Test(
                course_id=new_course.id,
                title=title,
                max_attempts=max_attempts
            )
            db.session.add(new_test)
            db.session.flush()

            # Копируем вопросы (безопасная загрузка)
            try:
                questions_to_copy = original_test.questions
            except (AttributeError, Exception):
                # Если нет атрибута questions, загружаем через прямой запрос
                from sqlalchemy import text
                from models import Question
                if original_test_id:
                    questions_to_copy = Question.query.filter_by(test_id=original_test_id).all()
                else:
                    questions_to_copy = []
            
            for original_question in questions_to_copy:
                new_question = Question(
                    test_id=new_test.id,
                    text=original_question.text,
                    option1=original_question.option1,
                    option2=original_question.option2,
                    option3=original_question.option3,
                    option4=original_question.option4,
                    correct_answer=original_question.correct_answer
                )
                db.session.add(new_question)

        db.session.commit()

        logger.info(f"[COURSES] 📋 Курс дублирован: {original.title} -> ID={new_course.id}")
        flash(f'Курс "{original.title}" успешно дублирован', 'success')

        return redirect(url_for('courses.detail', course_id=new_course.id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"[COURSES] ❌ Ошибка дублирования курса: {e}")
        flash('Ошибка при дублировании курса', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))


@courses_bp.route('/search')
@login_required
def search():
    """
    Расширенный поиск курсов
    """
    try:
        query_text = request.args.get('q', '').strip()

        if not query_text:
            flash('Введите поисковый запрос', 'info')
            return redirect(url_for('courses.list'))

        # Поиск по названию и описанию
        courses = Course.query.filter(
            (Course.title.ilike(f'%{query_text}%')) |
            (Course.description.ilike(f'%{query_text}%'))
        ).order_by(Course.updated_at.desc()).all()

        user = db.session.get(User, session['user_id'])

        # Добавляем доп. информацию
        courses_data = []
        for course in courses:
            progress = get_course_progress(user.id, course.id)
            is_fav = is_course_favorite(user.id, course.id)

            # Безопасный подсчет тестов
            try:
                test_count = len(course.tests)
            except Exception:
                from sqlalchemy import text
                result = db.session.execute(
                    text('SELECT COUNT(*) FROM tests WHERE course_id = :course_id'),
                    {'course_id': course.id}
                ).scalar()
                test_count = result or 0

            courses_data.append({
                'course': course,
                'progress': progress,
                'is_favorite': is_fav,
                'lesson_count': len(course.lessons),
                'test_count': test_count
            })

        return render_template('courses/search_results.html',
                               courses_data=courses_data,
                               query=query_text)

    except Exception as e:
        logger.error(f"[COURSES] ❌ Ошибка поиска: {e}")
        flash('Ошибка при поиске курсов', 'error')
        return redirect(url_for('courses.list'))

@courses_bp.route('/<int:course_id>/reorder_materials', methods=['POST'])
@course_owner_required
def reorder_materials(course_id):
    """
    Сохранение нового порядка уроков и тестов после drag & drop
    """
    try:
        data = request.get_json()
        order_list = data.get('order', [])

        if not order_list:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400

        # Собираем все уроки и тесты курса
        lessons = Lesson.query.filter_by(course_id=course_id).all()
        tests = Test.query.filter_by(course_id=course_id).all()

        # Создаём словари для быстрого поиска
        lesson_map = {l.id: l for l in lessons}
        test_map = {t.id: t for t in tests}

        # Присваиваем новый порядок
        new_order = 1
        for item in order_list:
            item_type = item['type']
            item_id = int(item['id'])

            if item_type == 'lesson' and item_id in lesson_map:
                lesson_map[item_id].order = new_order
            elif item_type == 'test' and item_id in test_map:
                test_map[item_id].order = new_order

            new_order += 1

        db.session.commit()
        
        # Инвалидируем кэш материалов курса
        from utils import invalidate_course_cache
        invalidate_course_cache(course_id)

        logger.info(f"[COURSES] 🔄 Порядок материалов обновлён для курса {course_id}")
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        logger.error(f"[COURSES] ❌ Ошибка переупорядочивания: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500