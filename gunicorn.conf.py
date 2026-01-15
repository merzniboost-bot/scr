import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gthread"
threads = 4
timeout = 60

# ===========================
# Логи
# ===========================
accesslog = None      # отключаем access log (не будет дублирования)
errorlog = "-"        # ошибки -> stdout (journald)
loglevel = "info"     # INFO в проде
