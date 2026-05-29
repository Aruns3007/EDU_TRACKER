from datetime import date, datetime
import sqlite3
from pathlib import Path

from flask import Blueprint, render_template
from flask_login import current_user

from extensions import db
from routes.access_control import admin_required

admin = Blueprint('admin', __name__, url_prefix='/admin')


def _fmt_value(value):
    if value is None:
        return '-'
    if isinstance(value, datetime):
        return value.strftime('%d %b %Y, %I:%M %p')
    if isinstance(value, date):
        return value.strftime('%d %b %Y')
    return str(value)


def _quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


def _table_title(name):
    return name.replace('_', ' ').title()


def _database_path():
    database = db.engine.url.database
    if not database:
        return None
    return Path(database)


def _build_section(title, description, badge, columns, rows, anchor):
    return {
        'title': title,
        'description': description,
        'badge': badge,
        'columns': columns,
        'rows': rows,
        'anchor': anchor,
    }


def _load_database_sections(limit=12):
    db_path = _database_path()
    if not db_path or not db_path.exists():
        return [], {'table_count': 0, 'row_count': 0, 'populated_count': 0, 'largest_table': '-', 'largest_rows': 0}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    table_names = [row['name'] for row in cursor.fetchall()]

    sections = []
    total_rows = 0
    populated_tables = 0
    largest_table = '-'
    largest_rows = 0

    try:
        for table_name in table_names:
            cursor.execute(f'PRAGMA table_info({_quote_identifier(table_name)})')
            table_info = cursor.fetchall()
            columns = [row['name'] for row in table_info]

            cursor.execute(f'SELECT COUNT(*) AS total FROM {_quote_identifier(table_name)}')
            row_count = cursor.fetchone()['total']
            total_rows += row_count
            if row_count:
                populated_tables += 1
            if row_count >= largest_rows:
                largest_rows = row_count
                largest_table = table_name

            order_column = next((row['name'] for row in table_info if row['pk']), None)
            if not order_column and 'id' in columns:
                order_column = 'id'

            query = f'SELECT * FROM {_quote_identifier(table_name)}'
            if order_column:
                query += f' ORDER BY {_quote_identifier(order_column)} DESC'
            else:
                query += ' ORDER BY rowid DESC'
            query += f' LIMIT {int(limit)}'

            cursor.execute(query)
            records = cursor.fetchall()
            rows = []
            for record in records:
                row = {}
                for column in columns:
                    value = record[column]
                    if table_name == 'user' and column == 'password':
                        row[column] = '[hidden]'
                    else:
                        row[column] = _fmt_value(value)
                rows.append(row)

            sections.append(
                _build_section(
                    _table_title(table_name),
                    f'Live rows from the `{table_name}` table in SQLite.',
                    f'{row_count} rows',
                    columns,
                    rows,
                    table_name.replace('_', '-'),
                )
            )
    finally:
        conn.close()

    metrics = {
        'table_count': len(table_names),
        'row_count': total_rows,
        'populated_count': populated_tables,
        'largest_table': _table_title(largest_table) if largest_table != '-' else '-',
        'largest_rows': largest_rows,
    }
    return sections, metrics


@admin.route('/')
@admin.route('/dashboard')
@admin_required
def dashboard():
    sections, metrics = _load_database_sections()
    database_path = _database_path()

    summary_cards = [
        {
            'label': 'Tables',
            'value': metrics['table_count'],
            'hint': 'SQLite tables currently available in the database',
        },
        {
            'label': 'Rows',
            'value': metrics['row_count'],
            'hint': 'Total rows across all tables',
        },
        {
            'label': 'Populated',
            'value': metrics['populated_count'],
            'hint': 'Tables that contain at least one row',
        },
        {
            'label': 'Largest Table',
            'value': metrics['largest_table'],
            'hint': f"{metrics['largest_rows']} rows" if metrics['largest_rows'] else 'No rows yet',
        },
    ]

    return render_template(
        'admin_dashboard.html',
        summary_cards=summary_cards,
        sections=sections,
        database_path=str(database_path) if database_path else '-',
        now=datetime.now(),
        current_user=current_user,
    )
