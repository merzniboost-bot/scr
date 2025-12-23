# routes/lessons.py
"""
Маршруты уроков: просмотр, создание, редактирование, удаление, прогресс
"""
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, abort, send_from_directory
from models import db, Lesson, Course, UserProgress, User
from decorators import login_required, course_owner_required
from utils import (
    save_file,
    delete_file,
    allowed_video_file,
    allowed_file,
    get_course_progress,
    get_lesson_progress_map,
    is_external_link,
    get_video_embed_url,
    markdown_to_html,
)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import UPLOAD_DIR
import pathlib
from werkzeug.utils import secure_filename
import logging

logger = logging.getLogger(__name__)

lessons_bp = Blueprint('lessons', __name__)


@lessons_bp.route('/<int:lesson_id>')
@login_required
def detail(lesson_id):
    """
    Просмотр урока
    """
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

                # === НОВОЕ: проверка даты открытия ===
        if lesson.open_at:
        # Введённое время — в МСК, приводим к UTC для сравнения
            open_at_msk = lesson.open_at.replace(tzinfo=ZoneInfo('Europe/Moscow'))
            open_at_utc = open_at_msk.astimezone(timezone.utc)
    
            if datetime.now(timezone.utc) < open_at_utc:
                flash(f'Урок станет доступен {open_at_msk.strftime("%d.%m.%Y в %H:%M")} (МСК)', 'info')
                return redirect(url_for('courses.detail', course_id=lesson.course_id))
    # Если время наступило — доступ открыт
    # Если время уже наступило или прошло — продолжаем показ урока
        # =====================================

        user = db.session.get(User, session['user_id'])

        # Проверяем, завершен ли урок
        progress = db.session.query(UserProgress).filter_by(
            user_id=user.id,
            lesson_id=lesson_id
        ).first()

        is_completed = progress and progress.completed

        # Проверяем права на редактирование
        can_edit = (user.role == 'admin' or lesson.course.creator_id == user.id)

        # Получаем все материалы курса для навигации
        from utils import get_course_materials
        all_materials = get_course_materials(lesson.course_id)
        
        # Находим текущую позицию и следующий материал
        current_position = 0
        next_lesson = None
        prev_lesson = None
        
        for i, mat in enumerate(all_materials):
            if mat['type'] == 'lesson' and mat['id'] == lesson.id:
                current_position = i + 1
                # Следующий урок (не тест!)
                for j in range(i + 1, len(all_materials)):
                    if all_materials[j]['type'] == 'lesson':
                        next_lesson = all_materials[j]['obj']
                        break
                # Предыдущий урок
                for j in range(i - 1, -1, -1):
                    if all_materials[j]['type'] == 'lesson':
                        prev_lesson = all_materials[j]['obj']
                        break
                break

        # Получаем прогресс по курсу
        course_progress = get_course_progress(user.id, lesson.course_id) if user else None
        lesson_progress_map = get_lesson_progress_map(user.id, lesson.course_id) if user else {}
        video_is_link = is_external_link(lesson.video_filename)
        file_is_link = is_external_link(lesson.file_filename)
        video_embed_url = get_video_embed_url(lesson.video_filename) if video_is_link else None
        content_rendered = markdown_to_html(lesson.content)

        return render_template('lessons/detail.html',
                               lesson=lesson,
                               is_completed=is_completed,
                               can_edit=can_edit,
                               next_lesson=next_lesson,
                               prev_lesson=prev_lesson,
                               lesson_progress=lesson_progress_map,
                               course_progress=course_progress,
                               video_is_link=video_is_link,
                               file_is_link=file_is_link,
                               video_embed_url=video_embed_url,
                               content_rendered=content_rendered,
                               current_position=current_position,
                               total_materials=len(all_materials))

    except Exception as e:
        logger.error(f"[LESSONS] ❌ Ошибка загрузки урока: {e}")
        flash('Ошибка загрузки урока', 'error')
        return redirect(url_for('courses.list'))


@lessons_bp.route('/course/<int:course_id>/add', methods=['GET', 'POST'])
@course_owner_required
def add(course_id):
    """
    Добавление нового урока в курс
    """
    course = db.session.get(Course, course_id)

    if not course:
        flash('Курс не найден', 'error')
        return redirect(url_for('courses.list'))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            order = int(request.form.get('order', 0))
            video_link = request.form.get('video_link', '').strip()
            file_link = request.form.get('file_link', '').strip()

                        # === НОВОЕ: дата открытия урока ===
            open_at_str = request.form.get('open_at')
            open_at = None
            if open_at_str:
                try:
                    open_at = datetime.strptime(open_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Неверный формат даты и времени открытия урока', 'warning')
            # ==================================

            # Валидация
            if not title:
                flash('Введите название урока', 'error')
                return render_template('lessons/add.html',
                                       course=course,
                                       next_order=len(course.lessons) + 1,
                                       form_data=request.form)

            if len(title) < 3:
                flash('Название урока должно содержать минимум 3 символа', 'error')
                return render_template('lessons/add.html',
                                       course=course,
                                       next_order=len(course.lessons) + 1,
                                       form_data=request.form)

            # Обработка видео
            video_filename = None
            if video_link:
                if is_external_link(video_link):
                    video_filename = video_link
                else:
                    flash('Введите корректную ссылку на видео (https://...)', 'warning')
            elif 'video' in request.files:
                video = request.files['video']
                if video and video.filename:
                    if allowed_video_file(video.filename):
                        video_filename = save_file(video, prefix='video')
                        logger.info(f"[LESSONS] 📹 Видео загружено: {video_filename}")
                    else:
                        flash('Неподдерживаемый формат видео', 'warning')

            # Обработка файла
            file_filename = None
            if file_link:
                if is_external_link(file_link):
                    file_filename = file_link
                else:
                    flash('Введите корректную ссылку на материал (https://...)', 'warning')
            elif 'file' in request.files:
                file = request.files['file']
                if file and file.filename:
                    if allowed_file(file.filename):
                        file_filename = save_file(file, prefix='file')
                        logger.info(f"[LESSONS] 📎 Файл загружен: {file_filename}")
                    else:
                        flash('Неподдерживаемый формат файла', 'warning')

            # Создание урока
            lesson = Lesson(
                course_id=course_id,
                title=title,
                content=content,
                order=order if order > 0 else len(course.lessons) + 1,
                video_filename=video_filename,
                file_filename=file_filename,
                open_at=open_at
            )

            db.session.add(lesson)

            # Обновляем время изменения курса
            course.updated_at = datetime.utcnow()

            db.session.commit()
            
            # Инвалидируем кэш материалов курса
            from utils import invalidate_course_cache
            invalidate_course_cache(course_id)

            logger.info(f"[LESSONS] ✅ Урок создан: {title} (ID={lesson.id}, course_id={course_id})")
            flash(f'Урок "{title}" успешно добавлен', 'success')

            return redirect(url_for('courses.detail', course_id=course_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[LESSONS] ❌ Ошибка создания урока: {e}")
            flash('Ошибка при создании урока', 'error')

    # GET запрос - показываем форму
    next_order = len(course.lessons) + 1
    return render_template('lessons/add.html', course=course, next_order=next_order)


@lessons_bp.route('/<int:lesson_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lesson_id):
    """
    Редактирование урока
    """
    lesson = db.session.get(Lesson, lesson_id)

    if not lesson:
        flash('Урок не найден', 'error')
        return redirect(url_for('courses.list'))

    user = db.session.get(User, session['user_id'])

    # Проверка прав
    if lesson.course.creator_id != user.id and user.role != 'admin':
        flash('У вас нет прав для редактирования этого урока', 'error')
        return redirect(url_for('lessons.detail', lesson_id=lesson_id))

    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            order = int(request.form.get('order', lesson.order))
            video_link = request.form.get('video_link', '').strip()

                        # === НОВОЕ: дата открытия урока ===
            open_at_str = request.form.get('open_at')
            if open_at_str:
                try:
                    lesson.open_at = datetime.strptime(open_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Неверный формат даты и времени открытия урока', 'warning')
            else:
                lesson.open_at = None
            # ==================================

            file_link = request.form.get('file_link', '').strip()

            # Валидация
            if not title:
                flash('Введите название урока', 'error')
                video_is_link = is_external_link(lesson.video_filename)
                file_is_link = is_external_link(lesson.file_filename)
                return render_template('lessons/edit.html', lesson=lesson, video_is_link=video_is_link, file_is_link=file_is_link)

            if len(title) < 3:
                flash('Название урока должно содержать минимум 3 символа', 'error')
                video_is_link = is_external_link(lesson.video_filename)
                file_is_link = is_external_link(lesson.file_filename)
                return render_template('lessons/edit.html', lesson=lesson, video_is_link=video_is_link, file_is_link=file_is_link)

            # Обработка видео
            if video_link:
                if is_external_link(video_link):
                    # удаляем старый локальный файл, если был
                    if lesson.video_filename and not is_external_link(lesson.video_filename):
                        delete_file(lesson.video_filename)
                    lesson.video_filename = video_link
                else:
                    flash('Введите корректную ссылку на видео (https://...)', 'warning')
            elif 'video' in request.files:
                video = request.files['video']
                if video and video.filename:
                    if allowed_video_file(video.filename):
                        # Удаляем старое видео
                        if lesson.video_filename and not is_external_link(lesson.video_filename):
                            delete_file(lesson.video_filename)

                        lesson.video_filename = save_file(video, prefix='video')
                        logger.info(f"[LESSONS] 📹 Видео обновлено: {lesson.video_filename}")
                    else:
                        flash('Неподдерживаемый формат видео', 'warning')

            # Удаление видео
            if request.form.get('delete_video') == 'true' and lesson.video_filename:
                if not is_external_link(lesson.video_filename):
                    delete_file(lesson.video_filename)
                lesson.video_filename = None
                logger.info(f"[LESSONS] 🗑️ Видео удалено из урока {lesson_id}")

            # Обработка файла
            if file_link:
                if is_external_link(file_link):
                    if lesson.file_filename and not is_external_link(lesson.file_filename):
                        delete_file(lesson.file_filename)
                    lesson.file_filename = file_link
                else:
                    flash('Введите корректную ссылку на материал (https://...)', 'warning')
            elif 'file' in request.files:
                file = request.files['file']
                if file and file.filename:
                    if allowed_file(file.filename):
                        # Удаляем старый файл
                        if lesson.file_filename and not is_external_link(lesson.file_filename):
                            delete_file(lesson.file_filename)

                        lesson.file_filename = save_file(file, prefix='file')
                        logger.info(f"[LESSONS] 📎 Файл обновлен: {lesson.file_filename}")
                    else:
                        flash('Неподдерживаемый формат файла', 'warning')

            # Удаление файла
            if request.form.get('delete_file') == 'true' and lesson.file_filename:
                if not is_external_link(lesson.file_filename):
                    delete_file(lesson.file_filename)
                lesson.file_filename = None
                logger.info(f"[LESSONS] 🗑️ Файл удален из урока {lesson_id}")

            # Обновление данных
            lesson.title = title
            lesson.content = content
            lesson.order = order
            lesson.updated_at = datetime.utcnow()

            # Обновляем время изменения курса
            lesson.course.updated_at = datetime.utcnow()

            db.session.commit()
            
            # Инвалидируем кэш материалов курса
            from utils import invalidate_course_cache
            invalidate_course_cache(lesson.course_id)

            logger.info(f"[LESSONS] ✏️ Урок отредактирован: {title} (ID={lesson_id})")
            flash(f'Урок "{title}" успешно обновлен', 'success')

            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        except Exception as e:
            db.session.rollback()
            logger.error(f"[LESSONS] ❌ Ошибка редактирования урока: {e}")
            flash('Ошибка при редактировании урока', 'error')

    return render_template('lessons/edit.html', lesson=lesson)


@lessons_bp.route('/<int:lesson_id>/delete', methods=['POST'])
@login_required
def delete(lesson_id):
    """Удаление урока"""
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])
        course_id = lesson.course_id

        # Проверка прав
        if lesson.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для удаления этого урока', 'error')
            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        title = lesson.title

        # Удаляем файлы
        if lesson.video_filename:
            delete_file(lesson.video_filename)

        if lesson.file_filename:
            delete_file(lesson.file_filename)

        # Удаляем урок (каскадное удаление прогресса)
        db.session.delete(lesson)

        # Обновляем время изменения курса
        lesson.course.updated_at = datetime.utcnow()

        db.session.commit()
        
        # Инвалидируем кэш материалов курса
        from utils import invalidate_course_cache
        invalidate_course_cache(course_id)

        logger.info(f"[LESSONS] 🗑️ Урок удален: {title} (ID={lesson_id})")
        flash(f'Урок "{title}" успешно удален', 'success')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[LESSONS] ❌ Ошибка удаления урока: {e}")
        flash('Ошибка при удалении урока', 'error')
        course_id = lesson.course_id if 'lesson' in locals() and lesson else None

    if course_id:
        return redirect(url_for('courses.detail', course_id=course_id))
    else:
        return redirect(url_for('courses.list'))


@lessons_bp.route('/<int:lesson_id>/complete', methods=['POST'])
@login_required
def mark_complete(lesson_id):
    """Отметить урок как завершенный и перейти к следующему уроку/курсу."""
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

        user_id = session['user_id']

        # Проверяем существующий прогресс
        progress = db.session.query(UserProgress).filter_by(
            user_id=user_id,
            lesson_id=lesson_id
        ).first()

        if not progress:
            # Создаем новую запись
            progress = UserProgress(
                user_id=user_id,
                course_id=lesson.course_id,
                lesson_id=lesson_id,
                completed=True,
                completed_at=datetime.utcnow()
            )
            db.session.add(progress)
            logger.info(f"[PROGRESS] ✅ Урок {lesson_id} завершен пользователем {user_id}")
        else:
            # Обновляем существующую
            if not progress.completed:
                progress.completed = True
                progress.completed_at = datetime.utcnow()
                logger.info(f"[PROGRESS] ✅ Урок {lesson_id} отмечен завершенным пользователем {user_id}")
            else:
                flash('Этот урок уже отмечен как завершенный', 'info')

        db.session.commit()
        flash(f'Урок "{lesson.title}" отмечен как завершенным!', 'success')

        # Автоматический переход: проверяем тесты и следующий урок
        from models import TestResult
        from utils import get_course_materials
        
        # Получаем все материалы курса (уроки + тесты), отсортированные по order
        materials = get_course_materials(lesson.course_id)
        
        # Находим текущий урок в списке
        current_index = None
        for i, mat in enumerate(materials):
            if mat['type'] == 'lesson' and mat['id'] == lesson.id:
                current_index = i
                break
        
        # Ищем следующий непройденный элемент
        if current_index is not None and current_index + 1 < len(materials):
            next_material = materials[current_index + 1]
            
            if next_material['type'] == 'lesson':
                return redirect(url_for('lessons.detail', lesson_id=next_material['id']))
            elif next_material['type'] == 'test':
                # Проверяем, пройден ли тест
                test_passed = db.session.query(TestResult).filter_by(
                    student_id=user_id,
                    test_id=next_material['id']
                ).first()
                
                if not test_passed:
                    # Перенаправляем на тест
                    flash('Пройдите тест перед переходом к следующему уроку', 'info')
                    return redirect(url_for('tests.take', test_id=next_material['id']))
                else:
                    # Тест уже пройден, ищем следующий материал
                    if current_index + 2 < len(materials):
                        next_next = materials[current_index + 2]
                        if next_next['type'] == 'lesson':
                            return redirect(url_for('lessons.detail', lesson_id=next_next['id']))
                        else:
                            return redirect(url_for('courses.detail', course_id=lesson.course_id))
        
        # Если следующего материала нет, возвращаемся к курсу
        return redirect(url_for('courses.detail', course_id=lesson.course_id))

    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROGRESS] ❌ Ошибка отметки урока: {e}")
        flash('Ошибка при обновлении прогресса', 'error')

        return redirect(request.referrer or url_for('lessons.detail', lesson_id=lesson_id))


@lessons_bp.route('/<int:lesson_id>/uncomplete', methods=['POST'])
@login_required
def mark_uncomplete(lesson_id):
    """Снять отметку о завершении урока."""
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

        user_id = session['user_id']

        # Проверяем существующий прогресс
        progress = db.session.query(UserProgress).filter_by(
            user_id=user_id,
            lesson_id=lesson_id
        ).first()

        if progress and progress.completed:
            progress.completed = False
            progress.completed_at = None
            db.session.commit()

            logger.info(f"[PROGRESS] ↩️ Отметка о завершении снята: урок {lesson_id}, пользователь {user_id}")
            flash(f'Отметка о завершении урока "{lesson.title}" снята', 'info')
        else:
            flash('Этот урок не был отмечен как завершенный', 'info')

    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROGRESS] ❌ Ошибка снятия отметки: {e}")
        flash('Ошибка при обновлении прогресса', 'error')

    return redirect(request.referrer or url_for('lessons.detail', lesson_id=lesson_id))


@lessons_bp.route('/<int:lesson_id>/statistics')
@login_required
def statistics(lesson_id):
    """Статистика урока: сколько студентов прошли, когда и т.д."""
    try:
        lesson = db.session.get(Lesson, lesson_id)
        
        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))
        
        user = db.session.get(User, session['user_id'])
        
        # Проверка прав
        if lesson.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для просмотра статистики', 'error')
            return redirect(url_for('lessons.detail', lesson_id=lesson_id))
        
        # Получаем статистику прогресса
        from sqlalchemy import func
        
        # Всего студентов, начавших курс
        total_students = db.session.query(func.count(func.distinct(UserProgress.user_id))).filter(
            UserProgress.course_id == lesson.course_id
        ).scalar() or 0
        
        # Студенты, завершившие урок
        completed_query = db.session.query(UserProgress).filter(
            UserProgress.lesson_id == lesson_id,
            UserProgress.completed == True
        ).all()
        
        completed_count = len(completed_query)
        completion_rate = (completed_count / total_students * 100) if total_students > 0 else 0
        
        # Детали по студентам
        students_progress = []
        for progress in completed_query:
            student = db.session.get(User, progress.user_id)
            if student:
                students_progress.append({
                    'user': student,
                    'completed_at': progress.completed_at,
                    'progress': progress
                })
        
        # Сортируем по дате завершения (новые первые)
        students_progress.sort(key=lambda x: x['completed_at'] or datetime.min, reverse=True)
        
        return render_template('lessons/statistics.html',
                             lesson=lesson,
                             total_students=total_students,
                             completed_count=completed_count,
                             completion_rate=round(completion_rate, 1),
                             students_progress=students_progress)
        
    except Exception as e:
        logger.error(f"[LESSONS] ❌ Ошибка загрузки статистики: {e}")
        flash('Ошибка загрузки статистики', 'error')
        return redirect(url_for('lessons.detail', lesson_id=lesson_id))


@lessons_bp.route('/<int:lesson_id>/reorder', methods=['POST'])
@login_required
def reorder(lesson_id):
    """
    Изменение порядка урока
    """
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

        user = db.session.get(User, session['user_id'])

        # Проверка прав
        if lesson.course.creator_id != user.id and user.role != 'admin':
            flash('У вас нет прав для изменения порядка уроков', 'error')
            return redirect(url_for('courses.detail', course_id=lesson.course_id))

        direction = request.form.get('direction')  # 'up' или 'down'

        if direction == 'up':
            # Найти урок с предыдущим порядком
            prev_lesson = db.session.query(Lesson).filter(
                Lesson.course_id == lesson.course_id,
                Lesson.order < lesson.order
            ).order_by(Lesson.order.desc()).first()

            if prev_lesson:
                # Меняем местами
                lesson.order, prev_lesson.order = prev_lesson.order, lesson.order
                db.session.commit()
                flash('Порядок урока изменен', 'success')
            else:
                flash('Урок уже первый в списке', 'info')

        elif direction == 'down':
            # Найти урок со следующим порядком
            next_lesson = db.session.query(Lesson).filter(
                Lesson.course_id == lesson.course_id,
                Lesson.order > lesson.order
            ).order_by(Lesson.order).first()

            if next_lesson:
                # Меняем местами
                lesson.order, next_lesson.order = next_lesson.order, lesson.order
                db.session.commit()
                flash('Порядок урока изменен', 'success')
            else:
                flash('Урок уже последний в списке', 'info')

        logger.info(f"[LESSONS] 🔄 Порядок урока изменен: {lesson_id} ({direction})")

    except Exception as e:
        db.session.rollback()
        logger.error(f"[LESSONS] ❌ Ошибка изменения порядка: {e}")
        flash('Ошибка при изменении порядка урока', 'error')

    return redirect(url_for('courses.detail', course_id=lesson.course_id))


@lessons_bp.route('/upload/<path:filename>')
@login_required
def serve_file(filename):
    """
    Отдача загруженных файлов (видео, документы)
    """
    try:
        # Безопасность: проверяем путь
        safe_path = pathlib.Path(secure_filename(filename))

        if '..' in str(safe_path) or str(safe_path).startswith('/'):
            logger.warning(f"[SECURITY] ⚠️ Попытка доступа к небезопасному пути: {filename}")
            abort(403)

        file_path = UPLOAD_DIR / safe_path

        if not file_path.exists():
            logger.warning(f"[404] Файл не найден: {filename}")
            abort(404)

        # Проверяем, что файл находится в UPLOAD_DIR
        if not file_path.is_relative_to(UPLOAD_DIR):
            logger.warning(f"[SECURITY] ⚠️ Попытка доступа к файлу вне uploads: {filename}")
            abort(403)

        return send_from_directory(UPLOAD_DIR, str(safe_path))

    except Exception as e:
        logger.error(f"[LESSONS] ❌ Ошибка отдачи файла: {e}")
        abort(404)


@lessons_bp.route('/<int:lesson_id>/download/<file_type>')
@login_required
def download_file(lesson_id, file_type):
    """
    Скачивание файла урока

    file_type: 'video' или 'file'
    """
    try:
        lesson = db.session.get(Lesson, lesson_id)

        if not lesson:
            flash('Урок не найден', 'error')
            return redirect(url_for('courses.list'))

        if file_type == 'video' and lesson.video_filename:
            filename = lesson.video_filename
        elif file_type == 'file' and lesson.file_filename:
            filename = lesson.file_filename
        else:
            flash('Файл не найден', 'error')
            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        file_path = UPLOAD_DIR / filename

        if not file_path.exists():
            flash('Файл не найден на сервере', 'error')
            return redirect(url_for('lessons.detail', lesson_id=lesson_id))

        logger.info(f"[DOWNLOAD] 📥 Файл скачан: {filename} пользователем {session['user_id']}")

        return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)

    except Exception as e:
        logger.error(f"[LESSONS] ❌ Ошибка скачивания файла: {e}")
        flash('Ошибка при скачивании файла', 'error')
        return redirect(url_for('lessons.detail', lesson_id=lesson_id))