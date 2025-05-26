from flask import Flask, render_template, request, redirect
from flask import send_file
import sqlite3
import datetime
import pandas as pd
import io

app = Flask(__name__)

# 初始化数据库
def init_db():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT,
        time TEXT NOT NULL,
        people_count INTEGER NOT NULL,
        direction TEXT NOT NULL,
        comment TEXT,
        submit_time TEXT NOT NULL
    )
''')

    conn.commit()
    conn.close()

@app.route('/')
def form():
    today = datetime.date.today()
    date_options = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    return render_template('form.html', date_options=date_options)


# 提交表单
@app.route('/submit', methods=['POST'])
def submit():
    date = request.form['date']
    time = request.form['time']
    full_time = f"{date} {time}"

    data = (
        request.form['country'],
        full_time,
        int(request.form['people_count']),
        request.form['direction'],
        request.form.get('comment', ''),
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO requests (country, time, people_count, direction, comment, submit_time)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', data)
    conn.commit()
    conn.close()
    return "Thank you for your submission! Your request has been recorded."

# 后台页面
@app.route('/admin', methods=['GET'])
def admin():
    selected_date = request.args.get('date')
    conn = sqlite3.connect('data.db')
    c = conn.cursor()

    if selected_date:
        c.execute('''
            SELECT country, time, people_count, direction, comment, submit_time, id
            FROM requests
            WHERE time LIKE ?
            ORDER BY submit_time DESC
        ''', (selected_date + '%',))
    else:
        c.execute('''
            SELECT country, time, people_count, direction, comment, submit_time, id
            FROM requests
            ORDER BY submit_time DESC
        ''')
    
    print(f"筛选日期: {selected_date}")
    print(f"SQL条件: time LIKE '{selected_date}%'")

    rows = c.fetchall()
    conn.close()

    return render_template('admin.html', requests=rows, selected_date=selected_date)

# 删除选中的记录
@app.route('/delete', methods=['POST'])
def delete_entries():
    ids = request.form.getlist('delete_ids')
    if ids:
        conn = sqlite3.connect('data.db')
        c = conn.cursor()
        query = f"DELETE FROM requests WHERE id IN ({','.join(['?'] * len(ids))})"
        c.execute(query, ids)
        conn.commit()
        conn.close()
    return redirect('/admin')

# 导出数据为Excel
@app.route('/export')
def export():
    selected_date = request.args.get('date')
    conn = sqlite3.connect('data.db')
    c = conn.cursor()

    if selected_date:
        c.execute('''
            SELECT country, time, people_count, direction, comment, submit_time
            FROM requests
            WHERE DATE(time) = ?
            ORDER BY time ASC
        ''', (selected_date,))
    else:
        c.execute('''
            SELECT country, time, people_count, direction, comment, submit_time
            FROM requests
            ORDER BY time ASC
        ''')

    rows = c.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["Country", "Time", "People Count", "Direction", "Comment", "Submitted At"])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Requests')

    output.seek(0)
    filename = f"shuttle_requests_{selected_date}.xlsx" if selected_date else "shuttle_requests_all.xlsx"
    return send_file(output, download_name=filename, as_attachment=True)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
