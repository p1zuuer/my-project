"""
Backward-compatibility shim. Реальная реализация переехала в services/gemini.py
(TASK 2/3 аудита — модульная структура сервисов + гарантированный graceful
fallback). Оставлено, чтобы bot.py, checker.py и check_handlers.py могли
продолжать импортировать `ai_analyst` без изменений.
"""
import os
import sys
import logging

logger = logging.getLogger(__name__)

try:
    from services.gemini import (
        generate_osint_summary,
        generate_wallet_status_analysis,
        OSINT_SYSTEM_PROMPT,
    )
except ModuleNotFoundError as e:
    # Диагностический guard: раньше эта ошибка (в реальном инциденте — из-за
    # рассинхронизации регистра "Services" vs "services" между локальной
    # case-insensitive файловой системой и Linux на Render) проявлялась как
    # голый ModuleNotFoundError на строке импорта в bot.py, без указания на
    # первопричину. Логируем явный диагностический контекст перед тем, как
    # перевыбросить исключение — приложение все равно должно упасть (иначе
    # бот запустится без AI-модуля вообще), но теперь причина видна сразу
    # в первых строках лога Render, а не требует поиска по трейсбеку.
    logger.critical(
        "Не удалось импортировать services.gemini: %s\n"
        "Проверьте: (1) папка services/ существует и закоммичена в git "
        "(включая пустой services/__init__.py); (2) регистр названия папки "
        "точно 'services', а не 'Services' — Render использует Linux, "
        "файловая система которого чувствительна к регистру, в отличие от "
        "Windows/macOS; (3) файлы не попадают под правило .gitignore. "
        "cwd=%s, sys.path[0]=%s",
        e, os.getcwd(), sys.path[0] if sys.path else "?"
    )
    raise

__all__ = ["generate_osint_summary", "generate_wallet_status_analysis", "OSINT_SYSTEM_PROMPT"]