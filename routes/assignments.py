# routes/assignments.py
"""
Маршруты заданий: создание, просмотр, загрузка работ, проверка
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, send_from_directory, abort, Response
from models import db, Assignment, Submission, Lesson, Course, User, Group, now_msk
from decorators import login_required, course_owner_required
from utils import save_file, delete_file
from datetime import datetime, timezone
from config import UPLOAD_DIR
from werkzeug.utils import secure_filename
import pathlib
import os
import logging
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

assignments_bp = Blueprint('assignments', __name__)

MSK = ZoneInfo('Europe/Moscow')
UTC = ZoneInfo('UTC')


def allowed_submission_file(filename, allowed_extensions):
    """Проверка расширения файла для задания"""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions


def get_file_size_mb(file):
    """Получить размер файла в МБ"""
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size / (1024 * 1024)


# ==================== СОЗДАНИЕ/РЕДАКТИРОВАНИЕ ЗАДАНИЯ ====================

@assignments_bp.route('/lesson/<int:lesson_id>/create', methods=['GET', 'POST'])
@login_required
def create(lesson_id):
    """Создание задания для урока"""
    lesson = db.session.get(Lesson, lesson_id)

    if not lesson:
        flash('Урок не найден', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])

    # Проверка прав
    if lesson.course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для создания задания', 'error')
        return redirect(url_for('lessons.detail', lesson_id=lesson_id))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            deadline_str = request.form.get('deadline', '').strip()
            max_file_size = int(request.form.get('max_file_size', 10))
            allowed_extensions = request.form.get('allowed_extensions', 'pdf,doc,docx,txt,zip').strip()
            is_required = request.form.get('is_required') == 'on'

            # Валидация
            if not title:
                flash('Введите название задания', 'error')
                return render_template('assignments/create.html', lesson=lesson)

            # Парсинг дедлайна
            deadline = None
            if deadline_str:
                try:
                    # Парсим как naive
                    naive_deadline = datetime.fromisoformat(deadline_str)
                    # Присваиваем MSK tz (т.к. форма в локальном времени)
                    msk_deadline = naive_deadline.replace(tzinfo=MSK)
                    # Конвертируем в UTC и делаем naive (для хранения)
                    deadline = msk_deadline.astimezone(UTC).replace(tzinfo=None)
                except ValueError:
                    flash('Неверный формат даты дедлайна', 'error')
                    return render_template('assignments/create.html', lesson=lesson)

            # Создаем задание
            assignment = Assignment(
                lesson_id=lesson_id,
                title=title,
                description=description,
                deadline=deadline,
                max_file_size_mb=max_file_size,
                allowed_extensions=allowed_extensions.lower(),
                is_required=is_required
            )

            db.session.add(assignment)
            db.session.commit()

            logger.info(f"[ASSIGNMENTS] ✅ Задание создано: {title} (ID={assignment.id})")
            flash(f'Задание "{title}" успешно создано!', 'success')

            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[ASSIGNMENTS] ❌ Ошибка создания задания: {e}")
            flash('Ошибка при создании задания', 'error')

    return render_template('assignments/create.html', lesson=lesson)


@assignments_bp.route('/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(assignment_id):
    """Редактирование задания"""
    assignment = db.session.get(Assignment, assignment_id)

    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])
    lesson = assignment.lesson

    # Проверка прав
    if lesson.course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для редактирования задания', 'error')
        return redirect(url_for('lessons.detail', lesson_id=lesson.id))

    if request.method == 'GET':
        return render_template('assignments/edit.html', 
                            assignment=assignment,
                            utc=UTC,
                            msk=MSK)
    
    if request.method == 'POST':
        try:
            assignment.title = request.form.get('title', '').strip()
            assignment.description = request.form.get('description', '').strip()
            deadline_str = request.form.get('deadline', '').strip()
            assignment.max_file_size_mb = int(request.form.get('max_file_size', 10))
            assignment.allowed_extensions = request.form.get('allowed_extensions',
                                                             'pdf,doc,docx,txt,zip').strip().lower()
            assignment.is_required = request.form.get('is_required') == 'on'

            # Валидация
            if not assignment.title:
                flash('Введите название задания', 'error')
                return render_template('assignments/edit.html', assignment=assignment)

            # Парсинг дедлайна
            if deadline_str:
                try:
                    # Парсим как naive
                    naive_deadline = datetime.fromisoformat(deadline_str)
                    # Присваиваем MSK tz (т.к. форма в локальном времени)
                    msk_deadline = naive_deadline.replace(tzinfo=MSK)
                    # Конвертируем в UTC и делаем naive (для хранения)
                    deadline = msk_deadline.astimezone(UTC).replace(tzinfo=None)
                except ValueError:
                    flash('Неверный формат даты дедлайна', 'error')
                    return render_template('assignments/create.html', lesson=lesson)
            else:
                assignment.deadline = None

            db.session.commit()

            logger.info(f"[ASSIGNMENTS] ✏️ Задание отредактировано: {assignment.title}")
            flash('Задание успешно обновлено', 'success')

            return redirect(url_for('lessons.detail', lesson_id=lesson.id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[ASSIGNMENTS] ❌ Ошибка редактирования: {e}")
            flash('Ошибка при редактировании задания', 'error')

    return render_template('assignments/edit.html', assignment=assignment)


@assignments_bp.route('/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete(assignment_id):
    """Удаление задания"""
    try:
        assignment = db.session.get(Assignment, assignment_id)

        if not assignment:
            flash('Задание не найдено', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])
        lesson_id = assignment.lesson_id

        # Проверка прав
        if assignment.lesson.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для удаления задания', 'error')
            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        title = assignment.title

        # Удаляем файлы всех сданных работ
        for submission in assignment.submissions:
            if submission.file_filename:
                delete_file(submission.file_filename)

        db.session.delete(assignment)
        db.session.commit()

        logger.info(f"[ASSIGNMENTS] 🗑️ Задание удалено: {title}")
        flash(f'Задание "{title}" удалено', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[ASSIGNMENTS] ❌ Ошибка удаления: {e}")
        flash('Ошибка при удалении задания', 'error')

    return redirect(url_for('lessons.detail', lesson_id=lesson_id))


# ==================== ЗАГРУЗКА РАБОТЫ СТУДЕНТОМ ====================

@assignments_bp.route('/<int:assignment_id>/submit', methods=['GET', 'POST'])
@login_required
def submit(assignment_id):
    """Страница загрузки работы студентом"""
    assignment = db.session.get(Assignment, assignment_id)

    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])

    # Проверяем, есть ли уже сданная работа
    existing_submission = Submission.query.filter_by(
        assignment_id=assignment_id,
        student_id=user.id
    ).first()

    if request.method == 'POST':
        try:
            # Проверка файла
            if 'file' not in request.files:
                flash('Выберите файл для загрузки', 'error')
                return render_template('assignments/submit.html',
                                       assignment=assignment,
                                       submission=existing_submission)

            file = request.files['file']

            if not file or not file.filename:
                flash('Выберите файл для загрузки', 'error')
                return render_template('assignments/submit.html',
                                       assignment=assignment,
                                       submission=existing_submission)

            # Проверка расширения
            allowed_ext = assignment.get_allowed_extensions_list()
            if not allowed_submission_file(file.filename, allowed_ext):
                flash(f'Разрешенные форматы: {", ".join(allowed_ext)}', 'error')
                return render_template('assignments/submit.html',
                                       assignment=assignment,
                                       submission=existing_submission)

            # Проверка размера
            file_size_mb = get_file_size_mb(file)
            if file_size_mb > assignment.max_file_size_mb:
                flash(f'Файл слишком большой. Максимум: {assignment.max_file_size_mb} МБ', 'error')
                return render_template('assignments/submit.html',
                                       assignment=assignment,
                                       submission=existing_submission)

            # Сохраняем файл
            original_filename = secure_filename(file.filename)
            saved_filename = save_file(file, prefix=f'submission_{user.id}')

            if not saved_filename:
                flash('Ошибка при сохранении файла', 'error')
                return render_template('assignments/submit.html',
                                       assignment=assignment,
                                       submission=existing_submission)

            if existing_submission:
                # Обновляем существующую работу
                # Удаляем старый файл
                if existing_submission.file_filename:
                    delete_file(existing_submission.file_filename)

                existing_submission.file_filename = saved_filename
                existing_submission.original_filename = original_filename
                existing_submission.file_size = int(file_size_mb * 1024 * 1024)
                existing_submission.submitted_at = datetime.now(lambda: datetime.utcnow())
                existing_submission.status = 'submitted'  # Сбрасываем статус
                existing_submission.grade = None
                existing_submission.feedback = None
                existing_submission.reviewed_at = None

                logger.info(f"[SUBMISSIONS] 📝 Работа обновлена: assignment={assignment_id}, student={user.id}")
                flash('Ваша работа успешно обновлена!', 'success')
            else:
                # Создаем новую работу
                submission = Submission(
                    assignment_id=assignment_id,
                    student_id=user.id,
                    file_filename=saved_filename,
                    original_filename=original_filename,
                    file_size=int(file_size_mb * 1024 * 1024),
                    status='submitted'
                )
                db.session.add(submission)

                logger.info(f"[SUBMISSIONS] ✅ Работа сдана: assignment={assignment_id}, student={user.id}")
                flash('Ваша работа успешно отправлена!', 'success')

            db.session.commit()

            return redirect(url_for('lessons.detail', lesson_id=assignment.lesson_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[SUBMISSIONS] ❌ Ошибка загрузки работы: {e}")
            flash('Ошибка при загрузке работы', 'error')

    return render_template('assignments/submit.html',
                           assignment=assignment,
                           submission=existing_submission)


@assignments_bp.route('/submission/<int:submission_id>/delete', methods=['POST'])
@login_required
def delete_submission(submission_id):
    """Удаление своей работы студентом"""
    try:
        submission = db.session.get(Submission, submission_id)

        if not submission:
            flash('Работа не найдена', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Только автор может удалить
        if submission.student_id != user.id:
            flash('Вы не можете удалить чужую работу', 'error')
            return redirect(url_for('courses.list'))

        # Нельзя удалить проверенную работу
        if submission.status in ['approved', 'reviewed']:
            flash('Нельзя удалить уже проверенную работу', 'error')
            return redirect(url_for('lessons.detail', lesson_id=submission.assignment.lesson_id))

        lesson_id = submission.assignment.lesson_id

        # Удаляем файл
        if submission.file_filename:
            delete_file(submission.file_filename)

        db.session.delete(submission)
        db.session.commit()

        flash('Ваша работа удалена', 'info')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[SUBMISSIONS] ❌ Ошибка удаления работы: {e}")
        flash('Ошибка при удалении работы', 'error')
        lesson_id = None

    if lesson_id:
        return redirect(url_for('lessons.detail', lesson_id=lesson_id))
    return redirect(url_for('courses.list'))


# ==================== СКАЧИВАНИЕ / ПРОСМОТР РАБОТ ====================

TEXT_EXTS = {'txt', 'md', 'py', 'js', 'ts', 'json', 'csv', 'html', 'css'}


@assignments_bp.route('/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    """Скачать файл работы (для автора или владельца курса/админа)."""
    submission = db.session.get(Submission, submission_id)
    if not submission:
        flash('Работа не найдена', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])
    course = submission.assignment.lesson.course

    if not (user.role == 'admin' or course.creator_id == user.id or submission.student_id == user.id):
        flash('Нет прав для скачивания', 'error')
        return redirect(url_for('courses.list'))

    filepath = UPLOAD_DIR / submission.file_filename
    if not filepath.exists():
        flash('Файл не найден', 'error')
        return redirect(url_for('courses.list'))

    return send_from_directory(directory=UPLOAD_DIR, path=submission.file_filename, as_attachment=True,
                               download_name=submission.original_filename or submission.file_filename)


@assignments_bp.route('/submission/<int:submission_id>/preview')
@login_required
def preview_submission(submission_id):
    """Предпросмотр текстовых работ в браузере (чтение файла)."""
    submission = db.session.get(Submission, submission_id)
    if not submission:
        abort(404)

    user = db.session.get(User, session['user_id'])
    course = submission.assignment.lesson.course
    if not (user.role == 'admin' or course.creator_id == user.id or submission.student_id == user.id):
        abort(403)

    filepath = UPLOAD_DIR / submission.file_filename
    if not filepath.exists():
        abort(404)

    ext = submission.file_filename.rsplit('.', 1)[-1].lower() if '.' in submission.file_filename else ''
    if ext not in TEXT_EXTS:
        # Для нетекстовых — предложим скачать
        return send_from_directory(directory=UPLOAD_DIR, path=submission.file_filename, as_attachment=True,
                                   download_name=submission.original_filename or submission.file_filename)

    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        return Response(content, mimetype='text/plain; charset=utf-8')
    except Exception:
        abort(500)


# ==================== ПРОСМОТР РАБОТ ПРЕПОДАВАТЕЛЕМ ====================

@assignments_bp.route('/<int:assignment_id>/submissions')
@login_required
def view_submissions(assignment_id):
    """Просмотр всех сданных работ по заданию (для преподавателя)"""
    assignment = db.session.get(Assignment, assignment_id)

    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])
    course = assignment.lesson.course

    # Проверка прав (только владелец курса или админ)
    if course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для просмотра работ', 'error')
        return redirect(url_for('lessons.detail', lesson_id=assignment.lesson_id))

    # Фильтры
    group_id = request.args.get('group_id', type=int)
    status_filter = request.args.get('status', '')

    # Получаем все группы для фильтра
    groups = Group.query.order_by(Group.name).all()

    # Базовый запрос сданных работ
    submissions_query = Submission.query.filter_by(assignment_id=assignment_id) \
        .join(User, Submission.student_id == User.id)

    if group_id:
        submissions_query = submissions_query.filter(User.group_id == group_id)

    if status_filter:
        submissions_query = submissions_query.filter(Submission.status == status_filter)

    submissions = submissions_query.order_by(Submission.submitted_at.desc()).all()

    # Получаем студентов, которые НЕ сдали работу
    # Сначала получаем всех студентов
    students_query = User.query.filter_by(role='student', approved=True)

    if group_id:
        students_query = students_query.filter_by(group_id=group_id)

    all_students = students_query.all()

    # ID студентов, которые сдали
    submitted_student_ids = {s.student_id for s in Submission.query.filter_by(assignment_id=assignment_id).all()}

    # Студенты, которые не сдали
    not_submitted_students = [s for s in all_students if s.id not in submitted_student_ids]

    # Статистика
    stats = {
        'total_submissions': len(submissions),
        'pending': len([s for s in submissions if s.status == 'submitted']),
        'reviewed': len([s for s in submissions if s.status in ['reviewed', 'approved', 'rejected']]),
        'not_submitted': len(not_submitted_students)
    }

    return render_template('assignments/submissions.html',
                           assignment=assignment,
                           submissions=submissions,
                           not_submitted_students=not_submitted_students,
                           groups=groups,
                           selected_group_id=group_id,
                           status_filter=status_filter,
                           stats=stats)


@assignments_bp.route('/submission/<int:submission_id>/review', methods=['POST'])
@login_required
def review_submission(submission_id):
    """Оценка работы преподавателем"""
    try:
        submission = db.session.get(Submission, submission_id)

        if not submission:
            flash('Работа не найдена', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])
        course = submission.assignment.lesson.course

        # Проверка прав
        if course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для оценки работ', 'error')
            return redirect(url_for('courses.list'))

        # Получаем данные
        grade = request.form.get('grade', type=int)
        feedback = request.form.get('feedback', '').strip()
        status = request.form.get('status', 'reviewed')

        # Валидация оценки
        if grade is not None and (grade < 0 or grade > 100):
            flash('Оценка должна быть от 0 до 100', 'error')
            return redirect(url_for('assignments.view_submissions', assignment_id=submission.assignment_id))

        submission.grade = grade
        submission.feedback = feedback
        submission.status = status
        submission.reviewed_at = now_msk()

        db.session.commit()

        logger.info(f"[SUBMISSIONS] ✓ Работа оценена: ID={submission_id}, grade={grade}, status={status}")
        flash('Работа успешно оценена', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[SUBMISSIONS] ❌ Ошибка оценки: {e}")
        flash('Ошибка при оценке работы', 'error')

    return redirect(url_for('assignments.view_submissions', assignment_id=submission.assignment_id))


# ==================== СТАТИСТИКА ПО ГРУППАМ ====================

@assignments_bp.route('/<int:assignment_id>/stats')
@login_required
def assignment_stats(assignment_id):
    """Статистика по заданию с разбивкой по группам"""
    assignment = db.session.get(Assignment, assignment_id)

    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])
    course = assignment.lesson.course

    # Проверка прав
    if course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для просмотра статистики', 'error')
        return redirect(url_for('lessons.detail', lesson_id=assignment.lesson_id))

    # Получаем все группы
    groups = Group.query.order_by(Group.name).all()

    # Статистика по группам
    groups_stats = []

    for group in groups:
        # Все студенты группы
        students_in_group = User.query.filter_by(
            role='student',
            approved=True,
            group_id=group.id
        ).count()

        if students_in_group == 0:
            continue

        # Сдавшие из группы
        submitted = db.session.query(Submission) \
            .join(User, Submission.student_id == User.id) \
            .filter(
            Submission.assignment_id == assignment_id,
            User.group_id == group.id
        ).count()

        # Проверенные
        reviewed = db.session.query(Submission) \
            .join(User, Submission.student_id == User.id) \
            .filter(
            Submission.assignment_id == assignment_id,
            User.group_id == group.id,
            Submission.status.in_(['reviewed', 'approved'])
        ).count()

        # Средняя оценка
        avg_grade = db.session.query(db.func.avg(Submission.grade)) \
            .join(User, Submission.student_id == User.id) \
            .filter(
            Submission.assignment_id == assignment_id,
            User.group_id == group.id,
            Submission.grade.isnot(None)
        ).scalar()

        groups_stats.append({
            'group': group,
            'total_students': students_in_group,
            'submitted': submitted,
            'not_submitted': students_in_group - submitted,
            'reviewed': reviewed,
            'avg_grade': round(avg_grade, 1) if avg_grade else None,
            'submission_rate': round(submitted / students_in_group * 100, 1)
        })

    # Студенты без группы
    students_no_group = User.query.filter_by(
        role='student',
        approved=True,
        group_id=None
    ).count()

    if students_no_group > 0:
        submitted_no_group = db.session.query(Submission) \
            .join(User, Submission.student_id == User.id) \
            .filter(
            Submission.assignment_id == assignment_id,
            User.group_id.is_(None)
        ).count()

        groups_stats.append({
            'group': None,
            'group_name': 'Без группы',
            'total_students': students_no_group,
            'submitted': submitted_no_group,
            'not_submitted': students_no_group - submitted_no_group,
            'reviewed': 0,
            'avg_grade': None,
            'submission_rate': round(submitted_no_group / students_no_group * 100, 1) if students_no_group else 0
        })

    return render_template('assignments/stats.html',
                           assignment=assignment,
                           groups_stats=groups_stats)