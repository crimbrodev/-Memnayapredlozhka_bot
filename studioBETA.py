"""
=============================================================================
NewEngine Studio v1.0 - Бета
=============================================================================

"""

import customtkinter as ctk
import os
import subprocess
import threading
import sys
import platform
import time
import shutil
import urllib.request
import zipfile
import io
import re
import json
import hashlib
from datetime import datetime
from tkinter import messagebox, ttk, simpledialog
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from concurrent.futures import ThreadPoolExecutor

# =============================================================================
# 1. ГЛОБАЛЬНАЯ КОНФИГУРАЦИЯ ПРИЛОЖЕНИЯ
# =============================================================================

class Config:
    """
    Статический класс конфигурации. Хранит пути и системные параметры.
    Все пути вычисляются относительно папки, в которой находится studio.py.
    """
    APP_NAME = "NewEngine Studio"
    VERSION = "1.0 (Fixed Beta)"
    THEME = "Dark"
    ACCENT_COLOR = "blue"
    
    # Определение корня проекта
    ROOT_DIR = Path(os.getcwd())
    
    # Директории сборки (результаты компиляции)
    BIN_DIR = ROOT_DIR / "bin"
    OBJ_DIR = BIN_DIR / "obj"
    
    # Директории исходного кода и ресурсов
    INCLUDE_DIR = ROOT_DIR / "include"
    THIRDPARTY_DIR = INCLUDE_DIR / "thirdparty"
    ASSETS_DIR = ROOT_DIR / "assets"
    GAME_DIR = ROOT_DIR / "game"
    ENGINE_DIR = ROOT_DIR / "engine"
    
    # Директории системы безопасности (бэкапы)
    BACKUP_DIR = ROOT_DIR / "backups"
    
    # Конфигурация компилятора GCC
    COMPILER = "gcc"
    if platform.system() == "Windows":
        OUTPUT_BINARY = "game.exe"
    else:
        OUTPUT_BINARY = "game"
        
    # Ссылки для системы обновлений (GitHub)
    URL_STUDIO_SOURCE = "https://raw.githubusercontent.com/crimbrodev/newengineSTUDIO/main/studio.py"
    URL_ENGINE_MASTER = "https://github.com/Kolya142/newengine/archive/refs/heads/main.zip"
    
    # Справочник сторонних библиотек (Single-header C libraries)
    LIBRARY_MAP = {
        "stb_image": "https://raw.githubusercontent.com/nothings/stb/master/stb_image.h",
        "miniaudio": "https://raw.githubusercontent.com/mackron/miniaudio/master/miniaudio.h",
        "cJSON": "https://raw.githubusercontent.com/DaveGamble/cJSON/master/cJSON.h",
        "nuklear": "https://raw.githubusercontent.com/Immediate-Mode-UI/Nuklear/master/nuklear.h"
    }

# =============================================================================
# 2. НИЗКОУРОВНЕВЫЕ UI КОМПОНЕНТЫ (ВИДЖЕТЫ)
# =============================================================================

class LogPanel(ctk.CTkTextbox):
    """
    Виджет расширенной консоли. 
    Позволяет выводить сообщения с цветовой разметкой.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        # Устанавливаем моноширинный шрифт для логов
        self.configure(state="disabled", font=("Consolas", 11))
        
        # Регистрация цветовой палитры. 
        # ВАЖНО: В Python 3.14/CustomTkinter нельзя менять шрифт в тегах!
        self.tag_config("error", foreground="#ff5555")    # Красный (ошибки)
        self.tag_config("warning", foreground="#ffb86c")  # Оранжевый (варнинги)
        self.tag_config("success", foreground="#50fa7b")  # Зеленый (успех)
        self.tag_config("info", foreground="#8be9fd")     # Голубой (инфо)
        self.tag_config("dim", foreground="#6272a4")      # Серый (детали)

    def write(self, text: str, tag: Optional[str] = None):
        """Добавляет текст в консоль. Потокобезопасно вызывается через .after()"""
        self.configure(state="normal")
        self.insert("end", text, tag)
        self.see("end") # Автоматический скролл вниз
        self.configure(state="disabled")

    def clear_content(self):
        """Полная очистка консоли."""
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")

class IssuesTable(ctk.CTkFrame):
    """
    Панель со списком проблем сборки. 
    Обертка над Treeview для отображения ошибок в виде таблицы.
    """
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Настройка визуального стиля Treeview (темная тема)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview", 
            background="#1d1d1d", 
            foreground="#ffffff", 
            fieldbackground="#1d1d1d", 
            borderwidth=0, 
            rowheight=26,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading", 
            background="#333333", 
            foreground="#ffffff", 
            borderwidth=1, 
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview", background=[('selected', '#1f538d')])

        # Определение колонок таблицы
        columns = ("File", "Line", "Severity", "Message")
        self.tree = ttk.Treeview(self, columns=columns, show='headings')
        
        self.tree.heading("File", text="Файл")
        self.tree.heading("Line", text="Стр.")
        self.tree.heading("Severity", text="Тип")
        self.tree.heading("Message", text="Сообщение")
        
        self.tree.column("File", width=150, anchor="w")
        self.tree.column("Line", width=60, anchor="center")
        self.tree.column("Severity", width=90, anchor="center")
        self.tree.column("Message", width=450, anchor="w")
        
        # Полоса прокрутки
        self.v_scroll = ctk.CTkScrollbar(self, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.v_scroll.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        self.v_scroll.pack(side="right", fill="y")

    def add_issue(self, file_name: str, line_num: str, severity: str, message: str):
        """Добавляет строку в список проблем."""
        status_icon = "❌" if severity.lower() == "error" else "⚠️"
        self.tree.insert("", "end", values=(file_name, line_num, f"{status_icon} {severity}", message))

    def clear_table(self):
        """Удаляет все записи из таблицы."""
        for row in self.tree.get_children():
            self.tree.delete(row)

class EditorTab(ctk.CTkFrame):
    """
    Класс отдельной вкладки редактора. 
    Управляет состоянием текста одного открытого файла.
    """
    def __init__(self, master, file_path: Path, on_change_callback, **kwargs):
        super().__init__(master, **kwargs)
        self.file_path = file_path
        self.on_change = on_change_callback
        self.last_saved_content = ""
        
        # Текстовое поле редактора
        self.textbox = ctk.CTkTextbox(
            self, 
            font=("Consolas", 13), 
            undo=True, 
            wrap="none", 
            corner_radius=0
        )
        self.textbox.pack(side="left", fill="both", expand=True)
        
        # Полосы прокрутки
        self.v_scroll = ctk.CTkScrollbar(self, orientation="vertical", command=self.textbox.yview)
        self.v_scroll.pack(side="right", fill="y")
        self.textbox.configure(yscrollcommand=self.v_scroll.set)
        
        # Загрузка файла
        self._load_file_data()
        
        # Привязка событий
        self.textbox.bind("<<Modified>>", self._on_content_modified)

    def _load_file_data(self):
        """Читает файл с диска и выводит в поле."""
        try:
            if self.file_path.exists():
                text = self.file_path.read_text(encoding='utf-8', errors='replace')
                self.textbox.insert("1.0", text)
                self.last_saved_content = text
                # Сброс флага изменения
                self.textbox.edit_modified(False)
            else:
                self.textbox.insert("1.0", f"// ОШИБКА: Файл {self.file_path.name} не найден.")
        except Exception as ex:
            self.textbox.insert("1.0", f"// ОШИБКА ЧТЕНИЯ: {str(ex)}")

    def perform_save(self) -> bool:
        """Записывает текущий текст на диск."""
        try:
            text_to_save = self.textbox.get("1.0", "end-1c")
            self.file_path.write_text(text_to_save, encoding='utf-8')
            
            self.last_saved_content = text_to_save
            self.textbox.edit_modified(False)
            # Сообщаем приложению, что файл больше не "грязный"
            self.on_change(self.file_path, False)
            return True
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить {self.file_path.name}:\n{e}")
            return False

    def _on_content_modified(self, event):
        """Вызывается при любом изменении текста в редакторе."""
        if self.textbox.edit_modified():
            current_text = self.textbox.get("1.0", "end-1c")
            # Если текст отличается от сохраненного — ставим пометку
            is_dirty = (current_text != self.last_saved_content)
            self.on_change(self.file_path, is_dirty)
            # Сбрасываем флаг, чтобы ловить следующее изменение
            self.textbox.edit_modified(False)

# =============================================================================
# 3. БЭКЕНД МОДУЛИ (ЛОГИКА И СИСТЕМЫ)
# =============================================================================

class DependencyManager:
    """Анализатор инклудов Си для реализации инкрементальной сборки."""
    
    def extract_includes(self, path: Path) -> List[str]:
        """Парсит файл на наличие строк #include."""
        if not path.exists():
            return []
            
        includes_found = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.read()
                # Ищет форматы: #include "file.h" и #include <file.h>
                pattern = r'#include\s+["<]([^">]+)[">]'
                matches = re.findall(pattern, data)
                for m in matches:
                    includes_found.append(m)
        except Exception as e:
            print(f"[DependencyManager] Ошибка: {e}")
            
        return includes_found

    def check_rebuild_needed(self, source_c: Path, object_o: Path) -> bool:
        """Рекурсивно проверяет дерево зависимостей файла."""
        if not object_o.exists():
            return True
            
        object_mtime = os.path.getmtime(object_o)
        
        # Проверка самого .c файла
        if os.path.getmtime(source_c) > object_mtime:
            return True
            
        # Рекурсивная проверка заголовков .h
        already_visited = set()
        stack = self.extract_includes(source_c)
        
        while stack:
            h_name = stack.pop()
            if h_name in already_visited:
                continue
            already_visited.add(h_name)
            
            # Поиск файла во всех папках инклудов
            search_folders = [Config.INCLUDE_DIR, Config.ASSETS_DIR, source_c.parent]
            for folder in search_folders:
                h_path = folder / h_name
                if h_path.exists():
                    if os.path.getmtime(h_path) > object_mtime:
                        return True
                    # Идем глубже в дерево зависимостей этого хедера
                    stack.extend(self.extract_includes(h_path))
                    break
                    
        return False

class GitEngine:
    """Система интеграции с Git консолью."""
    
    @staticmethod
    def is_installed() -> bool:
        """Проверяет наличие git в системе."""
        try:
            subprocess.run(["git", "--version"], capture_output=True)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def run_command(args: List[str]) -> Tuple[bool, str]:
        """Выполняет команду git и возвращает результат."""
        if not GitEngine.is_installed():
            return False, "Git не найден в переменной PATH."
            
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                cwd=Config.ROOT_DIR,
                encoding='utf-8',
                errors='replace'
            )
            
            success = (result.returncode == 0)
            output_msg = result.stdout if success else result.stderr
            return success, output_msg if output_msg else "ОК."
        except Exception as ex:
            return False, f"Ошибка Git: {str(ex)}"

    @staticmethod
    def get_detailed_status() -> str:
        """Возвращает отчет о статусе репозитория."""
        if not (Config.ROOT_DIR / ".git").exists():
            return "Git репозиторий не инициализирован."
            
        ok, out = GitEngine.run_command(["status", "--short"])
        if ok:
            return out if out.strip() else "Изменений не найдено."
        return f"Ошибка запроса: {out}"

class SnapshotManager:
    """Класс для создания и управления ZIP-бэкапами папки game/."""
    
    @staticmethod
    def create_snapshot(reason: str = "manual") -> str:
        """Упаковывает текущий код игры в архив."""
        if not Config.GAME_DIR.exists():
            return "Ошибка: папка game/ не найдена."
            
        Config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"backup_{timestamp_str}_{reason}.zip"
        zip_full_path = Config.BACKUP_DIR / zip_filename
        
        try:
            with zipfile.ZipFile(zip_full_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_item in Config.GAME_DIR.rglob("*"):
                    if file_item.is_file():
                        # Сохраняем путь относительно корня проекта для верной распаковки
                        archive.write(file_item, file_item.relative_to(Config.ROOT_DIR))
            return zip_filename
        except Exception as e:
            return f"Критическая ошибка ZIP: {str(e)}"

    @staticmethod
    def restore_snapshot(zip_name: str) -> bool:
        """Восстанавливает файлы из бэкапа."""
        archive_path = Config.BACKUP_DIR / zip_name
        if not archive_path.exists():
            return False
            
        try:
            # Безопасность: делаем авто-бэкап перед откатом
            SnapshotManager.create_snapshot("pre_restore_safety")
            
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(Config.ROOT_DIR)
            return True
        except Exception:
            return False

    @staticmethod
    def list_snapshots() -> List[str]:
        """Возвращает список всех существующих архивов бэкапа."""
        if not Config.BACKUP_DIR.exists():
            return []
            
        backups = [f.name for f in Config.BACKUP_DIR.glob("*.zip")]
        backups.sort(reverse=True) # Новые сверху
        return backups

class EngineDocParser:
    """Парсер для автоматического построения списка функций движка из заголовков."""
    
    @staticmethod
    def parse_engine_api() -> Dict[str, List[str]]:
        """Сканирует папку include/ и извлекает прототипы функций."""
        api_map = {}
        if not Config.INCLUDE_DIR.exists():
            return api_map
            
        # Регулярка для Си-функций: Тип Имя(Аргументы);
        func_regex = re.compile(r'^([A-Za-z0-9_]+\s+\*?[A-Za-z0-9_]+)\s*\(([^)]*)\);', re.MULTILINE)
        
        # Фильтры
        forbidden = {'return', 'if', 'else', 'while', 'for', 'switch', 'typedef', 'static', 'extern'}
        allowed_prefixes = ('NE_', 'NScreen_', 'NEnt_', 'RGFW_', 'void', 'int', 'bool', 'u8', 'u32', 'f32', 'f64', 's32')

        for h_file in Config.INCLUDE_DIR.rglob("*.h"):
            try:
                # Читаем текст, игнорируя ошибки кодировки
                text = h_file.read_text(encoding='utf-8', errors='ignore')
                # Удаляем все комментарии
                text = re.sub(r'//.*', '', text)
                text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
                
                matches = func_regex.findall(text)
                if matches:
                    rel_name = str(h_file.relative_to(Config.INCLUDE_DIR))
                    found_funcs = []
                    
                    for m in matches:
                        head = m[0].strip()
                        args = m[1].strip()
                        
                        # Разделяем заголовок на слова для проверки фильтра
                        head_words = head.split()
                        first_word = head_words[0] if head_words else ""
                        
                        if first_word in forbidden or "__" in head:
                            continue
                        if not any(head.startswith(p) for p in allowed_prefixes):
                            continue
                            
                        # Формируем чистую сигнатуру
                        full_signature = f"{head}({args});"
                        found_funcs.append(full_signature)
                        
                    if found_funcs:
                        api_map[rel_name] = found_funcs
            except Exception:
                continue
        return api_map

class ModelAssetProcessor:
    """Класс преобразования .obj файлов в заголовки C."""
    
    @staticmethod
    def process_obj_to_h(input_path: Path) -> str:
        """Разбирает геометрию OBJ и возвращает текст Си-файла."""
        name_prefix = input_path.stem.lower().replace(" ", "_").replace("-", "_")
        
        vertices = []
        faces = []
        
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                        
                    # Координаты вершин
                    if line.startswith('v '):
                        p = line.split()
                        if len(p) >= 4:
                            # Формат структуры {x, y, z}
                            v_str = f"    {{{p[1]}, {p[2]}, {p[3]}}}"
                            vertices.append(v_str)
                            
                    # Индексы граней
                    elif line.startswith('f '):
                        p = line.split()
                        # OBJ индексы 1-based -> C индексы 0-based
                        v_idxs = [str(int(part.split('/')[0]) - 1) for part in p[1:]]
                        
                        # Треугольники
                        if len(v_idxs) == 3:
                            faces.append(f"    {{{v_idxs[0]}, {v_idxs[1]}, {v_idxs[2]}}}")
                        # Квадраты -> 2 треугольника
                        elif len(v_idxs) == 4:
                            faces.append(f"    {{{v_idxs[0]}, {v_idxs[1]}, {v_idxs[2]}}}")
                            faces.append(f"    {{{v_idxs[0]}, {v_idxs[2]}, {v_idxs[3]}}}")

            code = f"#pragma once\n\n"
            code += f"// Сгенерировано NewEngine Studio v{Config.VERSION}\n"
            code += f"// Исходный файл: {input_path.name}\n\n"
            
            code += f"static const NE_Vertex {name_prefix}_v[] = {{\n"
            code += ",\n".join(vertices)
            code += "\n}};\n\n"
            
            code += f"static const NE_Color {name_prefix}_c[] = {{\n"
            white_col = "    {1.0, 1.0, 1.0, 1.0}"
            code += ",\n".join([white_col] * len(vertices))
            code += "\n}};\n\n"
            
            code += f"static const NE_Face {name_prefix}_f[] = {{\n"
            code += ",\n".join(faces)
            code += "\n}};\n\n"
            
            code += f"static const NE_Model {name_prefix}_model = {{\n"
            code += f"    .verteces = {name_prefix}_v,\n"
            code += f"    .colors = {name_prefix}_c,\n"
            code += f"    .faces = {name_prefix}_f,\n"
            code += f"    .face_count = {len(faces)}\n"
            code += "};\n"
            
            return code
            
        except Exception as e:
            return f"ОШИБКА ПРИ ОБРАБОТКЕ OBJ: {str(e)}"

# =============================================================================
# 4. СИСТЕМА СБОРКИ (MULTITHREADED CORE)
# =============================================================================

class BuildCore:
    """Ядро компиляции проекта. Запускает GCC в параллельных потоках."""
    def __init__(self, app):
        self.app = app
        self.dep_manager = DependencyManager()
        # Пул потоков: по одному потоку на каждое ядро процессора
        self.thread_executor = ThreadPoolExecutor(max_workers=os.cpu_count())
        self.active_game_process: Optional[subprocess.Popen] = None
        self.is_currently_building = False
        # Регулярка для захвата ошибок GCC
        self.gcc_regex = re.compile(r"^(.*):(\d+):(\d+): (error|warning|note): (.*)$")

    def run_compilation_async(self, profile: str, auto_launch: bool = False):
        """Запуск процесса сборки в фоновом режиме."""
        if self.is_currently_building:
            return
        
        # Создаем рабочий поток для сборки
        build_thread = threading.Thread(
            target=self._compilation_process_entry, 
            args=(profile, auto_launch), 
            daemon=True
        )
        build_thread.start()

    def _compile_single_unit(self, src: Path, flags: List[str]) -> Optional[str]:
        """Метод для компиляции одного файла. Выполняется параллельно."""
        rel_path = src.relative_to(Config.ROOT_DIR)
        # Формируем имя .o файла: bin/obj/path_to_file.o
        obj_name = str(rel_path).replace(os.sep, "_").replace(".c", ".o")
        obj_full_path = Config.OBJ_DIR / obj_name
        
        # Проверка: нужно ли пересобирать? (Smart Dependencies)
        if not self.dep_manager.check_rebuild_needed(src, obj_full_path):
            return str(obj_full_path)

        # Вывод в консоль через очередь главного потока
        self.app.log_to_console(f"Компиляция: {rel_path}\n", "dim")
        
        # Формирование команды GCC
        cmd = [Config.COMPILER, "-c", str(src), "-o", str(obj_full_path)] + flags
        
        # Подавление main в ядре движка
        if "engine" in src.parts and src.name == "main.c":
            cmd.append("-Dmain=__engine_dummy_main")
            
        process = subprocess.run(cmd, capture_output=True, text=True, cwd=Config.ROOT_DIR)
        
        if process.stderr:
            self.app.on_compiler_output_received(process.stderr)
            
        if process.returncode == 0:
            return str(obj_full_path)
        return None

    def _compilation_process_entry(self, profile: str, auto_run_game: bool):
        """Основной поток управления этапами сборки."""
        self.is_currently_building = True
        self.app.set_ui_busy_state(True)
        self.app.clear_console()
        self.app.clear_issues_list()
        
        start_time_mark = time.time()
        self.app.log_to_console(f"--- НАЧАЛО СБОРКИ ПРОЕКТА [{profile}] ---\n", "info")
        
        # Создание структуры папок
        Config.OBJ_DIR.mkdir(parents=True, exist_ok=True)
        Config.BIN_DIR.mkdir(parents=True, exist_ok=True)
        
        # Сбор списка файлов
        target_sources = []
        for d in [Config.ENGINE_DIR, Config.GAME_DIR]:
            if d.exists():
                target_sources.extend(list(d.rglob("*.c")))

        # Настройка флагов GCC
        is_debug = "Debug" in profile
        optimization_flags = ["-g", "-O0"] if is_debug else ["-O3", "-s"]
        
        base_flags = [
            f"-I{Config.INCLUDE_DIR}", 
            f"-I{Config.ASSETS_DIR}", 
            "-Wall"
        ] + optimization_flags

        # ЗАПУСК КОМПИЛЯЦИИ
        self.app.log_to_console(f"Задействовано ядер процессора: {os.cpu_count()}\n", "dim")
        compilation_results = list(self.thread_executor.map(
            lambda s: self._compile_single_unit(s, common_flags if 'common_flags' in locals() else base_flags), 
            target_sources
        ))
        
        # Анализ результатов
        if None in compilation_results:
            self.app.log_to_console("\nСБОЙ: Обнаружены ошибки в коде. См. вкладку Проблемы.\n", "error")
        else:
            # ЭТАП ЛИНКОВКИ
            self.app.log_to_console("\nЛинковка всех модулей в .exe...\n", "info")
            output_binary = Config.BIN_DIR / Config.OUTPUT_BINARY
            
            libs = ["-lopengl32", "-lglu32", "-lgdi32", "-lwinmm"]
            if platform.system() == "Linux":
                libs = ["-lGL", "-lGLU", "-lm", "-lX11", "-lXrandr"]
            
            if not is_debug and platform.system() == "Windows":
                libs.append("-mwindows")
            
            link_cmd = [Config.COMPILER] + compilation_results + ["-o", str(output_binary)] + base_flags + libs
            
            res_linking = subprocess.run(link_cmd, capture_output=True, text=True, cwd=Config.ROOT_DIR)
            
            if res_linking.returncode == 0:
                duration_secs = time.time() - start_time_mark
                self.app.log_to_console(f"УСПЕХ! Сборка завершена за {duration_secs:.2f} сек.\n", "success")
                if auto_run_game:
                    self.execute_game()
            else:
                self.app.on_compiler_output_received(res_linking.stderr)
                self.app.log_to_console("Ошибка на этапе линковки.\n", "error")

        self.is_currently_building = False
        self.app.set_ui_busy_state(False)

    def execute_game(self):
        """Запуск игры как отдельного процесса."""
        binary_path = Config.BIN_DIR / Config.OUTPUT_BINARY
        if not binary_path.exists():
            self.app.log_to_console("Файл игры не найден. Соберите проект.\n", "error")
            return
            
        # Завершаем старую копию
        if self.active_game_process and self.active_game_process.poll() is None:
            self.active_game_process.terminate()
            
        try:
            self.active_game_process = subprocess.Popen([str(binary_path)], cwd=Config.ROOT_DIR)
            self.app.log_to_console("Процесс игры запущен успешно.\n", "success")
        except Exception as e:
            self.app.log_to_console(f"Ошибка запуска: {str(e)}\n", "error")

# =============================================================================
# 5. ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ STUDIO (IDE)
# =============================================================================

class StudioApp(ctk.CTk):
    """Главный класс IDE в стиле VS Code."""
    def __init__(self):
        super().__init__()
        
        # Настройка окна
        self.title(f"{Config.APP_NAME} v{Config.VERSION}")
        self.geometry("1300x900")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Инициализация систем
        self.build_core = BuildCore(self)
        self.prof_var = ctk.StringVar(value="Отладка (Debug)")
        self.hot_reload_enabled = False
        self.mtime_store = {}
        self.open_tabs_map: Dict[str, EditorTab] = {}

        # ГЛАВНЫЙ МАКЕТ (Сетка 1x3)
        self.grid_columnconfigure(0, weight=0) # Activity Bar
        self.grid_columnconfigure(1, weight=0) # Side Bar
        self.grid_columnconfigure(2, weight=1) # Editor
        self.grid_rowconfigure(0, weight=1)

        # Создание интерфейса
        self._setup_activity_bar_ui()
        self._setup_sidebar_ui()
        self._setup_main_area_ui()
        
        # Горячие клавиши
        self.bind("<Control-s>", lambda event: self.ui_save_active_tab())

    # --- МЕТОДЫ ПОСТРОЕНИЯ ИНТЕРФЕЙСА ---

    def _setup_activity_bar_ui(self):
        """Левая панель с иконками быстрого переключения разделов."""
        self.activity_bar = ctk.CTkFrame(self, width=55, corner_radius=0, fg_color="#333333")
        self.activity_bar.grid(row=0, column=0, sticky="nsew")
        
        icon_data = [
            ("📁", "Проводник"),
            ("🌿", "Git"),
            ("📖", "API Справка"),
            ("⚙️", "Система"),
            ("📦", "Ассеты")
        ]
        
        for icon_char, tab_name in icon_data:
            btn = ctk.CTkButton(
                self.activity_bar, text=icon_char, width=45, height=45,
                fg_color="transparent", hover_color="#444444",
                command=lambda n=tab_name: self.ui_sidebar_tabs.set(n)
            )
            btn.pack(pady=10, padx=5)

    def _setup_sidebar_ui(self):
        """Боковая панель для детальных инструментов."""
        self.sidebar_container = ctk.CTkFrame(self, width=260, corner_radius=0)
        self.sidebar_container.grid(row=0, column=1, sticky="nsew")
        
        self.ui_sidebar_tabs = ctk.CTkTabview(self.sidebar_container, width=260)
        self.ui_sidebar_tabs.pack(fill="both", expand=True)
        # Скрываем заголовки вкладок
        self.ui_sidebar_tabs._segmented_button.grid_forget()

        # Инициализация контента каждой вкладки сайдбара
        self._init_explorer_tab_content(self.ui_sidebar_tabs.add("Проводник"))
        self._init_git_tab_content(self.ui_sidebar_tabs.add("Git"))
        self._init_api_tab_content(self.ui_sidebar_tabs.add("API Справка"))
        self._init_system_tab_content(self.ui_sidebar_tabs.add("Система"))
        self._init_assets_tab_content(self.ui_sidebar_tabs.add("Ассеты"))

    def _setup_main_area_ui(self):
        """Центральная рабочая зона: Редактор + Панель консоли."""
        self.work_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.work_frame.grid(row=0, column=2, sticky="nsew")
        
        # Сетка: редактор (3 доли) / консоль (1 доля)
        self.work_frame.grid_rowconfigure(0, weight=3)
        self.work_frame.grid_rowconfigure(1, weight=1)
        self.work_frame.grid_columnconfigure(0, weight=1)

        # ТАБЫ РЕДАКТОРА
        self.editor_tab_view = ctk.CTkTabview(self.work_frame)
        self.editor_tab_view.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))

        # НИЖНЯЯ ПАНЕЛЬ (Консоль + Проблемы)
        self.ui_bottom_panel = ctk.CTkTabview(self.work_frame, height=220)
        self.ui_bottom_panel.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Вкладка логов
        log_tab = self.ui_bottom_panel.add("Консоль")
        self.console_view = LogPanel(log_tab)
        self.console_view.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Вкладка списка проблем
        err_tab = self.ui_bottom_panel.add("Проблемы")
        self.issues_view = IssuesTable(err_tab)
        self.issues_view.pack(fill="both", expand=True)

    # --- МЕТОДЫ НАПОЛНЕНИЯ ВКЛАДОК САЙДБАРА ---

    def _init_explorer_tab_content(self, tab):
        ctk.CTkLabel(tab, text="ПРОВОДНИК ПРОЕКТА", font=("Arial", 12, "bold")).pack(pady=10)
        
        # Быстрые кнопки сборки
        f_top = ctk.CTkFrame(tab)
        f_top.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(f_top, text="🔨 Build", width=80, command=lambda: self.build_core.run_compilation_async(self.prof_var.get())).pack(side="left", padx=2)
        ctk.CTkButton(f_top, text="🚀 Run", width=80, fg_color="#2d8a2d", command=self.build_core.execute_game).pack(side="left", padx=2)
        
        ctk.CTkOptionMenu(tab, values=["Debug", "Release"], variable=self.prof_var, height=25).pack(fill="x", padx=5, pady=5)

        # Прокручиваемый список файлов
        self.ui_file_tree = ctk.CTkScrollableFrame(tab)
        self.ui_file_tree.pack(fill="both", expand=True, pady=10)
        self.ui_refresh_file_list()

    def _init_git_tab_content(self, tab):
        ctk.CTkLabel(tab, text="УПРАВЛЕНИЕ GIT", font=("Arial", 12, "bold")).pack(pady=10)
        self.ui_git_status_txt = ctk.CTkTextbox(tab, height=250, font=("Consolas", 10))
        self.ui_git_status_txt.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(tab, text="Обновить статус", command=self.on_git_refresh).pack(pady=5, padx=20)
        ctk.CTkButton(tab, text="Commit Изменений", command=self.on_git_commit).pack(pady=5, padx=20)
        ctk.CTkButton(tab, text="Push на GitHub", command=lambda: self.on_git_action_async(["push"])).pack(pady=5, padx=20)

    def _init_api_tab_content(self, tab):
        ctk.CTkLabel(tab, text="ENGINE API", font=("Arial", 12, "bold")).pack(pady=10)
        self.ui_api_scroll = ctk.CTkScrollableFrame(tab)
        self.ui_api_scroll.pack(fill="both", expand=True, padx=5)
        ctk.CTkButton(tab, text="Просканировать", command=self.on_ui_api_scan_exec).pack(pady=10)

    def _init_system_tab_content(self, tab):
        ctk.CTkLabel(tab, text="СИСТЕМА И БЭКАПЫ", font=("Arial", 12, "bold")).pack(pady=10)
        
        # Снимки
        ctk.CTkLabel(tab, text="Резервные копии:").pack(pady=(10, 0))
        self.ui_snapshot_dropdown = ctk.CTkOptionMenu(tab, values=["Список пуст"])
        self.ui_snapshot_dropdown.pack(pady=5, padx=10)
        
        ctk.CTkButton(tab, text="Создать снимок", command=self.on_ui_snap_create_exec).pack(pady=5, padx=20)
        ctk.CTkButton(tab, text="Восстановить проект", fg_color="orange", command=self.on_ui_snap_restore_exec).pack(pady=5, padx=20)
        
        # Обслуживание
        ctk.CTkLabel(tab, text="Обновления IDE/Core:").pack(pady=(20, 0))
        ctk.CTkButton(tab, text="Обновить Studio.py", command=self.on_ui_update_studio_exec).pack(pady=5, padx=20)
        ctk.CTkButton(tab, text="Обновить Движок", command=self.on_ui_update_engine_exec).pack(pady=5, padx=20)
        self.ui_refresh_snap_dropdown()

    def _init_assets_tab_content(self, tab):
        ctk.CTkLabel(tab, text="АССЕТЫ ПРОЕКТА", font=("Arial", 12, "bold")).pack(pady=10)
        ctk.CTkButton(tab, text="Импорт .obj модели", command=self.on_asset_import_wizard).pack(pady=10, padx=20)
        
        ctk.CTkLabel(tab, text="Установка библиотек:").pack(pady=(20, 5))
        for lib in Config.LIBRARY_MAP:
            ctk.CTkButton(tab, text=f"Install {lib}", command=lambda l=lib: self.on_ui_lib_install_exec(l)).pack(pady=2, padx=20)

    # --- МЕТОДЫ ЛОГИКИ ИНТЕРФЕЙСА ---

    def ui_refresh_file_list(self):
        """Обновляет дерево файлов в проводнике."""
        for widget in self.ui_file_tree.winfo_children():
            widget.destroy()
            
        for folder_path in [Config.ENGINE_DIR, Config.GAME_DIR]:
            if not folder_path.exists(): continue
            ctk.CTkLabel(self.ui_file_tree, text=f"📂 {folder_path.name}", font=("Arial", 11, "bold"), text_color="gray").pack(anchor="w", padx=2)
            
            files = sorted(list(folder_path.glob("*.[ch]")))
            for f in files:
                btn = ctk.CTkButton(
                    self.ui_file_tree, text=f"  📄 {f.name}", anchor="w",
                    fg_color="transparent", hover_color="#3d3d3d",
                    height=22, font=("Arial", 11),
                    command=lambda file_obj=f: self.on_open_file_in_editor(file_obj)
                )
                btn.pack(fill="x")

    def on_open_file_in_editor(self, path: Path):
        """Открывает файл в новой вкладке редактора."""
        key = str(path)
        if key in self.open_tabs_map:
            self.editor_tab_view.set(path.name)
            return

        tab_id = path.name
        self.editor_tab_view.add(tab_id)
        
        editor_frame = EditorTab(
            self.editor_tab_view.tab(tab_id), 
            path, 
            self.on_file_dirty_change
        )
        editor_frame.pack(fill="both", expand=True)
        
        self.open_tabs_map[key] = editor_frame
        self.editor_tab_view.set(tab_id)

    def on_file_dirty_change(self, path: Path, is_changed: bool):
        """Индикация несохраненных изменений."""
        pass

    def ui_save_active_tab(self):
        """Сохранение файла в активной вкладке редактора."""
        active_name = self.editor_tab_view.get()
        for tab in self.open_tabs_map.values():
            if tab.file_path.name == active_name:
                if tab.perform_save():
                    self.log_to_console(f"Сохранено: {tab.file_path.name}\n", "success")
                break

    # --- BRIDGE: ВЫВОД ИЗ БЭКЕНДА ---

    def log_to_console(self, message: str, tag: Optional[str] = None):
        """Потокобезопасный вывод в консоль."""
        self.after(0, lambda: self.console_view.write(message, tag))

    def clear_console(self):
        """Очистка панели логов."""
        self.after(0, self.console_view.clear_content)

    def clear_issues_list(self):
        """Очистка таблицы ошибок."""
        self.after(0, self.issues_view.clear_table)

    def on_compiler_output_received(self, text_output: str):
        """Парсит ошибки GCC и заносит их в таблицу Проблемы."""
        for line in text_output.splitlines():
            match = self.build_core.gcc_regex.match(line)
            if match:
                f, ln, col, sev, msg = match.groups()
                # Добавляем в таблицу
                self.after(0, lambda f=f, l=ln, s=sev, m=msg: self.issues_view.add_issue(f, l, s, m))
                # Выводим в лог с цветом
                self.log_to_console(line + "\n", "error" if sev == "error" else "warning")
            else:
                self.log_to_console(line + "\n")

    # --- ОБРАБОТЧИКИ СОБЫТИЙ ---

    def on_git_refresh(self):
        self.ui_git_status_txt.delete("1.0", "end")
        self.ui_git_status_txt.insert("end", GitEngine.get_detailed_status())

    def on_git_commit(self):
        msg = simpledialog.askstring("Git Commit", "Что вы изменили?")
        if msg:
            def task():
                GitEngine.run_command(["add", "."])
                ok, out = GitEngine.run_command(["commit", "-m", msg])
                self.log_to_console(out + "\n", "success" if ok else "error")
                self.after(0, self.on_git_refresh)
            threading.Thread(target=task, daemon=True).start()

    def on_git_action_async(self, args):
        def task():
            self.log_to_console(f"Git {' '.join(args)}...\n", "info")
            ok, out = GitEngine.run_command(args)
            self.log_to_console(out + "\n", "success" if ok else "error")
            self.after(0, self.on_git_refresh)
        threading.Thread(target=task, daemon=True).start()

    def on_ui_api_scan_exec(self):
        api = EngineDocParser.parse_engine_api()
        for w in self.ui_api_scroll.winfo_children(): w.destroy()
        if not api:
            ctk.CTkLabel(self.ui_api_scroll, text="API не найдено.").pack()
            return
        for file_name, funcs in api.items():
            ctk.CTkLabel(self.ui_api_scroll, text=file_name, font=("Arial", 11, "bold"), text_color="lightblue").pack(anchor="w")
            for f in funcs:
                ctk.CTkLabel(self.ui_api_scroll, text=f" • {f}", font=("Consolas", 10), anchor="w").pack(anchor="w", padx=15)

    def on_ui_snap_create_exec(self):
        res = SnapshotManager.create_snapshot("manual")
        self.log_to_console(f"Бэкап создан: {res}\n", "success")
        self.ui_refresh_snap_dropdown()

    def on_ui_snap_restore_exec(self):
        name = self.ui_snapshot_dropdown.get()
        if name == "Список пуст": return
        if messagebox.askyesno("Confirm", f"Откатить проект к {name}?"):
            if SnapshotManager.restore_snapshot(name):
                self.log_to_console("Успешно восстановлено.\n", "success")
                self.ui_refresh_snap_dropdown()

    def ui_refresh_snap_dropdown(self):
        snaps = SnapshotManager.list_snapshots()
        if snaps:
            self.ui_snapshot_dropdown.configure(values=snaps)
            self.ui_snapshot_dropdown.set(snaps[0])

    def on_ui_lib_install_exec(self, lib_name):
        def task():
            self.log_to_console(f"Загрузка {lib_name}.h...\n", "info")
            try:
                url = Config.LIBRARY_MAP[lib_name]
                with urllib.request.urlopen(url) as r:
                    Config.THIRDPARTY_DIR.mkdir(parents=True, exist_ok=True)
                    (Config.THIRDPARTY_DIR / f"{lib_name}.h").write_bytes(r.read())
                self.log_to_console(f"Библиотека {lib_name} установлена.\n", "success")
            except Exception as e:
                self.log_to_console(f"Ошибка установки: {e}\n", "error")
        threading.Thread(target=task, daemon=True).start()

    def on_asset_import_wizard(self):
        p = ctk.filedialog.askopenfilename(filetypes=[("OBJ Models", "*.obj")])
        if p:
            def task():
                self.log_to_console(f"Конвертация {Path(p).name}...\n", "info")
                h_code = ModelAssetProcessor.process_obj_to_h(Path(p))
                Config.ASSETS_DIR.mkdir(exist_ok=True)
                (Config.ASSETS_DIR / f"{Path(p).stem}.h").write_text(h_code, encoding="utf-8")
                self.log_to_console("Конвертация завершена.\n", "success")
            threading.Thread(target=task, daemon=True).start()

    def on_ui_update_studio_exec(self):
        def task():
            try:
                with urllib.request.urlopen(Config.URL_STUDIO_SOURCE) as r:
                    with open("studio.py", "wb") as f: f.write(r.read())
                self.log_to_console("Studio обновлена.\n", "success")
            except Exception as e: self.log_to_console(f"Error: {e}\n", "error")
        threading.Thread(target=task, daemon=True).start()

    def on_ui_update_engine_exec(self):
        def task():
            SnapshotManager.create_snapshot("pre_update")
            try:
                with urllib.request.urlopen(Config.URL_ENGINE_MASTER) as r:
                    with zipfile.ZipFile(io.BytesIO(r.read())) as z:
                        root = z.namelist()[0].split('/')[0]
                        for f in z.namelist():
                            if any(x in f for x in ['engine/', 'include/']):
                                rel = f[len(root)+1:]; dest = Config.ROOT_DIR / rel
                                if f.endswith('/'): dest.mkdir(parents=True, exist_ok=True)
                                else: dest.write_bytes(z.read(f))
                self.log_to_console("Engine обновлен!\n", "success")
            except Exception as e: self.log_to_console(f"Err: {e}\n", "error")
        threading.Thread(target=task, daemon=True).start()

    def on_toggle_hot_reload(self):
        self.hot_reload_enabled = self.sw_auto.get()
        if self.hot_reload_enabled:
            threading.Thread(target=self._hot_reload_loop, daemon=True).start()

    def _hot_reload_loop(self):
        while self.hot_reload_enabled:
            found = False
            for d in [Config.ENGINE_DIR, Config.GAME_DIR]:
                if d.exists():
                    for f in d.rglob("*.c"):
                        mt = os.path.getmtime(f)
                        if str(f) not in self.mtime_store or mt > self.mtime_store[str(f)]:
                            self.mtime_store[str(f)] = mt; found = True
            if found:
                self.after(0, lambda: self.build_core.run_compilation_async(self.prof_var.get(), True))
            time.sleep(1.5)

    def set_ui_busy_state(self, is_busy: bool):
        """Отключает кнопки во время сборки."""
        state = "disabled" if is_busy else "normal"
        self.btn_compile.configure(state=state)
        self.btn_br.configure(state=state)

# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================

if __name__ == "__main__":
    try:
        app = StudioApp()
        app.mainloop()
    except Exception as fatal_e:
        print(f"Критическая ошибка запуска: {fatal_e}")