import flet as ft
import sqlite3
from datetime import datetime
import os
from flet import FilePickerResultEvent
import sys


def resource_path(relative_path):
    """Return absolute path to resource, works for dev and PyInstaller onefile."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

class DatabaseTracker:
    def __init__(self):
        self.db_path = "tracker.db"
        self.init_database()
        self.current_table = "builds"
        
    def init_database(self):
        """Initialize SQLite database with all tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS builds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                manifest_id TEXT,
                year INTEGER,
                season TEXT,
                crack_type TEXT,
                link TEXT,
                md5 TEXT,
                description TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version TEXT,
                link TEXT,
                description TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cheats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT,
                link TEXT,
                description TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT,
                description TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS preserved (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT,
                description TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

        # ensure expected columns exist (migrate old DBs if necessary)
        try:
            for tbl in ["builds", "tools", "cheats", "downloaders", "preserved"]:
                self.ensure_table_columns(tbl)
        except Exception as e:
            print(f"Error during post-init migration: {e}")

    def get_table_columns(self, table_name):
        """Return a set of existing column names for a table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            cols = {row[1] for row in cursor.fetchall()}  # name is at index 1
            return cols
        finally:
            conn.close()

    def ensure_table_columns(self, table_name):
        """Ensure the table has the expected columns; add any missing ones.

        This will perform non-destructive ALTER TABLE ADD COLUMN operations for
        any missing columns. For safety, NOT NULL constraints are omitted when
        adding columns to existing tables.
        """
        expected_schema = {
            "builds": [
                ("name", "TEXT"),
                ("manifest_id", "TEXT"),
                ("year", "INTEGER"),
                ("season", "TEXT"),
                ("crack_type", "TEXT"),
                ("link", "TEXT"),
                ("md5", "TEXT"),
                ("description", "TEXT"),
            ],
            "tools": [
                ("name", "TEXT"),
                ("version", "TEXT"),
                ("link", "TEXT"),
                ("description", "TEXT"),
            ],
            "cheats": [
                ("name", "TEXT"),
                ("type", "TEXT"),
                ("link", "TEXT"),
                ("description", "TEXT"),
            ],
            "downloaders": [
                ("name", "TEXT"),
                ("link", "TEXT"),
                ("description", "TEXT"),
            ],
            "preserved": [
                ("name", "TEXT"),
                ("link", "TEXT"),
                ("description", "TEXT"),
            ],
        }

        if table_name not in expected_schema:
            return

        expected_cols = [c[0] for c in expected_schema[table_name]]
        expected_full_set = set(["id"] + expected_cols)
        existing = self.get_table_columns(table_name)

        # If existing columns exactly match expected, nothing to do
        if existing == expected_full_set:
            return

        # If expected columns are a subset of existing, we can safely add missing ones
        if set(expected_cols).issubset(existing):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                for col_name, col_type in expected_schema[table_name]:
                    if col_name not in existing:
                        sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        try:
                            cursor.execute(sql)
                            print(f"Added missing column '{col_name}' to table '{table_name}'")
                        except Exception as ex:
                            print(f"Failed to add column {col_name} to {table_name}: {ex}")
                conn.commit()
            finally:
                conn.close()
            return

        # Otherwise, perform a safer migration: recreate the table with the expected schema
        self.migrate_table_schema(table_name, expected_schema[table_name])

    def migrate_table_schema(self, table_name, expected_columns):
        """Recreate table to match expected_columns and copy data for matching columns.

        expected_columns: list of (name, type)
        """
        try:
            existing = self.get_table_columns(table_name)
        except Exception as e:
            print(f"Could not read existing columns for {table_name}: {e}")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        temp_name = f"{table_name}_old_migrate"
        try:
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN")
            # rename current table
            cursor.execute(f"ALTER TABLE {table_name} RENAME TO {temp_name}")

            # build create statement
            cols_sql = ", ".join([f"{name} {typ}" for name, typ in expected_columns])
            create_sql = f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})"
            cursor.execute(create_sql)

            # build insert/select mapping
            # intelligent mapping: try exact, case-insensitive, normalized, and simple-alias matches
            def normalize(col):
                return ''.join(ch.lower() for ch in str(col) if ch.isalnum())

            existing_list = list(existing)
            # build lookup maps
            existing_lower = {col.lower(): col for col in existing_list}
            existing_norm = {normalize(col): col for col in existing_list}

            # simple alias map (normalized form -> expected normalized)
            alias_map = {
                'manifestid': 'manifest_id',
                'manifest': 'manifest_id',
                'md5sum': 'md5',
                'md5hash': 'md5',
                'crack': 'crack_type',
            }

            select_exprs = []
            insert_cols = []
            for expected_name, _ in expected_columns:
                insert_cols.append(expected_name)
                mapped = None

                # 1) exact
                if expected_name in existing:
                    mapped = expected_name
                # 2) case-insensitive
                elif expected_name.lower() in existing_lower:
                    mapped = existing_lower[expected_name.lower()]
                else:
                    # 3) normalized match
                    exp_norm = normalize(expected_name)
                    if exp_norm in existing_norm:
                        mapped = existing_norm[exp_norm]
                    else:
                        # 4) alias matches (normalized)
                        if exp_norm in alias_map:
                            alias_norm = normalize(alias_map[exp_norm])
                            if alias_norm in existing_norm:
                                mapped = existing_norm[alias_norm]
                        # 5) fuzzy contains/starts-with attempts
                        if not mapped:
                            for norm_col, orig_col in existing_norm.items():
                                # if expected normalized is substring of existing normalized
                                if exp_norm and (exp_norm in norm_col or norm_col in exp_norm):
                                    mapped = orig_col
                                    break

                if mapped:
                    # quote column name in case it has weird characters
                    select_exprs.append(f'"{mapped}"')
                else:
                    select_exprs.append("NULL")

            # handle id if it exists in old table
            if 'id' in existing:
                insert_cols_sql = "id, " + ", ".join(insert_cols)
                select_sql = "id, " + ", ".join(select_exprs)
            else:
                insert_cols_sql = ", ".join(insert_cols)
                select_sql = ", ".join(select_exprs)

            cursor.execute(f"INSERT INTO {table_name} ({insert_cols_sql}) SELECT {select_sql} FROM {temp_name}")
            cursor.execute(f"DROP TABLE {temp_name}")
            cursor.execute("COMMIT")
            print(f"Migrated table {table_name} to expected schema")
        except Exception as e:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            print(f"Migration failed for {table_name}: {e}")
        finally:
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass
            conn.close()

    def get_table_data(self, table_name):
        """Get all data from specified table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name}")
        data = cursor.fetchall()
        conn.close()
        return data

    def add_record(self, table_name, data):
        """Add a new record to specified table"""
        try:
            # make sure the table has expected columns (migrate if needed)
            try:
                self.ensure_table_columns(table_name)
            except Exception as _:
                # don't block adding record if migration check fails; attempt insert and let sqlite raise
                pass
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if table_name == "builds":
                # for builds table, make sure you have all 8 values even if some are empty
                while len(data) < 8:
                    data.append("")  # pad with empty strings
                cursor.execute('''
                    INSERT INTO builds (name, manifest_id, year, season, crack_type, link, md5, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', tuple(data))  # convert to tuple for sqlite
            elif table_name == "tools":
                cursor.execute('''
                    INSERT INTO tools (name, version, link, description)
                    VALUES (?, ?, ?, ?)
                ''', data)
            elif table_name == "cheats":
                cursor.execute('''
                    INSERT INTO cheats (name, type, link, description)
                    VALUES (?, ?, ?, ?)
                ''', data)
            elif table_name == "downloaders":
                cursor.execute('''
                    INSERT INTO downloaders (name, link, description)
                    VALUES (?, ?, ?)
                ''', data)
            elif table_name == "preserved":
                cursor.execute('''
                    INSERT INTO preserved (name, link, description)
                    VALUES (?, ?, ?)
                ''', data)
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error in add_record: {str(e)}")  # for debugging stuff
            raise e

    def delete_record(self, table_name, record_id):
        """Delete a record from specified table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()

def main(page: ft.Page):
    page.title = "database | 6"  # def title
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1400
    page.window_height = 900
    page.bgcolor = "#000000"
    # placeholder for db instance so nested functions can declare nonlocal db
    db = None

    # setup file pickers for import/export
    import_file_picker = ft.FilePicker()
    export_file_picker = ft.FilePicker()
    page.overlay.extend([import_file_picker, export_file_picker])

    def pick_files_result(e: ft.FilePickerResultEvent):
        nonlocal db
        if e.files and len(e.files) > 0:
            file_path = e.files[0].path
            if file_path.lower().endswith('.db'):
                try:
                    import shutil
                    shutil.copy2(file_path, db.db_path)
                    # reinitialize db instance so migrations and schema refresh are applied
                    try:
                        db = DatabaseTracker()
                    except Exception:
                        pass
                    update_entries()
                    show_snackbar("Database imported successfully")
                except Exception as ex:
                    show_snackbar(f"Import failed: {str(ex)}", ft.Colors.RED_400)
            else:
                show_snackbar("Please select a .db file", ft.Colors.RED_400)
        settings_dialog.open = False
        page.update()

    def save_file_result(e: ft.FilePickerResultEvent):
        if e.path:
            try:
                save_path = e.path if e.path.lower().endswith('.db') else e.path + '.db'
                import shutil
                shutil.copy2(db.db_path, save_path)
                show_snackbar(f"Database exported successfully")
            except Exception as ex:
                show_snackbar(f"Export failed: {str(ex)}", ft.Colors.RED_400)
        settings_dialog.open = False
        page.update()

    import_file_picker.on_result = pick_files_result
    export_file_picker.on_result = save_file_result

    def handle_import_result(e: FilePickerResultEvent):
        nonlocal db
        if e.files and len(e.files) > 0:
            try:
                import shutil
                shutil.copy2(e.files[0].path, db.db_path)
                # reinitialize db instance so migrations and schema refresh are applied
                try:
                    db = DatabaseTracker()
                except Exception:
                    pass
                update_entries()
                show_snackbar("Database imported successfully")
            except Exception as ex:
                show_snackbar(f"Import failed: {str(ex)}", ft.Colors.RED_400)
        settings_dialog.open = False
        page.update()

    def handle_export_result(e: FilePickerResultEvent):
        if e.path:
            try:
                import shutil
                shutil.copy2(db.db_path, e.path)
                show_snackbar(f"Database exported successfully")
            except Exception as ex:
                show_snackbar(f"Export failed: {str(ex)}", ft.Colors.RED_400)
        settings_dialog.open = False
        page.update()
    
    # snackbar helper
    def show_snackbar(message, color=ft.Colors.GREEN):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()
        
    def change_theme(theme_name):
        themes = {
            "dark_blue": {"primary": "#191970", "secondary": "#1E3A8A"},
            "midnight_purple": {"primary": "#2D1B69", "secondary": "#4B0082"},
            "dark_red": {"primary": "#8B0000", "secondary": "#A52A2A"},
            "forest_dark": {"primary": "#2F4F4F", "secondary": "#3B5323"},
            "ocean_dark": {"primary": "#1A3C40", "secondary": "#204E4A"}
        }
        
        if theme_name in themes:
            theme = themes[theme_name]
            # update sidebar colour
            sidebar_container.bgcolor = theme["primary"]
            # update active tab colour
            for btn in nav_buttons:
                if btn["container"].bgcolor:
                    btn["container"].bgcolor = theme["secondary"]
            # update form dialog
            form_dialog.bgcolor = theme["primary"]
            # update settings dialog
            settings_dialog.bgcolor = theme["primary"]
            # persist setting
            try:
                import json
                with open("db6_settings.json", "w", encoding="utf-8") as f:
                    json.dump({"theme": theme_name}, f)
            except Exception as e:
                print(f"Error saving theme setting: {e}")
            page.update()

    def perform_clear_all_data():
        """Perform actual DB deletions and update UI. Returns summary string."""
        try:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                deleted_info = []
                for (table_name,) in tables:
                    if table_name == 'sqlite_sequence':
                        continue
                    try:
                        try:
                            before = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                        except Exception:
                            before = None
                        cursor.execute(f"DELETE FROM {table_name}")
                        try:
                            after = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                        except Exception:
                            after = None
                        deleted_info.append((table_name, before, after))
                    except Exception as ex:
                        print(f"Error deleting from {table_name}: {ex}")

                try:
                    cursor.execute("DELETE FROM sqlite_sequence")
                except Exception as e:
                    print(f"Error resetting sqlite_sequence: {e}")

                conn.commit()

            update_entries()

            summary_lines = []
            for t, b, a in deleted_info:
                if b is None:
                    summary_lines.append(f"{t}: cleared")
                else:
                    summary_lines.append(f"{t}: {b} -> {a}")
            summary = ", ".join(summary_lines) if summary_lines else "No user tables found"
            print(f"perform_clear_all_data summary: {summary}")
            show_snackbar(f"All data cleared: {summary}", ft.Colors.RED_400)
            return summary
        except Exception as e:
            print(f"perform_clear_all_data error: {e}")
            show_snackbar(f"Error clearing data: {str(e)}", ft.Colors.RED_400)
            page.update()
            return None
            
    def confirm_clear_data(e=None):
        # close settings dialog if open
        try:
            settings_dialog.open = False
            page.update()
        except Exception:
            pass

        # create confirmation dialog
        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Confirm Data Deletion"),
            content=ft.Text("Are you sure you want to clear all data? This cannot be undone."),
            actions=[],
        )

        # define handlers
        def close_confirm(e=None):
            confirm_dialog.open = False
            page.update()

        def clear_all_data(e=None):
            nonlocal db
            # close confirm and settings dialogs
            confirm_dialog.open = False
            page.update()
            try:
                settings_dialog.open = False
            except Exception:
                pass
            # perform clear (fixed scope issue)
            summary = perform_clear_all_data()
            # reinitialize db tracker instance
            try:
                nonlocal db
                db = DatabaseTracker()
            except Exception:
                pass

        # asign actions now that handlers are defined
        confirm_dialog.actions = [
            ft.TextButton("Cancel", on_click=close_confirm),
        ]

        page.dialog = confirm_dialog
        confirm_dialog.open = True
        page.update()
        
    def export_database(e=None):
        if os.path.exists(db.db_path):
            import shutil
            try:
                backup_path = db.db_path + ".backup"
                shutil.copy2(db.db_path, backup_path)
                show_snackbar(f"Database exported to: {backup_path}")
            except Exception as e:
                show_snackbar(f"Export failed: {str(e)}", ft.Colors.RED_400)
                
    def import_database(e=None):
        if os.path.exists(db.db_path + ".backup"):
            import shutil
            try:
                shutil.copy2(db.db_path + ".backup", db.db_path)
                update_entries()
                show_snackbar("Database imported successfully")
            except Exception as e:
                show_snackbar(f"Import failed: {str(e)}", ft.Colors.RED_400)
        else:
            show_snackbar("No backup file found", ft.Colors.RED_400)

    def close_settings(e=None):
        settings_dialog.open = False
        page.update()

    def show_settings_dialog(e=None):
        settings_dialog.open = True
        page.update()
    
    db = DatabaseTracker()
    
    # table headers configuration
    table_headers = {
        "builds": ["Name", "ManifestID", "Year", "Season", "CrackType", "Link", "MD5", "Description"],
        "tools": ["Name", "Version", "Link", "Description"],
        "cheats": ["Name", "Type", "Link", "Description"],
        "downloaders": ["Name", "Link", "Description"],
        "preserved": ["Name", "Link", "Description"]
    }
    
    # form fields configuration
    form_fields = {
        "builds": [
            {"name": "name", "label": "Name", "required": True},
            {"name": "manifest_id", "label": "ManifestID", "required": False},
            {"name": "year", "label": "Year", "required": False, "type": "number"},
            {"name": "season", "label": "Season", "required": False},
            {"name": "crack_type", "label": "CrackType", "required": False},
            {"name": "link", "label": "Link", "required": False},
            {"name": "md5", "label": "MD5", "required": False},
            {"name": "description", "label": "Description", "required": False, "multiline": True}
        ],
        "tools": [
            {"name": "name", "label": "Name", "required": True},
            {"name": "version", "label": "Version", "required": False},
            {"name": "link", "label": "Link", "required": False},
            {"name": "description", "label": "Description", "required": False, "multiline": True}
        ],
        "cheats": [
            {"name": "name", "label": "Name", "required": True},
            {"name": "type", "label": "Type", "required": False},
            {"name": "link", "label": "Link", "required": False},
            {"name": "description", "label": "Description", "required": False, "multiline": True}
        ],
        "downloaders": [
            {"name": "name", "label": "Name", "required": True},
            {"name": "link", "label": "Link", "required": False},
            {"name": "description", "label": "Description", "required": False, "multiline": True}
        ],
        "preserved": [
            {"name": "name", "label": "Name", "required": True},
            {"name": "link", "label": "Link", "required": False},
            {"name": "description", "label": "Description", "required": False, "multiline": True}
        ]
    }
    
    # store references to nav buttons and entries container
    nav_buttons = []
    entries_container = ft.Column([], spacing=10, scroll=ft.ScrollMode.AUTO)
    
    form_dialog = ft.AlertDialog(
        title=ft.Text("Add New Record"),
        content=ft.Container(
            content=ft.Column([], scroll=ft.ScrollMode.AUTO),
            width=500,
            height=600
        ),
        actions=[],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor="#191970"
    )
    
    def show_snackbar(message, color=ft.Colors.GREEN):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()
    
    def create_entry_card(record, headers):
        """Create an individual entry card"""
        # create rows for non-empty fieldsq
        field_rows = []
        
        for i, (header, value) in enumerate(zip(headers, record[1:])):  # skip id
            if value and str(value).strip():  # only show non empty fields
                field_rows.append(
                    ft.Row([
                        ft.Container(
                            content=ft.Text(
                                f"{header}:",
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE,
                                size=14
                            ),
                            width=120
                        ),
                        ft.Container(
                            content=ft.Text(
                                str(value),
                                color=ft.Colors.WHITE70,
                                size=14,
                                selectable=True
                            ),
                            expand=True
                        )
                    ], spacing=10)
                )
        
        # create the card
        card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(
                        f"ID: {record[0]}",
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.CYAN,
                        size=16
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.DELETE,
                        icon_color=ft.Colors.RED_400,
                        icon_size=20,
                        on_click=lambda e, record_id=record[0]: delete_record(record_id)
                    )
                ]),
                ft.Divider(height=1, color=ft.Colors.WHITE24),
                ft.Column(field_rows, spacing=8)
            ], spacing=10),
            bgcolor="#191970",
            padding=15,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.WHITE12),
            margin=ft.margin.only(bottom=10)
        )
        
        return card
    
    def switch_tab(tab_name):
        db.current_table = tab_name
        # update page title
        page.title = f"database | 6 - {tab_name.title()}"
        update_entries()
        # update active button styles
        for btn_data in nav_buttons:
            if btn_data["name"] == tab_name:
                btn_data["container"].bgcolor = "#1E3A8A"
                btn_data["icon"].color = ft.Colors.WHITE
                btn_data["text"].color = ft.Colors.WHITE
            else:
                btn_data["container"].bgcolor = None
                btn_data["icon"].color = "#AAAAAA"
                btn_data["text"].color = "#AAAAAA"
        page.update()
    
    def update_entries():
        """Update the entries display"""
        entries_container.controls.clear()
        
        # get data for current table
        data = db.get_table_data(db.current_table)
        headers = table_headers[db.current_table]
        
        if not data:
            entries_container.controls.append(
                ft.Container(
                    content=ft.Text(
                        f"No {db.current_table} found. Click the + button to add some!",
                        color=ft.Colors.WHITE70,
                        size=16,
                        text_align=ft.TextAlign.CENTER
                    ),
                    alignment=ft.alignment.center,
                    padding=50
                )
            )
        else:
            for record in data:
                entries_container.controls.append(create_entry_card(record, headers))
        
        page.update()
    
    def delete_record(record_id):
        try:
            db.delete_record(db.current_table, record_id)
            update_entries()
            show_snackbar("Record deleted successfully!")
        except Exception as e:
            show_snackbar(f"Error deleting record: {str(e)}", ft.Colors.RED)
    
    def show_add_dialog(e=None):
        # clear previous form content
        form_dialog.content.content.controls.clear()
        form_dialog.actions.clear()

        form_controls = []
        controls_by_name = {}

        # create form fields based on current table
        fields = form_fields[db.current_table]
        for field in fields:
            # create kwargs and common properties
            kwargs = {
                "label": field["label"],
                "hint_text": f"Enter {field['label'].lower()}",
                "bgcolor": "#000033",
                "border_color": "#1E3A8A",
                "color": ft.Colors.WHITE
            }

            # add type-specific properties
            if field.get("type") == "number":
                kwargs["keyboard_type"] = ft.KeyboardType.NUMBER
            elif field.get("multiline"):
                kwargs.update({
                    "multiline": True,
                    "max_lines": 4,
                    "min_lines": 3
                })

            control = ft.TextField(**kwargs)
            # keep reference to control so we can read values on save
            controls_by_name[field["name"]] = control
            form_controls.append(control)
            form_controls.append(ft.Container(height=10))  # Spacer

        def save_record(e):
            print(f"save_record called for table: {db.current_table}")
            try:
                # read values directly from the TextField controls
                values = []
                for field in fields:
                    control = controls_by_name.get(field["name"])
                    value = ""
                    if control is not None:
                        value = control.value if control.value is not None else ""

                    # handle number type conversion
                    if field.get("type") == "number":
                        if value != "":
                            try:
                                value = int(value)
                            except ValueError:
                                show_snackbar(f"{field['label']} must be a number!", ft.Colors.RED)
                                print(f"validation failed: {field['name']} not a number: {value}")
                                return
                        else:
                            value = None

                    values.append(value)

                # Validate required fields
                for i, field in enumerate(fields):
                    if field["required"] and (values[i] is None or values[i] == ""):
                        show_snackbar(f"{field['label']} is required!", ft.Colors.RED)
                        print(f"validation failed: {field['name']} is required")
                        return

                print(f"attempting to add_record with values: {values}")
                try:
                    db.add_record(db.current_table, values)
                    form_dialog.open = False
                    update_entries()
                    page.update()
                    show_snackbar("Record added successfully!")
                    # record added successfully
                except Exception as e:
                    show_snackbar(f"Error saving record: {str(e)}", ft.Colors.RED)
                    print(f"Error saving record: {str(e)}")  # For debugging
            except Exception as e:
                show_snackbar(f"Error preparing record data: {str(e)}", ft.Colors.RED)
                print(f"Error preparing record data: {str(e)}")  # For debugging

        def close_dialog(e=None):
            form_dialog.open = False
            page.update()

        # set form controls and actions
        form_dialog.content.content.controls = form_controls
        form_dialog.actions = [
            ft.TextButton("Cancel", on_click=close_dialog),
            ft.ElevatedButton("Save", on_click=save_record, bgcolor="#1E3A8A")
        ]

        form_dialog.open = True
        page.update()
        
    def show_settings_dialog(e=None):
        settings_dialog.open = True
        page.update()
    
    # create navigation buttons (same as PySix style)
    nav_Icons = {
        "builds": ft.Icons.BUILD,
        "tools": ft.Icons.CONSTRUCTION,
        "cheats": ft.Icons.SECURITY,
        "downloaders": ft.Icons.DOWNLOAD,
        "preserved": ft.Icons.ARCHIVE,
        "about": ft.Icons.INFO,
    }

    for tab_name in table_headers.keys():
        icon_control = ft.Icon(nav_Icons[tab_name], color="#AAAAAA", size=20)
        text_control = ft.Text(tab_name.title(), size=16, color="#AAAAAA")
        
        container = ft.Container(
            content=ft.Row([
                icon_control,
                text_control
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=12, horizontal=20),
            border_radius=6,
            on_click=lambda e, name=tab_name: switch_tab(name),
        )
        
        nav_buttons.append({
            "container": container,
            "icon": icon_control,
            "text": text_control,
            "name": tab_name
        })
    
    # set initial active button
    nav_buttons[0]["container"].bgcolor = "#1E3A8A"
    nav_buttons[0]["icon"].color = ft.Colors.WHITE
    nav_buttons[0]["text"].color = ft.Colors.WHITE
    
    # sidebar (matching █████ exactly)
    sidebar_header = ft.Column([
        ft.Container(
            content=ft.Image(
                src=resource_path("db6.png"),
                fit=ft.ImageFit.SCALE_DOWN,
                filter_quality=ft.FilterQuality.HIGH,
            ),
            width=220,
            height=100,
            padding=0,
            margin=0,
            alignment=ft.alignment.center,
            bgcolor=None,
        ),
        ft.Divider(thickness=1, color=ft.Colors.WHITE24),
    ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER, height=100)
    
    sidebar = ft.Column(
        controls=[btn_data["container"] for btn_data in nav_buttons],
        spacing=5,
        alignment=ft.MainAxisAlignment.START,
        expand=True
    )
    
    sidebar_container = ft.Container(
        content=ft.Column([sidebar_header, sidebar], expand=True),
        width=240,
        bgcolor="#191970",
        padding=ft.padding.only(left=10, right=10, top=0, bottom=0),
    )
    
    # content area (responsive width)
    content_area = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text(
                        f"{db.current_table.title()}",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE
                    ),
                    ft.Container(expand=True),
                    ft.FloatingActionButton(
                        icon=ft.Icons.SETTINGS,
                        on_click=show_settings_dialog,
                        bgcolor="#1E3A8A",
                        width=40,
                        height=40,
                    ),
                    ft.Container(width=10),  # spacer
                    ft.FloatingActionButton(
                        icon=ft.Icons.ADD,
                        text="Add Record", 
                        on_click=show_add_dialog,
                        bgcolor="#1E3A8A",
                    )
                ]),
                padding=20
            ),
            ft.Container(
                content=entries_container,
                expand=True,
                padding=ft.padding.symmetric(horizontal=20)
            )
        ]),
        expand=True,
        padding=0,
        bgcolor="#000000"
    )
    
    # main layout
    layout = ft.Row([
        sidebar_container,
        ft.Container(width=1, bgcolor=ft.Colors.WHITE12, margin=ft.margin.symmetric(vertical=20)),
        content_area,
    ], expand=True)
    
    # create a single instance of the settings dialog
    settings_dialog = ft.AlertDialog(
        title=ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
        modal=True,
        content=ft.Container(
            content=ft.Column([
                # theme selection
                ft.Text("Theme", size=18, weight=ft.FontWeight.BOLD),
                ft.Dropdown(
                    width=400,
                    options=[
                        ft.dropdown.Option("dark_blue", "Dark Blue (Default)"),
                        ft.dropdown.Option("midnight_purple", "Midnight Purple"),
                        ft.dropdown.Option("dark_red", "Dark Red"),
                        ft.dropdown.Option("forest_dark", "Forest Dark"),
                        ft.dropdown.Option("ocean_dark", "Ocean Dark"),
                    ],
                    value="dark_blue",
                    on_change=lambda e: change_theme(e.control.value),
                ),
                ft.Divider(height=1, color=ft.Colors.WHITE24),
                
                # data management
                ft.Text("Data Management", size=18, weight=ft.FontWeight.BOLD),
                # force clear + refresh (without confirm)
                ft.Row([
                    ft.ElevatedButton(
                        "Force Clear (no confirm)",
                        icon=ft.Icons.DELETE,
                        color=ft.Colors.RED_400,
                        on_click=lambda e: perform_clear_all_data(),
                    ),
                    ft.ElevatedButton(
                        "Refresh Entries",
                        icon=ft.Icons.REFRESH,
                        on_click=lambda e: (update_entries(), show_snackbar("Entries refreshed")),
                    )
                ], spacing=10),
                
                # export / import 
                ft.Text("Data Transfer", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.ElevatedButton(
                        "Export Database",
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=lambda e: export_file_picker.save_file(),
                    ),
                    ft.ElevatedButton(
                        "Import Database",
                        icon=ft.Icons.DOWNLOAD_ROUNDED,
                        on_click=lambda e: import_file_picker.pick_files(),
                    ),
                ], spacing=10),
                
            ], scroll=ft.ScrollMode.AUTO, spacing=20),
            width=500,
            height=400,
            padding=20,
        ),
        actions=[
            ft.TextButton("Close", on_click=close_settings),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor="#191970"
    )

    # load persisted settings (theme)
    try:
        import json
        if os.path.exists("db6_settings.json"):
            with open("db6_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
                theme_val = settings.get("theme")
                if theme_val:
                    change_theme(theme_val)
    except Exception as e:
        print(f"Error loading settings: {e}")





    # add components to page
    page.add(layout)

    page.overlay.extend([form_dialog, settings_dialog])
    
    # initialize with builds entries
    update_entries()

if __name__ == "__main__":
    ft.app(target=main)


"""
this script is a flet-based gui db tracker (db6) for r6 builds etc

- db:
   uses sqlite (tracker.db) to store five tables:
        - builds
        - tools
        - cheats
        - downloaders
        - preserved

- CRUD functions:
        - create tables if not exist
        - add record
        - get all records
        - delete record

- GUI:
    - sidebare navigation
    - main content area
    - floating add button
    - snackbars for success/error notifications

- Features:
    - dynamic fonts
    - delete button
    - dark theme 
    - responsive layout

"""