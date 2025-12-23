# tests/test_utils.py
"""
Unit-тесты для функций utils.py
Запуск: python -m pytest tests/test_utils.py -v
"""
import pytest
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Course, Lesson, Test, User
from utils import get_course_materials


@pytest.fixture(scope='function')
def app():
    """Создание тестового приложения"""
    test_app = create_app('testing')
    test_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    test_app.config['TESTING'] = True
    test_app.config['WTF_CSRF_ENABLED'] = False
    
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.rollback()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Тестовый клиент"""
    return app.test_client()


@pytest.fixture(scope='function')
def test_user(app):
    """Создание тестового пользователя"""
    with app.app_context():
        user = User(
            username='testuser',
            fullname='Test User',
            email='test@example.com',
            role='teacher',
            approved=True
        )
        user.set_password('TestPassword123')
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture(scope='function')
def test_course(app, test_user):
    """Создание тестового курса"""
    with app.app_context():
        course = Course(
            title='Тестовый курс',
            description='Описание тестового курса',
            creator_id=test_user
        )
        db.session.add(course)
        db.session.commit()
        return course.id


class TestGetCourseMaterials:
    """Тесты для функции get_course_materials()"""
    
    def test_empty_course_returns_empty_list(self, app, test_course):
        """Пустой курс (нет уроков/тестов) → возвращается пустой список"""
        with app.app_context():
            materials = get_course_materials(test_course)
            
            assert materials == []
            assert isinstance(materials, list)
    
    def test_only_lessons(self, app, test_course):
        """Курс только с уроками"""
        with app.app_context():
            # Создаем уроки
            lesson1 = Lesson(course_id=test_course, title='Урок 1', order=1)
            lesson2 = Lesson(course_id=test_course, title='Урок 2', order=2)
            lesson3 = Lesson(course_id=test_course, title='Урок 3', order=3)
            
            db.session.add_all([lesson1, lesson2, lesson3])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 3
            assert all(m['type'] == 'lesson' for m in materials)
            assert [m['order'] for m in materials] == [1, 2, 3]
    
    def test_only_tests(self, app, test_course):
        """Курс только с тестами"""
        with app.app_context():
            test1 = Test(course_id=test_course, title='Тест 1', order=1)
            test2 = Test(course_id=test_course, title='Тест 2', order=2)
            
            db.session.add_all([test1, test2])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 2
            assert all(m['type'] == 'test' for m in materials)
    
    def test_mixed_order_lessons_and_tests(self, app, test_course):
        """Смешанный порядок уроков и тестов"""
        with app.app_context():
            lesson1 = Lesson(course_id=test_course, title='Урок 1', order=1)
            test1 = Test(course_id=test_course, title='Тест 1', order=2)
            lesson2 = Lesson(course_id=test_course, title='Урок 2', order=3)
            test2 = Test(course_id=test_course, title='Тест 2', order=4)
            
            db.session.add_all([lesson1, test1, lesson2, test2])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 4
            assert materials[0]['type'] == 'lesson'
            assert materials[0]['order'] == 1
            assert materials[1]['type'] == 'test'
            assert materials[1]['order'] == 2
            assert materials[2]['type'] == 'lesson'
            assert materials[2]['order'] == 3
            assert materials[3]['type'] == 'test'
            assert materials[3]['order'] == 4
    
    def test_test_with_none_order(self, app, test_course):
        """Тест с order=None трактуется как большой номер"""
        with app.app_context():
            lesson1 = Lesson(course_id=test_course, title='Урок 1', order=1)
            lesson2 = Lesson(course_id=test_course, title='Урок 2', order=2)
            test_no_order = Test(course_id=test_course, title='Тест без order', order=None)
            
            db.session.add_all([lesson1, lesson2, test_no_order])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 3
            # Тест с order=None должен быть в конце
            assert materials[2]['type'] == 'test'
            assert materials[2]['order'] == 999999  # Заменённое значение для None
    
    def test_duplicate_order_stable_sort(self, app, test_course):
        """Дубликат order → стабильная сортировка"""
        with app.app_context():
            lesson1 = Lesson(course_id=test_course, title='Урок 1', order=1)
            test1 = Test(course_id=test_course, title='Тест 1', order=1)
            lesson2 = Lesson(course_id=test_course, title='Урок 2', order=2)
            
            db.session.add_all([lesson1, test1, lesson2])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 3
            # Проверяем, что все с order=1 идут первыми
            assert materials[0]['order'] == 1
            assert materials[1]['order'] == 1
            assert materials[2]['order'] == 2
    
    def test_correct_structure_of_elements(self, app, test_course):
        """Корректная структура элементов: type, id, order, obj"""
        with app.app_context():
            lesson = Lesson(course_id=test_course, title='Урок 1', order=1)
            test = Test(course_id=test_course, title='Тест 1', order=2)
            
            db.session.add_all([lesson, test])
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            # Проверяем урок
            lesson_mat = materials[0]
            assert 'type' in lesson_mat
            assert 'id' in lesson_mat
            assert 'order' in lesson_mat
            assert 'obj' in lesson_mat
            assert lesson_mat['type'] in ('lesson', 'test')
            assert isinstance(lesson_mat['id'], int)
            assert isinstance(lesson_mat['order'], int)
            
            # Проверяем тест
            test_mat = materials[1]
            assert test_mat['type'] == 'test'
            assert test_mat['obj'].title == 'Тест 1'
    
    def test_nonexistent_course(self, app):
        """Несуществующий курс → пустой список"""
        with app.app_context():
            materials = get_course_materials(99999)
            assert materials == []
    
    def test_large_course(self, app, test_course):
        """Большой курс с множеством материалов"""
        with app.app_context():
            # Создаем 50 уроков и 20 тестов
            for i in range(1, 51):
                lesson = Lesson(course_id=test_course, title=f'Урок {i}', order=i*2-1)
                db.session.add(lesson)
            
            for i in range(1, 21):
                test = Test(course_id=test_course, title=f'Тест {i}', order=i*5)
                db.session.add(test)
            
            db.session.commit()
            
            materials = get_course_materials(test_course)
            
            assert len(materials) == 70
            # Проверяем сортировку
            orders = [m['order'] for m in materials]
            assert orders == sorted(orders)


class TestGetCourseMaterialsIntegration:
    """Интеграционные тесты"""
    
    def test_materials_reflect_database_changes(self, app, test_course):
        """Материалы отражают изменения в БД"""
        with app.app_context():
            # Сначала пусто
            assert get_course_materials(test_course) == []
            
            # Добавляем урок
            lesson = Lesson(course_id=test_course, title='Урок 1', order=1)
            db.session.add(lesson)
            db.session.commit()
            
            materials = get_course_materials(test_course)
            assert len(materials) == 1
            
            # Добавляем тест
            test = Test(course_id=test_course, title='Тест 1', order=2)
            db.session.add(test)
            db.session.commit()
            
            materials = get_course_materials(test_course)
            assert len(materials) == 2
            
            # Удаляем урок
            db.session.delete(lesson)
            db.session.commit()
            
            materials = get_course_materials(test_course)
            assert len(materials) == 1
            assert materials[0]['type'] == 'test'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
