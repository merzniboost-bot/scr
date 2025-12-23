# routes/tests.py
"""
Маршруты тестов: создание, вопросы, прохождение, результаты
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from models import db, Test, Question, TestResult, Course, User
from decorators import login_required, course_owner_required, test_owner_required
from utils import calculate_test_score
from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo 

logger = logging.getLogger(__name__)

tests_bp = Blueprint('tests', __name__)


# ============================================================================
# СОЗДАНИЕ И УПРАВЛЕНИЕ ТЕСТАМИ
# ============================================================================

@tests_bp.route('/course/<int:course_id>/create', methods=['GET', 'POST'])
@course_owner_required
def create(course_id):
    """
    Создание нового теста для курса
    """
    course = db.session.get(Course, course_id)

    if not course:
        flash('Курс не найден', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            max_attempts = request.form.get('max_attempts', '0').strip()

            # Валидация
            if not title:
                flash('Введите название теста', 'error')
                return render_template('tests/create.html', course=course)

            if len(title) < 5:
                flash('Название теста должно содержать минимум 5 символов', 'error')
                return render_template('tests/create.html', course=course)

            # Валидация количества попыток
            try:
                max_attempts = int(max_attempts) if max_attempts else 0
                if max_attempts < 0:
                    max_attempts = 0
            except ValueError:
                max_attempts = 0
            
                        # === НОВОЕ: дата открытия теста ===
            open_at_str = request.form.get('open_at')
            open_at = None
            if open_at_str:
                try:
                    open_at = datetime.strptime(open_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Неверный формат даты и времени открытия теста', 'warning')
            # ==================================

            # Создание теста
            test = Test(
                course_id=course_id,
                title=title,
                max_attempts=max_attempts,
                open_at=open_at  # ← новая строка
            )

            db.session.add(test)
            db.session.commit()
            
            # Инвалидируем кэш материалов курса
            from utils import invalidate_course_cache
            invalidate_course_cache(course_id)

            logger.info(f"[TESTS] ✅ Тест создан: {title} (ID={test.id}, course_id={course_id})")
            flash(f'Тест "{title}" успешно создан', 'success')

            # Перенаправляем на добавление вопросов
            return redirect(url_for('tests.add_question', test_id=test.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[TESTS] ❌ Ошибка создания теста: {e}")
            flash('Ошибка при создании теста', 'error')

    return render_template('tests/create.html', course=course)


@tests_bp.route('/<int:test_id>/edit', methods=['GET', 'POST'])
@test_owner_required
def edit(test_id):
    """
    Редактирование теста
    """
    test = db.session.get(Test, test_id)

    if not test:
        flash('Тест не найден', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            max_attempts = request.form.get('max_attempts', '0').strip()

            # Валидация
            if not title:
                flash('Введите название теста', 'error')
                return render_template('tests/edit.html', test=test)

            if len(title) < 5:
                flash('Название теста должно содержать минимум 5 символов', 'error')
                return render_template('tests/edit.html', test=test)

            # Валидация количества попыток
            try:
                max_attempts = int(max_attempts) if max_attempts else 0
                if max_attempts < 0:
                    max_attempts = 0
            except ValueError:
                max_attempts = 0

                        # === НОВОЕ: дата открытия теста ===
            open_at_str = request.form.get('open_at')
            if open_at_str:
                try:
                    test.open_at = datetime.strptime(open_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Неверный формат даты и времени открытия теста', 'warning')
            else:
                test.open_at = None
            # ==================================

            test.title = title
            test.max_attempts = max_attempts
            db.session.commit()
            
            # Инвалидируем кэш материалов курса
            from utils import invalidate_course_cache
            invalidate_course_cache(test.course_id)

            logger.info(f"[TESTS] ✏️ Тест отредактирован: {title} (ID={test_id})")
            flash(f'Тест "{title}" успешно обновлен', 'success')

            return redirect(url_for('tests.manage', test_id=test_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[TESTS] ❌ Ошибка редактирования теста: {e}")
            flash('Ошибка при редактировании теста', 'error')

    return render_template('tests/edit.html', test=test)


@tests_bp.route('/<int:test_id>/delete', methods=['POST'])
@test_owner_required
def delete(test_id):
    """
    Удаление теста
    """
    try:
        test = db.session.get(Test, test_id)

        if not test:
            flash('Тест не найден', 'error')
            return redirect(url_for('courses.list'))

        course_id = test.course_id
        title = test.title

        # Удаляем тест (каскадное удаление вопросов и результатов)
        db.session.delete(test)
        db.session.commit()
        
        # Инвалидируем кэш материалов курса
        from utils import invalidate_course_cache
        invalidate_course_cache(course_id)

        logger.info(f"[TESTS] 🗑️ Тест удален: {title} (ID={test_id})")
        flash(f'Тест "{title}" успешно удален', 'success')

        return redirect(url_for('courses.detail', course_id=course_id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"[TESTS] ❌ Ошибка удаления теста: {e}")
        flash('Ошибка при удалении теста', 'error')
        return redirect(url_for('courses.list'))


@tests_bp.route('/<int:test_id>/manage')
@test_owner_required
def manage(test_id):
    """
    Управление тестом: список вопросов, добавление, редактирование
    """
    try:
        test = db.session.get(Test, test_id)

        if not test:
            flash('Тест не найден', 'error')
            return redirect(url_for('courses.list'))

        questions = db.session.query(Question).filter_by(test_id=test_id) \
            .order_by(Question.id).all()

        # Статистика по тесту
        total_attempts = db.session.query(db.func.count(TestResult.id)) \
                             .filter_by(test_id=test_id).scalar() or 0

        avg_score = db.session.query(
            db.func.avg(TestResult.score * 100.0 / TestResult.total)
        ).filter_by(test_id=test_id).scalar() or 0

        stats = {
            'total_questions': len(questions),
            'total_attempts': total_attempts,
            'avg_score': int(avg_score)
        }

        return render_template('tests/manage.html',
                               test=test,
                               questions=questions,
                               stats=stats)

    except Exception as e:
        logger.error(f"[TESTS] ❌ Ошибка загрузки управления тестом: {e}")
        flash('Ошибка загрузки теста', 'error')
        return redirect(url_for('courses.list'))


# ============================================================================
# ВОПРОСЫ
# ============================================================================

@tests_bp.route('/<int:test_id>/questions/add', methods=['GET', 'POST'])
@test_owner_required
def add_question(test_id):
    """
    Добавление вопроса в тест
    """
    test = db.session.get(Test, test_id)

    if not test:
        flash('Тест не найден', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            text = request.form.get('text', '').strip()
            option1 = request.form.get('option1', '').strip()
            option2 = request.form.get('option2', '').strip()
            option3 = request.form.get('option3', '').strip()
            option4 = request.form.get('option4', '').strip()
            correct_answer = int(request.form.get('correct_answer', 0))

            # Валидация
            if not text:
                flash('Введите текст вопроса', 'error')
                return render_template('tests/add_question.html', test=test)

            if not all([option1, option2, option3, option4]):
                flash('Заполните все варианты ответов', 'error')
                return render_template('tests/add_question.html', test=test)

            if correct_answer not in [1, 2, 3, 4]:
                flash('Выберите правильный ответ', 'error')
                return render_template('tests/add_question.html', test=test)

            # Создание вопроса
            question = Question(
                test_id=test_id,
                text=text,
                option1=option1,
                option2=option2,
                option3=option3,
                option4=option4,
                correct_answer=correct_answer
            )

            db.session.add(question)
            db.session.commit()

            logger.info(f"[TESTS] ✅ Вопрос добавлен в тест {test_id} (question_id={question.id})")
            flash('Вопрос успешно добавлен', 'success')

            # Проверяем, хочет ли пользователь добавить еще вопросы
            if request.form.get('add_another') == 'true':
                return redirect(url_for('tests.add_question', test_id=test_id))
            else:
                return redirect(url_for('tests.manage', test_id=test_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[TESTS] ❌ Ошибка добавления вопроса: {e}")
            flash('Ошибка при добавлении вопроса', 'error')

    return render_template('tests/add_question.html', test=test)


@tests_bp.route('/questions/<int:question_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_question(question_id):
    """
    Редактирование вопроса
    """
    question = db.session.get(Question, question_id)

    if not question:
        flash('Вопрос не найден', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])

    # Проверка прав
    if question.test.course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для редактирования этого вопроса', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            text = request.form.get('text', '').strip()
            option1 = request.form.get('option1', '').strip()
            option2 = request.form.get('option2', '').strip()
            option3 = request.form.get('option3', '').strip()
            option4 = request.form.get('option4', '').strip()
            correct_answer = int(request.form.get('correct_answer', 0))

            # Валидация
            if not text:
                flash('Введите текст вопроса', 'error')
                return render_template('tests/edit_question.html', question=question)

            if not all([option1, option2, option3, option4]):
                flash('Заполните все варианты ответов', 'error')
                return render_template('tests/edit_question.html', question=question)

            if correct_answer not in [1, 2, 3, 4]:
                flash('Выберите правильный ответ', 'error')
                return render_template('tests/edit_question.html', question=question)

            # Обновление вопроса
            question.text = text
            question.option1 = option1
            question.option2 = option2
            question.option3 = option3
            question.option4 = option4
            question.correct_answer = correct_answer

            db.session.commit()

            logger.info(f"[TESTS] ✏️ Вопрос отредактирован (question_id={question_id})")
            flash('Вопрос успешно обновлен', 'success')

            return redirect(url_for('tests.manage', test_id=question.test_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[TESTS] ❌ Ошибка редактирования вопроса: {e}")
            flash('Ошибка при редактировании вопроса', 'error')

    return render_template('tests/edit_question.html', question=question)


@tests_bp.route('/questions/<int:question_id>/delete', methods=['POST'])
@login_required
def delete_question(question_id):
    """
    Удаление вопроса
    """
    try:
        question = db.session.get(Question, question_id)

        if not question:
            flash('Вопрос не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])
        test_id = question.test_id

        # Проверка прав
        if question.test.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для удаления этого вопроса', 'error')
            return redirect(url_for('tests.manage', test_id=test_id))

        db.session.delete(question)
        db.session.commit()

        logger.info(f"[TESTS] 🗑️ Вопрос удален (question_id={question_id})")
        flash('Вопрос успешно удален', 'success')

        return redirect(url_for('tests.manage', test_id=test_id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"[TESTS] ❌ Ошибка удаления вопроса: {e}")
        flash('Ошибка при удалении вопроса', 'error')
        return redirect(url_for('courses.list'))


# ============================================================================
# ПРОХОЖДЕНИЕ ТЕСТОВ
# ============================================================================

@tests_bp.route('/<int:test_id>/take', methods=['GET', 'POST'])
@login_required
def take(test_id):
    """
    Прохождение теста студентом
    """
    test = db.session.get(Test, test_id)
    
    if not test:
        flash('Тест не найден', 'error')
        return redirect(url_for('courses.list'))
    # === НОВОЕ: проверка даты открытия ===
    
    if test.open_at:
        open_at_msk = test.open_at.replace(tzinfo=ZoneInfo('Europe/Moscow'))
        open_at_utc = open_at_msk.astimezone(timezone.utc)
        
        if datetime.now(timezone.utc) < open_at_utc:
            flash(f'Тест станет доступен {open_at_msk.strftime("%d.%m.%Y в %H:%M")} (МСК)', 'info')
            return redirect(url_for('courses.detail', course_id=test.course_id))
            # =====================================
    questions = db.session.query(Question).filter_by(test_id=test_id) \
        .order_by(Question.id).all()

    if not questions:
        flash('В этом тесте пока нет вопросов', 'warning')
        return redirect(url_for('courses.detail', course_id=test.course_id))

    user = db.session.get(User, session['user_id'])
    
    # Получаем все материалы курса для определения позиции теста
    from utils import get_course_materials
    all_materials = get_course_materials(test.course_id)
    
    # Находим позицию текущего теста
    current_position = 0
    for i, mat in enumerate(all_materials):
        if mat['type'] == 'test' and mat['id'] == test_id:
            current_position = i + 1
            break
    
    # Проверка количества попыток
    if test.max_attempts > 0:
        user_attempts = db.session.query(TestResult).filter_by(
            student_id=user.id,
            test_id=test_id
        ).count()
        
        if user_attempts >= test.max_attempts:
            flash(f'Вы исчерпали все попытки прохождения этого теста. Максимум попыток: {test.max_attempts}', 'error')
            return redirect(url_for('courses.detail', course_id=test.course_id))
        
        remaining_attempts = test.max_attempts - user_attempts
    else:
        remaining_attempts = None  # Неограниченно

    if request.method == 'POST':
        try:
            # Собираем ответы
            answers = {}
            for key, value in request.form.items():
                if key.startswith('question_'):
                    question_id = key.replace('question_', '')
                    answers[question_id] = int(value)

            # Подсчитываем результат
            score = 0
            total = len(questions)

            for question in questions:
                user_answer = answers.get(str(question.id))
                if user_answer and user_answer == question.correct_answer:
                    score += 1

            # Сохраняем результат
            result = TestResult(
                student_id=session['user_id'],
                test_id=test_id,
                score=score,
                total=total
            )

            db.session.add(result)
            db.session.commit()

            logger.info(
                f"[TESTS] 📝 Тест пройден: test_id={test_id}, user_id={session['user_id']}, score={score}/{total}")

            # Перенаправляем на страницу результатов
            return redirect(url_for('tests.result', result_id=result.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[TESTS] ❌ Ошибка сохранения результата: {e}")
            flash('Ошибка при сохранении результата теста', 'error')

    return render_template('tests/take.html', 
                         test=test, 
                         questions=questions,
                         remaining_attempts=remaining_attempts,
                         current_position=current_position,
                         total_materials=len(all_materials))


@tests_bp.route('/results/<int:result_id>')
@login_required
def result(result_id):
    """
    Просмотр результата теста
    """
    try:
        result = db.session.get(TestResult, result_id)

        if not result:
            flash('Результат не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Проверка прав: студент видит свой результат, преподаватель/админ - все
        if result.student_id != user.id and \
                result.test.course.creator_id != user.id and \
                user.role != 'admin':
            flash('У вас нет доступа к этому результату', 'error')
            return redirect(url_for('courses.list'))

        # Расчет процента
        percent = int((result.score / result.total * 100)) if result.total > 0 else 0

        # Определяем оценку
        if percent >= 90:
            grade = 'Отлично'
            grade_class = 'success'
        elif percent >= 75:
            grade = 'Хорошо'
            grade_class = 'info'
        elif percent >= 60:
            grade = 'Удовлетворительно'
            grade_class = 'warning'
        else:
            grade = 'Неудовлетворительно'
            grade_class = 'danger'

        return render_template('tests/result.html',
                               result=result,
                               percent=percent,
                               grade=grade,
                               grade_class=grade_class)

    except Exception as e:
        logger.error(f"[TESTS] ❌ Ошибка загрузки результата: {e}")
        flash('Ошибка загрузки результата', 'error')
        return redirect(url_for('courses.list'))


@tests_bp.route('/<int:test_id>/results')
@login_required
def all_results(test_id):
    """
    Список всех результатов теста (для преподавателя/админа)
    """
    try:
        test = db.session.get(Test, test_id)

        if not test:
            flash('Тест не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Проверка прав
        if test.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет доступа к результатам этого теста', 'error')
            return redirect(url_for('courses.detail', course_id=test.course_id))

        # Получаем все результаты
        results = db.session.query(TestResult, User) \
            .join(User, TestResult.student_id == User.id) \
            .filter(TestResult.test_id == test_id) \
            .order_by(TestResult.created_at.desc()).all()

        # Добавляем проценты
        results_data = []
        for result, student in results:
            percent = int((result.score / result.total * 100)) if result.total > 0 else 0
            results_data.append({
                'result': result,
                'student': student,
                'percent': percent
            })

        # Статистика
        total_attempts = len(results_data)
        avg_score = sum(r['percent'] for r in results_data) / total_attempts if total_attempts > 0 else 0

        stats = {
            'total_attempts': total_attempts,
            'avg_score': int(avg_score),
            'max_score': max((r['percent'] for r in results_data), default=0),
            'min_score': min((r['percent'] for r in results_data), default=0)
        }

        return render_template('tests/all_results.html',
                               test=test,
                               results_data=results_data,
                               stats=stats)

    except Exception as e:
        logger.error(f"[TESTS] ❌ Ошибка загрузки результатов: {e}")
        flash('Ошибка загрузки результатов', 'error')
        return redirect(url_for('courses.list'))


@tests_bp.route('/my-results')
@login_required
def my_results():
    """
    Все результаты тестов текущего пользователя
    """
    try:
        user = db.session.get(User, session['user_id'])

        # Получаем результаты с информацией о тестах и курсах
        results = db.session.query(TestResult, Test, Course) \
            .join(Test, TestResult.test_id == Test.id) \
            .join(Course, Test.course_id == Course.id) \
            .filter(TestResult.student_id == user.id) \
            .order_by(TestResult.created_at.desc()).all()

        # Добавляем проценты
        results_data = []
        for result, test, course in results:
            percent = int((result.score / result.total * 100)) if result.total > 0 else 0
            results_data.append({
                'result': result,
                'test': test,
                'course': course,
                'percent': percent
            })

        # Статистика
        total_tests = len(results_data)
        avg_score = sum(r['percent'] for r in results_data) / total_tests if total_tests > 0 else 0

        stats = {
            'total_tests': total_tests,
            'avg_score': int(avg_score)
        }

        return render_template('tests/my_results.html',
                               results_data=results_data,
                               stats=stats)

    except Exception as e:
        logger.error(f"[TESTS] ❌ Ошибка загрузки моих результатов: {e}")
        flash('Ошибка загрузки результатов', 'error')
        return redirect(url_for('courses.list'))


@tests_bp.route('/results/<int:result_id>/delete', methods=['POST'])
@login_required
def delete_result(result_id):
    """
    Удаление результата теста (только для преподавателя/админа)
    """
    try:
        result = db.session.get(TestResult, result_id)

        if not result:
            flash('Результат не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])
        test_id = result.test_id

        # Проверка прав
        if result.test.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для удаления этого результата', 'error')
            return redirect(url_for('tests.all_results', test_id=test_id))

        db.session.delete(result)
        db.session.commit()

        logger.info(f"[TESTS] 🗑️ Результат удален (result_id={result_id})")
        flash('Результат успешно удален', 'success')

        return redirect(url_for('tests.all_results', test_id=test_id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"[TESTS] ❌ Ошибка удаления результата: {e}")
        flash('Ошибка при удалении результата', 'error')
        return redirect(url_for('courses.list'))