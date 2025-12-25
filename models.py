"""
Модели базы данных
"""
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Timezones
MSK = ZoneInfo('Europe/Moscow')

def now_msk():
    """Get current datetime in MSK timezone"""
    return datetime.now(timezone.utc).astimezone(MSK).replace(tzinfo=None)

db = SQLAlchemy()
bcrypt = Bcrypt()


class User(db.Model):
    """Модель пользователя"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    fullname = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student', index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    position = db.Column(db.String(100), nullable=True)
    avatar_filename = db.Column(db.String(512))
    approved = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=now_msk)

    # Relationships
    group_rel = db.relationship('Group', backref='students')
    created_categories = db.relationship('Category', foreign_keys='Category.created_by', backref='creator')

    def set_password(self, password):
        """Установить хешированный пароль"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Проверить пароль"""
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Group(db.Model):
    """Учебная группа"""
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=now_msk)

    def __repr__(self):
        return f'<Group {self.name}>'


class Category(db.Model):
    """Категории курсов"""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), default='')
    color = db.Column(db.String(7), default='#12A0F4')
    icon = db.Column(db.String(50), default='📚')
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=now_msk)
    updated_at = db.Column(db.DateTime, default=now_msk, onupdate=now_msk)

    # Relationships
    courses = db.relationship('Course', back_populates='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Course(db.Model):
    """Курс обучения"""
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text)
    preview_filename = db.Column(db.String(512))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=now_msk)
    updated_at = db.Column(db.DateTime, default=now_msk, onupdate=now_msk)

    # Relationships
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_courses')
    category = db.relationship('Category', foreign_keys=[category_id], back_populates='courses')
    lessons = db.relationship('Lesson', back_populates='course', cascade='all, delete-orphan',
                            order_by='Lesson.order', lazy='select')
    tests = db.relationship('Test', back_populates='course', cascade='all, delete-orphan', lazy='select')

    def __repr__(self):
        return f'<Course {self.title}>'


class Module(db.Model):
    """Модуль курса - группа уроков и тестов"""
    __tablename__ = 'modules'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, default=0, index=True)
    is_visible = db.Column(db.Boolean, default=True)
    open_at = db.Column(db.DateTime, nullable=True)  # Когда модуль станет доступен
    created_at = db.Column(db.DateTime, default=now_msk)

    # Relationships
    course = db.relationship('Course', backref=db.backref('modules', order_by='Module.order', cascade='all, delete-orphan'))
    lessons = db.relationship('Lesson', back_populates='module', order_by='Lesson.order')

    def __repr__(self):
        return f'<Module {self.title}>'


class Lesson(db.Model):
    """Урок в курсе"""
    __tablename__ = 'lessons'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id', ondelete='SET NULL'), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    video_filename = db.Column(db.String(512))
    file_filename = db.Column(db.String(512))
    order = db.Column(db.Integer, default=0, index=True)
    created_at = db.Column(db.DateTime, default=now_msk)
    updated_at = db.Column(db.DateTime, default=now_msk, onupdate=now_msk)
    open_at = db.Column(db.DateTime, nullable=True)  # Когда урок станет доступен студентам

    # Relationships
    course = db.relationship('Course', back_populates='lessons')
    module = db.relationship('Module', back_populates='lessons')
    assignments = db.relationship('Assignment', back_populates='lesson', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<Lesson {self.title}>'


class Test(db.Model):
    """Тест для курса"""
    __tablename__ = 'tests'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True)
    module_id = db.Column(db.Integer, db.ForeignKey('modules.id', ondelete='SET NULL'), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    max_attempts = db.Column(db.Integer, default=0, nullable=False)
    open_at = db.Column(db.DateTime, nullable=True)  # Время открытия теста для студентов
    created_at = db.Column(db.DateTime, default=now_msk)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    order = db.Column(db.Integer, nullable=False, default=1)

    # Relationships
    course = db.relationship('Course', back_populates='tests')
    module = db.relationship('Module', backref='tests')
    questions = db.relationship('Question', back_populates='test', cascade='all, delete-orphan', lazy='select')
    results = db.relationship('TestResult', back_populates='test', lazy=True)

    def __repr__(self):
        return f'<Test {self.title}>'


class Question(db.Model):
    """Вопрос в тесте"""
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id', ondelete='CASCADE'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(255))
    option2 = db.Column(db.String(255))
    option3 = db.Column(db.String(255))
    option4 = db.Column(db.String(255))
    correct_answer = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=now_msk)

    # Relationships
    test = db.relationship('Test', back_populates='questions')

    def __repr__(self):
        return f'<Question {self.id}>'


class TestResult(db.Model):
    """Результаты тестов"""
    __tablename__ = 'test_results'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id', ondelete='CASCADE'), nullable=False, index=True)
    score = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=now_msk)

    # Relationships
    student = db.relationship('User', foreign_keys=[student_id])
    test = db.relationship('Test', foreign_keys=[test_id])

    # Indexes
    __table_args__ = (db.Index('idx_student_test', 'student_id', 'test_id'),)

    def __repr__(self):
        return f'<TestResult {self.id}>'


class UserProgress(db.Model):
    """Прогресс пользователя по урокам"""
    __tablename__ = 'user_progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False, index=True)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_msk)

    # Constraints and indexes
    __table_args__ = (
        db.UniqueConstraint('user_id', 'lesson_id', name='uq_user_lesson'),
        db.Index('idx_user_course_progress', 'user_id', 'course_id'),
        db.Index('idx_user_completed', 'user_id', 'completed'),
    )

    def __repr__(self):
        return f'<UserProgress user={self.user_id} lesson={self.lesson_id}>'


class Favorite(db.Model):
    """Избранные курсы пользователей"""
    __tablename__ = 'favorites'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, index=True)
    added_at = db.Column(db.DateTime, default=now_msk)

    # Constraints and indexes
    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='uq_user_course_fav'),
        db.Index('idx_user_favorites', 'user_id'),
    )

    def __repr__(self):
        return f'<Favorite user={self.user_id} course={self.course_id}>'


class Assignment(db.Model):
    """Задание для урока с загрузкой файла"""
    __tablename__ = 'assignments'

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=True)
    max_file_size_mb = db.Column(db.Integer, default=10)
    allowed_extensions = db.Column(db.String(255), default='pdf,doc,docx,txt,zip,rar,py,js,html,css')
    is_required = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=now_msk)
    updated_at = db.Column(db.DateTime, default=now_msk, onupdate=now_msk)

    # Relationships
    lesson = db.relationship('Lesson', back_populates='assignments')
    submissions = db.relationship('Submission', back_populates='assignment', cascade='all, delete-orphan', lazy='dynamic')

    def get_allowed_extensions_list(self):
        """Получить список разрешенных расширений"""
        return [ext.strip().lower() for ext in self.allowed_extensions.split(',') if ext.strip()]

    def is_overdue(self):
        """Проверить, просрочено ли задание"""
        from datetime import datetime
        if not self.deadline:
            return False
        return datetime.utcnow() > self.deadline

    def __repr__(self):
        return f'<Assignment {self.title}>'


class Submission(db.Model):
    """Сданное задание студентом"""
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id', ondelete='CASCADE'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Файл
    file_filename = db.Column(db.String(512), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    
    # Статус и оценка
    status = db.Column(db.String(20), default='submitted', index=True)
    grade = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    
    # Время
    submitted_at = db.Column(db.DateTime, default=now_msk)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    assignment = db.relationship('Assignment', back_populates='submissions')
    student = db.relationship('User', foreign_keys=[student_id])

    # Indexes
    __table_args__ = (
        db.UniqueConstraint('assignment_id', 'student_id', name='uq_assignment_student'),
        db.Index('idx_submission_status', 'assignment_id', 'status'),
    )

    def is_late(self):
        """Проверить, сдано ли с опозданием"""
        if not self.assignment.deadline:
            return False
        return self.submitted_at > self.assignment.deadline

    def __repr__(self):
        return f'<Submission assignment={self.assignment_id} student={self.student_id}>'