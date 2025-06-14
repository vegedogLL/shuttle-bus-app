from flask import Flask, render_template, request, redirect, send_file, url_for
import sqlite3
import datetime
import pandas as pd
import io
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os

app = Flask(__name__)

# 获取SQLite连接
def get_db_conn():
    return sqlite3.connect('data.db')

# 初始化数据库
def init_db():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT,
        time TEXT NOT NULL,
        people_count INTEGER NOT NULL,
        direction TEXT NOT NULL,
        comment TEXT,
        submit_time TEXT NOT NULL,
        activity_id INTEGER,
        FOREIGN KEY(activity_id) REFERENCES activities(id)
    )
    ''')
    conn.commit()
    c.close()
    conn.close()

@app.route('/')
def index():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT id, name FROM activities ORDER BY id DESC')
    activities = c.fetchall()
    c.close()
    conn.close()
    return render_template('activity_select.html', activities=activities)

@app.route('/<activity_name>')
def form(activity_name):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT id, name FROM activities WHERE name = ?', (activity_name,))
    activity = c.fetchone()
    c.close()
    conn.close()
    if not activity:
        return "Activity not found", 404
    today = datetime.date.today()
    date_options = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    return render_template('form.html', date_options=date_options, activity=activity)

@app.route('/submit/<activity_name>', methods=['POST'])
def submit(activity_name):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT id FROM activities WHERE name = ?', (activity_name,))
    activity = c.fetchone()
    if not activity:
        c.close()
        conn.close()
        return "Activity not found", 404
    activity_id = activity[0]
    date = request.form['date']
    time = request.form['time']
    full_time = f"{date} {time}"
    data = (
        request.form['country'],
        full_time,
        int(request.form['people_count']),
        request.form['direction'],
        request.form.get('comment', ''),
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        activity_id
    )
    c.execute('''
        INSERT INTO requests (country, time, people_count, direction, comment, submit_time, activity_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', data)
    conn.commit()
    c.close()
    conn.close()
    return render_template('success.html', activity_name=activity_name)

@app.route('/admin', methods=['GET', 'POST'])
def admin_index():
    if request.method == 'POST':
        name = request.form.get('activity_name')
        if name:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO activities (name) VALUES (?)', (name,))
            conn.commit()
            c.close()
            conn.close()
        return redirect('/admin')
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT id, name FROM activities ORDER BY id DESC')
    activities = c.fetchall()
    c.close()
    conn.close()
    return render_template('admin_activity_select.html', activities=activities)

@app.route('/admin/<activity_name>', methods=['GET'])
def admin(activity_name):
    selected_date = request.args.get('date')
    conn = get_db_conn()
    c = conn.cursor()
    c.execute('SELECT id, name FROM activities WHERE name = ?', (activity_name,))
    activity = c.fetchone()
    if not activity:
        c.close()
        conn.close()
        return "Activity not found", 404
    activity_id = activity[0]
    query = '''
        SELECT country, time, people_count, direction, comment, submit_time, id
        FROM requests
        WHERE activity_id = ?
    '''
    params = [activity_id]
    if selected_date:
        query += ' AND time LIKE ?'
        params.append(selected_date + '%')
    query += ' ORDER BY submit_time DESC'
    c.execute(query, params)
    rows = c.fetchall()
    c.close()
    conn.close()
    return render_template('admin.html', requests=rows, selected_date=selected_date, activity_name=activity_name)

@app.route('/delete_activity', methods=['POST'])
def delete_activity():
    activity_name = request.form.get('activity_name')
    if activity_name:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute('SELECT id FROM activities WHERE name = ?', (activity_name,))
        row = c.fetchone()
        if row:
            activity_id = row[0]
            c.execute('DELETE FROM requests WHERE activity_id = ?', (activity_id,))
            c.execute('DELETE FROM activities WHERE id = ?', (activity_id,))
        conn.commit()
        c.close()
        conn.close()
    return redirect('/admin')

@app.route('/delete/<activity_name>', methods=['POST'])
def delete_entries(activity_name):
    ids = request.form.getlist('delete_ids')
    if ids:
        conn = get_db_conn()
        c = conn.cursor()
        query = f"DELETE FROM requests WHERE id IN ({','.join(['?'] * len(ids))})"
        c.execute(query, ids)
        conn.commit()
        c.close()
        conn.close()
    return redirect(f'/admin/{activity_name}')

@app.route('/export')
def export():
    try:
        selected_activity = request.args.get('activity_id')
        selected_date = request.args.get('date')
        conn = get_db_conn()
        c = conn.cursor()
        # 修正：activity_name传递给前端的是活动名，需要先查id
        activity_id = None
        if selected_activity:
            c.execute('SELECT id FROM activities WHERE name = ?', (selected_activity,))
            row = c.fetchone()
            if row:
                activity_id = row[0]
        query = '''
            SELECT country, time, people_count, direction, comment, submit_time
            FROM requests
        '''
        params = []
        where_clauses = []
        if activity_id:
            where_clauses.append('activity_id = ?')
            params.append(activity_id)
        if selected_date:
            where_clauses.append('DATE(time) = ?')
            params.append(selected_date)
        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)
        query += ' ORDER BY time ASC'
        c.execute(query, params)
        rows = c.fetchall()
        c.close()
        conn.close()
        if rows:
            df = pd.DataFrame(rows, columns=["Country", "Time", "People Count", "Direction", "Comment", "Submitted At"])
        else:
            df = pd.DataFrame(columns=["Country", "Time", "People Count", "Direction", "Comment", "Submitted At"])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Requests')
        output.seek(0)
        filename = "shuttle_requests"
        if selected_activity:
            filename += f"_{selected_activity}"
        if selected_date:
            filename += f"_{selected_date}"
        filename += ".xlsx"
        return send_file(output, download_name=filename, as_attachment=True)
    except Exception as e:
        import traceback
        print("Export error:", e)
        print(traceback.format_exc())
        return "Export failed: " + str(e), 500

@app.route('/qrcode/<activity_name>')
def qrcode_img(activity_name):
    url = request.url_root.rstrip('/') + '/' + activity_name
    img = qrcode.make(url).convert("RGB")
    title = activity_name

    # 云端环境通常没有arial.ttf，导致load_default字体很小
    # 尝试加载常见的字体，否则用默认字体
    font = None
    font_size = 22
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux常见
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux常见
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",       # 备选
        "arial.ttf"                                              # Windows
    ]
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width, text_height = font.getsize(title)
    padding = 18
    new_height = img.height + text_height + padding
    new_img = Image.new("RGB", (img.width, new_height), "white")
    new_img.paste(img, (0, text_height + padding))
    draw = ImageDraw.Draw(new_img)
    text_x = (img.width - text_width) // 2
    text_y = 8
    draw.text((text_x, text_y), title, fill="#222", font=font)
    buf = io.BytesIO()
    new_img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
