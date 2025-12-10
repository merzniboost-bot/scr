
        const lessonsData = {
            '1.1': {
                title: 'Урок 1.1: Что такое Python и зачем он нужен',
                progress: 1
            },
            '1.2': {
                title: 'Урок 1.2: Установка Python',
                progress: 2
            },
            '1.3': {
                title: 'Урок 1.3: Первая программа',
                progress: 3
            },
            '1.4': {
                title: 'Урок 1.4: Практическое задание',
                progress: 4
            },
            '2.1': {
                title: 'Урок 2.1: Переменные',
                progress: 5
            },
            '2.2': {
                title: 'Урок 2.2: Числа',
                progress: 6
            },
            '2.3': {
                title: 'Урок 2.3: Строки',
                progress: 7
            },
            '2.4': {
                title: 'Урок 2.4: Списки',
                progress: 8
            }
        };

        function switchLesson(lessonId) {
            document.querySelectorAll('.lesson-item').forEach(item => {
                item.classList.remove('active');
            });

            const selectedLesson = document.querySelector(`[data-lesson="${lessonId}"]`);
            if (selectedLesson) {
                selectedLesson.classList.add('active');
            }

            document.querySelectorAll('.lesson-description').forEach(desc => {
                desc.classList.remove('active');
            });

            const selectedDescription = document.querySelector(`.lesson-description[data-lesson="${lessonId}"]`);
            if (selectedDescription) {
                selectedDescription.classList.add('active');
            }

            const lessonData = lessonsData[lessonId];
            if (lessonData) {
                document.getElementById('current-lesson-title').textContent = lessonData.title;
                document.getElementById('current-lesson-counter').textContent = `${lessonData.progress} урок из 19`;
                document.getElementById('progress-counter').textContent = `${lessonData.progress} из 19 уроков`;
                
                const progressPercent = (lessonData.progress / 19) * 100;
                document.getElementById('progress-fill').style.width = `${progressPercent}%`;
            }

            document.querySelector('.description-section').scrollIntoView({
                behavior: 'smooth'
            });
        }

        document.addEventListener('DOMContentLoaded', function() {
            const lessonItems = document.querySelectorAll('.lesson-item');
            
            lessonItems.forEach(item => {
                item.addEventListener('click', function() {
                    const lessonId = this.getAttribute('data-lesson');
                    switchLesson(lessonId);
                });
            });

            switchLesson('1.1');
        });
