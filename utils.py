# utils.py
"""
Вспомогательные функции
"""
import re
import uuid
import pathlib
import logging
import base64
from datetime import datetime, timedelta
from threading import Lock
from werkzeug.utils import secure_filename


# ============================================================================
# СИСТЕМА КЭШИРОВАНИЯ
# ============================================================================

class SimpleCache:
    """Простой in-memory кэш с TTL"""
    
    def __init__(self, default_ttl=300):
        """
        Args:
            default_ttl: Время жизни кэша в секундах (по умолчанию 5 минут)
        """
        self._cache = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
    
    def get(self, key):
        """Получить значение из кэша"""
        with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if datetime.now() < expires_at:
                    return value
                else:
                    del self._cache[key]
            return None
    
    def set(self, key, value, ttl=None):
        """Установить значение в кэш"""
        if ttl is None:
            ttl = self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)
        with self._lock:
            self._cache[key] = (value, expires_at)
    
    def delete(self, key):
        """Удалить значение из кэша"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def invalidate_pattern(self, pattern):
        """Инвалидировать все ключи, содержащие pattern"""
        with self._lock:
            keys_to_delete = [k for k in self._cache if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
    
    def clear(self):
        """Очистить весь кэш"""
        with self._lock:
            self._cache.clear()


# Глобальный экземпляр кэша
cache = SimpleCache(default_ttl=300)  # 5 минут по умолчанию


def invalidate_course_cache(course_id):
    """Инвалидировать кэш для конкретного курса"""
    cache.invalidate_pattern(f"course_{course_id}_")
    logger.debug(f"[CACHE] Кэш инвалидирован для курса {course_id}")
from config import UPLOAD_DIR, Config
from zoneinfo import ZoneInfo
from PIL import Image, ImageOps
import io
from markupsafe import Markup, escape
import markdown
import bleach
try:
    from bleach.css_sanitizer import CSSSanitizer
except Exception:
    CSSSanitizer = None

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
    Рендер Markdown в безопасный HTML через единый пайплайн
    """
    if not text:
        return Markup("")
    return Markup(markdown_to_html(text))


def markdown_to_html(content, safe_mode=True):
    """Конвертирует Markdown в HTML с поддержкой цветного текста"""
    if not content:
        return ""
    
    try:
        import markdown
        import bleach
        
        # Настройки Markdown с поддержкой HTML
        html = markdown.markdown(
            content,
            extensions=['extra', 'fenced_code', 'tables', 'nl2br'],
            output_format='html'
        )
        
        if safe_mode:
            # Безопасные теги
            base_tags = list(bleach.sanitizer.ALLOWED_TAGS)
            allowed_tags = base_tags + [
                'span', 'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'br', 'hr', 'pre', 'code', 'blockquote',
                'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'th', 'td'
            ]
            
            # Разрешенные атрибуты
            allowed_attrs = {
                'span': ['style', 'class'],
                'div': ['style', 'class'],
                'p': ['style', 'class'],
                'a': ['href', 'title', 'target', 'rel'],
                'img': ['src', 'alt', 'title', 'width', 'height'],
                'code': ['class'],
                'pre': ['class'],
                'table': ['class', 'border'],
                'td': ['colspan', 'rowspan'],
                'th': ['colspan', 'rowspan']
            }
            
            # Очищаем
            html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
        
        return html
        
    except Exception as e:
        logger.error(f"[UTILS] Ошибка конвертации Markdown: {e}")
        return content


def sanitize_html_description(content: str | None) -> str:
    """
    Санитизация HTML для описаний курса (WYSIWYG, без Markdown).
    Разрешаем базовые теги форматирования и inline-стили для цветов.
    """
    if not content:
        return ""

    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's',
        'ul', 'ol', 'li', 'code', 'pre', 'blockquote',
        'h1', 'h2', 'h3', 'h4', 'div', 'span', 'a'
    ]

    allowed_attrs = {
        '*': ['class', 'style'],
        'a': ['href', 'target', 'rel'],
        'code': ['class', 'style'],
        'pre': ['class', 'style'],
        'span': ['class', 'style'],
        'div': ['class', 'style'],
        'p': ['class', 'style'],
        'strong': ['style'],
        'b': ['style'],
        'em': ['style'],
        'i': ['style'],
        'u': ['style'],
        's': ['style'],
        'h1': ['style'],
        'h2': ['style'],
        'h3': ['style'],
        'h4': ['style'],
    }

    # Разрешаем CSS-свойства для WYSIWYG
    allowed_styles = [
        'color', 'background-color', 'background',
        'font-size', 'font-weight', 'font-style', 'font-family',
        'text-align', 'text-decoration', 'text-decoration-line',
        'padding', 'margin', 'border', 'border-radius',
        'display', 'width', 'height'
    ]

    css_sanitizer = CSSSanitizer(allowed_css_properties=allowed_styles) if CSSSanitizer else None

    try:
        if css_sanitizer:
            cleaned = bleach.Cleaner(
                tags=allowed_tags,
                attributes=allowed_attrs,
                css_sanitizer=css_sanitizer,
                strip=True,
            ).clean(content)
        else:
            # fallback for older bleach versions
            cleaned = bleach.clean(
                content,
                tags=allowed_tags,
                attributes=allowed_attrs,
                strip=True,
            )
        return cleaned
    except Exception as e:
        logger.error(f"[UTILS] Ошибка санитизации описания: {e}")
        return escape(content)


def html_to_plain_text(content: str | None, max_len: int | None = None) -> str:
    """
    Удаляет теги, оставляя только текст. Опционально обрезает до max_len.
    """
    if not content:
        return ""

    text = bleach.clean(content, tags=[], strip=True)
    return text[:max_len] if max_len else text


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


def save_avatar(file, size=200):
    """
    Сохраняет аватарку с crop в квадрат и оптимизацией.
    
    Args:
        file: FileStorage объект или data URL
        size: размер квадрата (по умолчанию 200x200)
    
    Returns:
        str: имя файла или None
    """
    if not file:
        return None
    
    try:
        # Если это data URL
        if isinstance(file, str) and file.startswith('data:image/'):
            header, b64data = file.split(',', 1)
            raw = base64.b64decode(b64data)
            img = Image.open(io.BytesIO(raw))
        # Если это FileStorage
        else:
            if not file.filename:
                return None
            img = Image.open(file.stream)
        
        # Конвертируем в RGB
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # Crop в квадрат (центрированный)
        width, height = img.size
        if width > height:
            left = (width - height) // 2
            img = img.crop((left, 0, left + height, height))
        elif height > width:
            top = (height - width) // 2
            img = img.crop((0, top, width, top + width))
        
        # Resize до нужного размера
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        
        # Сохраняем
        unique_filename = f"avatar_{uuid.uuid4().hex[:8]}.webp"
        final_path = UPLOAD_DIR / unique_filename
        img.save(final_path, 'WEBP', quality=90, method=6)
        
        logger.info(f"[UTILS] Аватарка сохранена: {unique_filename} ({size}x{size})")
        return unique_filename
        
    except Exception as e:
        logger.error(f"[UTILS] Ошибка сохранения аватарки: {e}")
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


def get_course_materials(course_id, use_cache=True):
    """
    Получить все материалы курса (уроки + тесты) в правильном порядке
    
    Args:
        course_id: ID курса
        use_cache: Использовать кэш (по умолчанию True)
    
    Returns:
        list: Список словарей с информацией о материалах
              [{'type': 'lesson'|'test', 'id': int, 'order': int, 'obj': Lesson|Test}, ...]
    """
    from models import db, Lesson, Test
    
    cache_key = f"course_{course_id}_materials"
    
    # Пробуем получить из кэша (но obj нельзя кэшировать напрямую из-за сессии SQLAlchemy)
    # Поэтому кэшируем только ID и order, объекты подгружаем заново
    
    try:
        course_lessons = db.session.query(Lesson).filter_by(course_id=course_id).order_by(Lesson.order).all()
        course_tests = db.session.query(Test).filter_by(course_id=course_id).order_by(Test.order).all()
        
        materials = []
        for l in course_lessons:
            materials.append({'type': 'lesson', 'id': l.id, 'order': l.order, 'obj': l})
        for t in course_tests:
            materials.append({'type': 'test', 'id': t.id, 'order': t.order or 999999, 'obj': t})
        
        materials.sort(key=lambda x: x['order'])
        return materials
        
    except Exception as e:
        logger.error(f"[MATERIALS] Ошибка получения материалов курса {course_id}: {e}")
        return []


def get_course_materials_cached_ids(course_id):
    """
    Получить ID материалов курса с кэшированием (без ORM объектов)
    
    Returns:
        list: [{'type': 'lesson'|'test', 'id': int, 'order': int}, ...]
    """
    from models import db, Lesson, Test
    
    cache_key = f"course_{course_id}_material_ids"
    
    # Пробуем получить из кэша
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"[CACHE] HIT: {cache_key}")
        return cached
    
    try:
        # Запрашиваем только нужные поля
        lessons_data = db.session.query(Lesson.id, Lesson.order).filter_by(course_id=course_id).all()
        tests_data = db.session.query(Test.id, Test.order).filter_by(course_id=course_id).all()
        
        materials = []
        for lid, lorder in lessons_data:
            materials.append({'type': 'lesson', 'id': lid, 'order': lorder})
        for tid, torder in tests_data:
            materials.append({'type': 'test', 'id': tid, 'order': torder or 999999})
        
        materials.sort(key=lambda x: x['order'])
        
        # Кэшируем результат
        cache.set(cache_key, materials, ttl=300)
        logger.debug(f"[CACHE] SET: {cache_key}")
        
        return materials
        
    except Exception as e:
        logger.error(f"[MATERIALS] Ошибка получения ID материалов курса {course_id}: {e}")
        return []


def get_test_analytics(course_id=None):
    """
    Получить аналитику по сложности тестов
    
    Args:
        course_id: ID курса (если None - все тесты)
    
    Returns:
        list: Список словарей с аналитикой по каждому тесту, отсортированный по сложности
    """
    from models import db, Test, TestResult
    from sqlalchemy import func
    
    try:
        # Базовый запрос
        query = db.session.query(
            Test.id,
            Test.title,
            Test.course_id,
            func.count(TestResult.id).label('attempts'),
            func.avg(TestResult.score * 100.0 / TestResult.total).label('avg_score'),
            func.sum(
                db.case((TestResult.score * 100.0 / TestResult.total < 60, 1), else_=0)
            ).label('failed_count')
        ).outerjoin(TestResult, Test.id == TestResult.test_id).group_by(Test.id)
        
        if course_id:
            query = query.filter(Test.course_id == course_id)
        
        results = query.all()
        
        analytics = []
        for row in results:
            attempts = row.attempts or 0
            avg_score = float(row.avg_score) if row.avg_score else 0
            failed_count = row.failed_count or 0
            failed_rate = (failed_count / attempts * 100) if attempts > 0 else 0
            
            analytics.append({
                'test_id': row.id,
                'title': row.title,
                'course_id': row.course_id,
                'attempts': attempts,
                'avg_score': round(avg_score, 1),
                'failed_count': failed_count,
                'failed_rate': round(failed_rate, 1),
                'difficulty': 'high' if failed_rate > 50 else ('medium' if failed_rate > 30 else 'low')
            })
        
        # Сортируем по проценту неудач (самые сложные первыми)
        analytics.sort(key=lambda x: -x['failed_rate'])
        
        return analytics
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Ошибка получения аналитики тестов: {e}")
        return []


def get_next_incomplete_material(user_id, course_id):
    """
    Получить следующий незавершенный материал курса для пользователя
    
    Args:
        user_id: ID пользователя
        course_id: ID курса
    
    Returns:
        dict или None: {'type': 'lesson'|'test', 'id': int, 'title': str} или None если всё пройдено
    """
    from models import db, UserProgress, TestResult
    
    try:
        materials = get_course_materials(course_id)
        
        # Получаем прогресс по урокам
        completed_lessons = set()
        lesson_progress = db.session.query(UserProgress.lesson_id).filter(
            UserProgress.user_id == user_id,
            UserProgress.course_id == course_id,
            UserProgress.completed == True
        ).all()
        for lp in lesson_progress:
            completed_lessons.add(lp.lesson_id)
        
        # Получаем прогресс по тестам
        completed_tests = set()
        test_results = db.session.query(TestResult.test_id).filter(
            TestResult.student_id == user_id
        ).distinct().all()
        for tr in test_results:
            completed_tests.add(tr.test_id)
        
        # Ищем первый незавершенный материал
        for mat in materials:
            if mat['type'] == 'lesson' and mat['id'] not in completed_lessons:
                return {
                    'type': 'lesson',
                    'id': mat['id'],
                    'title': mat['obj'].title
                }
            elif mat['type'] == 'test' and mat['id'] not in completed_tests:
                return {
                    'type': 'test',
                    'id': mat['id'],
                    'title': mat['obj'].title
                }
        
        return None  # Всё пройдено
        
    except Exception as e:
        logger.error(f"[NAV] Ошибка получения следующего материала: {e}")
        return None


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