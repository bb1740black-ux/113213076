from contextlib import closing
from html import escape
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()
DB = Path(__file__).with_name("manuscripts.db")
STATUS = {"draft": "編輯中", "review": "審查中", "approved": "已通過"}


def query(sql, *values):
    with closing(sqlite3.connect(DB)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS manuscripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
        )""")
        result = db.execute(sql, values)
        return result.fetchall() if result.description else result.rowcount


def page(title, body):
    return HTMLResponse(f"""<!doctype html>
<html lang="zh-Hant">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ background:#eef4ef; color:#25372d; font:16px/1.6 system-ui; margin:24px 12px; }}
main {{ max-width:720px; margin:auto; background:white; padding:24px; border-radius:10px; }}
a {{ color:#235d45; }}
article {{ padding:12px 0; border-top:1px solid #dbe6dc; overflow-wrap:anywhere; }}
h2,p {{ margin:8px 0; }}
label {{ display:block; margin:12px 0; }}
input,textarea {{ box-sizing:border-box; display:block; width:100%; padding:8px; font:inherit; }}
button {{ background:#235d45; color:white; padding:7px 12px; border:0; border-radius:5px; cursor:pointer; }}
.action {{ display:inline-block; margin:4px; }}
.content {{ white-space:pre-wrap; }}
</style>
<main><nav><a href="/">首頁</a></nav><h1>{title}</h1>{body}</main>
</html>""")


def button(url, label):
    return f'<form class="action" method="post" action="{url}"><button>{label}</button></form>'


def author_path(author):
    if author not in (1, 2):
        raise HTTPException(404, "找不到作者")
    return f"/author/{author}"


def redirect(url):
    return RedirectResponse(url, status_code=303)


def fields(category, title, content):
    values = (category.strip(), title.strip(), content.strip())
    if not all(values):
        raise HTTPException(400, "請填寫類別、標題和文章內容")
    return values


@app.get("/")
def home():
    return page("投稿審查系統", """
    <p>選擇身分開始操作。</p>
    <ul>
      <li><a href="/author/1">作者 1</a></li>
      <li><a href="/author/2">作者 2</a></li>
      <li><a href="/editor">編輯</a></li>
    </ul>""")


@app.get("/author/{author}")
def author_list(author: int):
    path = author_path(author)
    rows = query("SELECT * FROM manuscripts WHERE author = ? ORDER BY id DESC", author)
    body = f'<p><a href="{path}/new">新增稿件</a></p>'
    for row in rows:
        url = f"{path}/{row['id']}"
        actions = ""
        if row["status"] == "draft":
            actions = f'<a href="{url}/edit">編輯</a>'
            actions += button(url + "/submit", "送出投稿") + button(url + "/delete", "刪除")
        body += f"""<article><h2>{escape(row['title'])}</h2>
        <p>{escape(row['category'])} · {STATUS[row['status']]}</p>{actions}</article>"""
    return page(f"作者 {author} 的稿件", body + ("" if rows else "<p>目前沒有稿件。</p>"))


def manuscript_form(path, action, row=None):
    category, title, content = (
        (escape(row["category"]), escape(row["title"]), escape(row["content"]))
        if row else ("", "", "")
    )
    return f"""<p><a href="{path}">返回稿件清單</a></p>
    <form method="post" action="{action}">
      <label>類別<input name="category" required value="{category}"></label>
      <label>標題<input name="title" required value="{title}"></label>
      <label>文章內容<textarea name="content" rows="8" required>{content}</textarea></label>
      <button>儲存稿件</button>
    </form>"""


@app.get("/author/{author}/new")
def new_form(author: int):
    path = author_path(author)
    return page("新增稿件", manuscript_form(path, path + "/new"))


@app.post("/author/{author}/new")
def create(author: int, category: str = Form(), title: str = Form(), content: str = Form()):
    path = author_path(author)
    query("INSERT INTO manuscripts (author, category, title, content) VALUES (?, ?, ?, ?)",
          author, *fields(category, title, content))
    return redirect(path)


@app.get("/author/{author}/{item}/edit")
def edit_form(author: int, item: int):
    path = author_path(author)
    rows = query("SELECT * FROM manuscripts WHERE id = ? AND author = ? AND status = 'draft'",
                 item, author)
    if not rows:
        raise HTTPException(404, "找不到可編輯的稿件")
    return page("編輯稿件", manuscript_form(path, f"{path}/{item}/edit", rows[0]))


@app.post("/author/{author}/{item}/edit")
def update(author: int, item: int, category: str = Form(), title: str = Form(), content: str = Form()):
    path = author_path(author)
    changed = query("""UPDATE manuscripts SET category = ?, title = ?, content = ?
                       WHERE id = ? AND author = ? AND status = 'draft'""",
                    *fields(category, title, content), item, author)
    if not changed:
        raise HTTPException(400, "只有自己的編輯中稿件可以修改")
    return redirect(path)


@app.post("/author/{author}/{item}/{action}")
def author_action(author: int, item: int, action: str):
    path = author_path(author)
    if action == "submit":
        sql = "UPDATE manuscripts SET status = 'review'"
    elif action == "delete":
        sql = "DELETE FROM manuscripts"
    else:
        raise HTTPException(404, "找不到這項操作")
    if not query(sql + " WHERE id = ? AND author = ? AND status = 'draft'", item, author):
        raise HTTPException(400, "只有自己的編輯中稿件可以送出或刪除")
    return redirect(path)


@app.get("/editor")
def editor_list():
    rows = query("SELECT * FROM manuscripts WHERE status = 'review' ORDER BY id DESC")
    body = "".join(f"""<article><h2><a href="/editor/{row['id']}">{escape(row['title'])}</a></h2>
    <p>作者 {row['author']} · {escape(row['category'])}</p></article>""" for row in rows)
    return page("待審稿件", body or "<p>目前沒有待審稿件。</p>")


@app.get("/editor/{item}")
def review(item: int):
    rows = query("SELECT * FROM manuscripts WHERE id = ? AND status = 'review'", item)
    if not rows:
        raise HTTPException(404, "找不到待審稿件")
    row = rows[0]
    body = f"""<p><a href="/editor">返回待審清單</a></p>
    <h2>{escape(row['title'])}</h2><p>作者 {row['author']} · {escape(row['category'])}</p>
    <article class="content">{escape(row['content'])}</article>"""
    body += button(f"/editor/{item}/approve", "通過") + button(f"/editor/{item}/return", "退回")
    return page("審查稿件", body)


@app.post("/editor/{item}/{action}")
def editor_action(item: int, action: str):
    targets = {"approve": "approved", "return": "draft"}
    if action not in targets:
        raise HTTPException(404, "找不到這項操作")
    if not query("UPDATE manuscripts SET status = ? WHERE id = ? AND status = 'review'",
                 targets[action], item):
        raise HTTPException(400, "只有審查中的稿件可以審查")
    return redirect("/editor")
