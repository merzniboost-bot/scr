# utils.py
"""
Вспомогательные функции
"""
import re
import uuid
import pathlib
import logging
import base64
from werkzeug.utils import secure_filename
from config import UPLOAD_DIR, Config
from zoneinfo import ZoneInfo
from PIL import Image, ImageOps
import io
from markupsafe import Markup, escape

logger = logging.getLogger(__name__)


def is_valid_email(email):
    """
    Валидация email адреса
    """
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None


def is_external_link(value: str) -> bool:
    """
    Быстрая проверка, что строка выглядит как внешняя ссылка
    """
    if not value:
        return False
    return value.startswith(('http://', 'https://'))


def get_video_embed_url(url: str) -> str | None:
    """
    Преобразовать ссылку на YouTube/Rutube в embed-формат
    """
    if not url:
        return None

    url = url.strip()
    try:
        # YouTube
        if 'youtu.be/' in url:
            video_id = url.rsplit('/', 1)[-1].split('?')[0]
            return f'https://www.youtube.com/embed/{video_id}'
        if 'youtube.com/watch' in url:
            match = re.search(r'v=([A-Za-z0-9_-]+)', url)
            if match:
                return f'https://www.youtube.com/embed/{match.group(1)}'
        if 'youtube.com/embed/' in url:
            return url

        # Rutube
        if 'rutube.ru/video/' in url:
            video_id = url.rsplit('/', 1)[-1].split('?')[0]
            return f'https://rutube.ru/play/embed/{video_id}'
        if 'rutube.ru/play/embed/' in url:
            return url

    except Exception as e:
        logger.warning(f"Не удалось сконструировать embed url: {e}")

    # Если не смогли распознать — вернем исходное, чтобы показать как есть
    return url


def render_mini_content(text: str | None) -> Markup:
    """
    Простейший рендер мини-разметки: **жирный**, *курсив*, __подчеркнутый__,
    списки с "- " и ссылки вида [текст](https://...)
    """
    if not text:
        return Markup("")

    escaped = escape(text)

    # Ссылки
    escaped = re.sub(
        r'\[([^\]]+)]\((https?://[^\s)]+)\)',
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        escaped
    )
    # Жирный, курсив, подчёркнутый
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', escaped)
    escaped = re.sub(r'__(.+?)__', r'<u>\1</u>', escaped)

    # Списки
    lines = escaped.split('\n')
    rendered_lines = []
    in_list = False
    for line in lines:
        if line.strip().startswith('- '):
            if not in_list:
                rendered_lines.append('<ul>')
                in_list = True
            rendered_lines.append(f"<li>{line.strip()[2:]}</li>")
        else:
            if in_list:
                rendered_lines.append('</ul>')
                in_list = False
            rendered_lines.append(line)
    if in_list:
        rendered_lines.append('</ul>')

    escaped = '\n'.join(rendered_lines)

    # Перевод строк
    escaped = escaped.replace('\n', '<br>')

    return Markup(escaped)


def allowed_video_file(filename):
    """
    Проверка расширения видео файла
    """
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in Config.ALLOWED_VIDEO_EXTENSIONS


def allowed_file(filename):
    """
    Проверка расширения обычного файла
    """
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in Config.ALLOWED_FILE_EXTENSIONS


def save_file(file, prefix='file', target_size=(400, 250)):
    """
    Сохраняет файл и для изображений делает идеальное вписывание в target_size
    Без обрезки — добавляются белые поля сверху/снизу или по бокам
    """
    if not file or not file.filename:
        return None

    filename = secure_filename(file.filename)
    if not filename:
        return None

    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    base_name = filename.rsplit('.', 1)[0]
    base_name = secure_filename(base_name) or prefix
    base_name = base_name[:40]  # ограничиваем длину
    unique_filename = f"{prefix}_{base_name}_{uuid.uuid4().hex[:8]}"

    try:
        # Только для изображений делаем магию
        if ext in {'jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'tiff'}:
            with Image.open(file.stream) as img:
                # Конвертируем в RGB (чтобы WebP работал)
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # ВПИСЫВАЕМ картинку в нужный размер БЕЗ обрезки (letterbox)
                img_resized = ImageOps.contain(img, target_size, Image.Resampling.LANCZOS)

                canvas = Image.new("RGB", target_size, (255, 255, 255))
                offset = (
                    (target_size[0] - img_resized.width) // 2,
                    (target_size[1] - img_resized.height) // 2
                )
                canvas.paste(img_resized, offset)

                # Сохраняем как WebP — лёгкий формат без обрезки
                final_path = UPLOAD_DIR / f"{unique_filename}.webp"
                canvas.save(final_path, 'WEBP', quality=85, method=6)

                logger.info(f"Превью вписано {target_size} → {unique_filename}.webp")
                return f"{unique_filename}.webp"

        # Для видео и других файлов — просто сохраняем как есть
        filepath = UPLOAD_DIR / f"{unique_filename}.{ext}"
        file.save(str(filepath))
        logger.info(f"Файл сохранен без изменений: {unique_filename}.{ext}")
        return f"{unique_filename}.{ext}"

    except Exception as e:
        logger.error(f"Ошибка обработки файла: {e}")
        return None


def save_data_url(data_url: str, prefix='file', target_size=(400, 250)):
    """
    Принимает data:image/...;base64,... и сохраняет как WebP с вписыванием без обрезки.
    """
    if not data_url or not data_url.startswith('data:image/'):
        return None
    try:
        header, b64data = data_url.split(',', 1)
        raw = base64.b64decode(b64data)
        base_name = f"{prefix}_{uuid.uuid4().hex[:8]}"
        with Image.open(io.BytesIO(raw)) as img:
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img_resized = ImageOps.contain(img, target_size, Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", target_size, (255, 255, 255))
            offset = (
                (target_size[0] - img_resized.width) // 2,
                (target_size[1] - img_resized.height) // 2
            )
            canvas.paste(img_resized, offset)

            final_path = UPLOAD_DIR / f"{base_name}.webp"
            canvas.save(final_path, 'WEBP', quality=85, method=6)
            logger.info(f"Превью из data-url {target_size} → {base_name}.webp")
            return f"{base_name}.webp"
    except Exception as e:
        logger.error(f"Ошибка обработки data-url файла: {e}")
        return None


def delete_file(filename):
    """
    Безопасное удаление файла из uploads
    """
    if not filename:
        return

    try:
        filepath = UPLOAD_DIR / filename
        if filepath.exists() and filepath.parent == UPLOAD_DIR:
            filepath.unlink()
            logger.info(f"🗑️  Файл удален: {filename}")
        else:
            logger.warning(f"⚠️  Попытка удалить файл вне uploads: {filename}")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления файла {filename}: {e}")


def get_course_progress(user_id, course_id):
    """
    Получить прогресс пользователя по курсу (уроки + тесты)
    
    Returns:
        dict: {
            'completed': int,           # Завершенных элементов всего
            'total': int,               # Всего элементов
            'percent': int,             # Процент завершения
            'is_completed': bool,       # Курс полностью завершен
            'lessons_completed': int,   # Завершенных уроков
            'lessons_total': int,       # Всего уроков
            'tests_completed': int,     # Пройденных тестов
            'tests_total': int          # Всего тестов
        }
    """
    from models import db, Lesson, Test, UserProgress, TestResult

    # === Подсчет уроков ===
    lessons_total = db.session.query(db.func.count(Lesson.id)) \
        .filter_by(course_id=course_id).scalar() or 0

    lessons_completed = db.session.query(db.func.count(UserProgress.lesson_id)) \
        .join(Lesson, UserProgress.lesson_id == Lesson.id) \
        .filter(
            UserProgress.user_id == user_id,
            Lesson.course_id == course_id,
            UserProgress.completed == True
        ).scalar() or 0

    # === Подсчет тестов ===
    try:
        tests_total = db.session.query(db.func.count(Test.id)) \
            .filter_by(course_id=course_id).scalar() or 0

        # Тест считается завершенным, если есть хотя бы один результат
        tests_completed = db.session.query(db.func.count(db.distinct(TestResult.test_id))) \
            .join(Test, TestResult.test_id == Test.id) \
            .filter(
                TestResult.student_id == user_id,
                Test.course_id == course_id
            ).scalar() or 0
    except Exception as e:
        logger.warning(f"Ошибка подсчета тестов: {e}")
        tests_total = 0
        tests_completed = 0

    # === Общий прогресс ===
    total = lessons_total + tests_total
    completed = lessons_completed + tests_completed
    percent = int((completed / total * 100)) if total > 0 else 0

    return {
        'total': total,
        'completed': completed,
        'percent': percent,
        'is_completed': completed == total and total > 0,
        'lessons_completed': lessons_completed,
        'lessons_total': lessons_total,
        'tests_completed': tests_completed,
        'tests_total': tests_total
    }


def get_test_progress_map(user_id, course_id):
    """
    Получить карту прогресса по тестам курса
    
    Returns:
        dict: {test_id: {'completed': bool, 'score': int, 'total': int, 'percent': int, 'attempts': int}}
    """
    from models import db, Test, TestResult

    progress_map = {}

    try:
        # Получаем все тесты курса
        tests = db.session.query(Test.id).filter_by(course_id=course_id).all()
        test_ids = [t[0] for t in tests]

        # Для каждого теста получаем лучший результат и количество попыток
        for test_id in test_ids:
            # Лучший результат (по проценту правильных ответов)
            best_result = db.session.query(TestResult) \
                .filter_by(student_id=user_id, test_id=test_id) \
                .order_by(TestResult.score.desc()) \
                .first()

            # Количество попыток
            attempts = db.session.query(db.func.count(TestResult.id)) \
                .filter_by(student_id=user_id, test_id=test_id) \
                .scalar() or 0

            if best_result:
                percent = int((best_result.score / best_result.total * 100)) if best_result.total > 0 else 0
                progress_map[test_id] = {
                    'completed': True,
                    'score': best_result.score,
                    'total': best_result.total,
                    'percent': percent,
                    'passed': percent >= 60,  # Считаем пройденным при 60%+
                    'attempts': attempts
                }
            else:
                progress_map[test_id] = {
                    'completed': False,
                    'score': 0,
                    'total': 0,
                    'percent': 0,
                    'passed': False,
                    'attempts': 0
                }

    except Exception as e:
        logger.warning(f"Ошибка получения прогресса тестов: {e}")

    return progress_map


def is_course_favorite(user_id, course_id):
    """
    Проверить, находится ли курс в избранном пользователя
    """
    from models import db, Favorite

    exists = db.session.query(
        db.exists().where(
            (Favorite.user_id == user_id) & (Favorite.course_id == course_id)
        )
    ).scalar()

    return exists


def get_lesson_progress_map(user_id, course_id):
    """
    Получить карту прогресса по урокам курса
    """
    from models import db, UserProgress, Lesson

    lessons = db.session.query(Lesson.id).filter_by(course_id=course_id).all()

    completed = db.session.query(UserProgress.lesson_id).filter_by(
        user_id=user_id,
        course_id=course_id,
        completed=True
    ).all()

    completed_ids = {row[0] for row in completed}
    progress_map = {lesson[0]: lesson[0] in completed_ids for lesson in lessons}

    return progress_map


def format_datetime(dt):
    """Форматирование datetime для отображения"""
    if not dt:
        return '—'
    return dt.strftime('%d.%m.%Y %H:%M')


def format_date(dt):
    """Форматирование даты без времени"""
    if not dt:
        return '—'
    return dt.strftime('%d.%m.%Y')


def get_user_statistics(user_id):
    """
    Получить общую статистику пользователя
    """
    from models import db, UserProgress, Favorite, TestResult, Course

    total_courses = db.session.query(
        db.func.count(db.distinct(UserProgress.course_id))
    ).filter_by(user_id=user_id).scalar() or 0

    total_lessons = db.session.query(
        db.func.count(UserProgress.id)
    ).filter_by(user_id=user_id).scalar() or 0

    completed_lessons = db.session.query(
        db.func.count(UserProgress.id)
    ).filter_by(user_id=user_id, completed=True).scalar() or 0

    favorite_count = db.session.query(
        db.func.count(Favorite.id)
    ).filter_by(user_id=user_id).scalar() or 0

    tests_taken = db.session.query(
        db.func.count(TestResult.id)
    ).filter_by(student_id=user_id).scalar() or 0

    avg_score_data = db.session.query(
        db.func.avg(TestResult.score * 100.0 / TestResult.total)
    ).filter(
        TestResult.student_id == user_id,
        TestResult.total > 0
    ).scalar()

    avg_score = int(avg_score_data) if avg_score_data else 0

    overall_progress = int(
        (completed_lessons / total_lessons * 100)
    ) if total_lessons > 0 else 0

    return {
        'total_courses': total_courses,
        'total_lessons': total_lessons,
        'completed_lessons': completed_lessons,
        'overall_progress': overall_progress,
        'favorite_count': favorite_count,
        'tests_taken': tests_taken,
        'avg_score': avg_score
    }


def calculate_test_score(test_id, answers):
    """Рассчитать результат теста"""
    from models import db, Question

    questions = db.session.query(Question).filter_by(test_id=test_id).all()

    score = 0
    total = len(questions)

    for question in questions:
        user_answer = answers.get(str(question.id))
        if user_answer and int(user_answer) == question.correct_answer:
            score += 1

    return {
        'score': score,
        'total': total
    }


def sanitize_filename(filename):
    """Очистка имени файла от опасных символов"""
    filename = pathlib.Path(filename).name
    safe = secure_filename(filename)
    return safe if safe else 'unnamed'


def paginate_query(query, page=1, per_page=20):
    """Пагинация запроса SQLAlchemy"""
    total = query.count()
    pages = (total + per_page - 1) // per_page

    if page < 1:
        page = 1
    elif page > pages and pages > 0:
        page = pages

    offset = (page - 1) * per_page
    items = query.limit(per_page).offset(offset).all()

    return {
        'items': items,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': pages
    }


# def init_demo_data():
#     """Создание демонстрационных данных при первом запуске"""
#     from models import db, User, Course, Lesson, Test, Question, Group
#     import os
#
#     logger.info("Создание демонстрационных данных...")
#
#     admin = User.query.filter_by(role='admin').first()
#     if admin:
#         logger.info("Демо-данные уже существуют")
#         return
#
#     # Создаем админа
#     admin_password = os.environ.get('ADMIN_PASSWORD', 'Admin123!')
#     admin = User(
#         username='admin',
#         fullname='Администратор',
#         email='admin@example.com',
#         role='admin',
#         approved=True
#     )
#     admin.set_password(admin_password)
#     db.session.add(admin)
#
#     # Создаем преподавателя
#     teacher = User(
#         username='teacher',
#         fullname='Преподаватель Тестовый',
#         email='teacher@example.com',
#         role='teacher',
#         approved=True
#     )
#     teacher.set_password('Teacher123!')
#     db.session.add(teacher)
#
#     # Создаем студента
#     student = User(
#         username='student',
#         fullname='Студент Тестовый',
#         email='student@example.com',
#         role='student',
#         approved=True
#     )
#     student.set_password('Student123!')
#     db.session.add(student)
#
#     db.session.commit()
#
#     # Создаем группу
#     group = Group(
#         name='Группа 101',
#         description='Тестовая группа'
#     )
#     db.session.add(group)
#     db.session.commit()
#
#     # Назначаем студента в группу
#     student.group_id = group.id
#     db.session.commit()
#
#     # Создаем демо-курс
#     course = Course(
#         title='Введение в программирование на Python',
#         description='Изучите основы языка программирования Python с нуля. '
#                     'Курс подходит для начинающих и не требует предварительных знаний.',
#         creator_id=teacher.id
#     )
#     db.session.add(course)
#     db.session.commit()
#
#     # Создаем уроки
#     lesson1 = Lesson(
#         course_id=course.id,
#         title='Что такое Python?',
#         content='Python - это высокоуровневый язык программирования общего назначения. '
#                 'Он известен своей простотой и читаемостью кода.',
#         order=1
#     )
#
#     lesson2 = Lesson(
#         course_id=course.id,
#         title='Установка Python',
#         content='В этом уроке мы научимся устанавливать Python на различные операционные системы.',
#         order=2
#     )
#
#     lesson3 = Lesson(
#         course_id=course.id,
#         title='Переменные и типы данных',
#         content='Переменные - это контейнеры для хранения данных. '
#                 'В Python есть несколько основных типов данных: int, float, str, bool.',
#         order=3
#     )
#
#     db.session.add_all([lesson1, lesson2, lesson3])
#     db.session.commit()
#
#     # Создаем тест
#     test = Test(
#         course_id=course.id,
#         title='Проверочный тест: Основы Python'
#     )
#     db.session.add(test)
#     db.session.commit()
#
#     # Создаем вопросы
#     q1 = Question(
#         test_id=test.id,
#         text='Что такое Python?',
#         option1='Язык программирования',
#         option2='Текстовый редактор',
#         option3='Операционная система',
#         option4='База данных',
#         correct_answer=1
#     )
#
#     q2 = Question(
#         test_id=test.id,
#         text='Какой тип данных используется для хранения целых чисел?',
#         option1='str',
#         option2='float',
#         option3='int',
#         option4='bool',
#         correct_answer=3
#     )
#
#     q3 = Question(
#         test_id=test.id,
#         text='Какой символ используется для комментариев в Python?',
#         option1='//',
#         option2='#',
#         option3='/*',
#         option4='--',
#         correct_answer=2
#     )
#
#     db.session.add_all([q1, q2, q3])
#     db.session.commit()
#
#     logger.info("✅ Демо-данные созданы:")
#     logger.info(f"   Админ: admin@example.com / {admin_password}")
#     logger.info(f"   Преподаватель: teacher@example.com / Teacher123!")
#     logger.info(f"   Студент: student@example.com / Student123!")
