# app.py
import os
import math
import random
import urllib.parse
from functools import lru_cache
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, request, redirect, url_for, render_template_string, abort

APP_TITLE = "Explore Artworks • The MET"
BASE_API = "https://collectionapi.metmuseum.org/public/collection/v1"

app = Flask(__name__)

# ---- 简单稳定的 HTTP 工具 ----

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Explore-MET-Demo/1.0"})
TIMEOUT = 12


class MetAPIError(RuntimeError):
    pass


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        r = SESSION.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise MetAPIError(f"MET API 请求失败：{e}")


@lru_cache(maxsize=1)
def get_departments() -> List[Dict[str, Any]]:
    data = _get_json(f"{BASE_API}/departments")
    return data.get("departments", [])


@lru_cache(maxsize=4096)
def get_object(object_id: int) -> Dict[str, Any]:
    return _get_json(f"{BASE_API}/objects/{object_id}")


def search_objects(
    q: str,
    has_images: bool = True,
    department_id: Optional[int] = None,
    artist_or_culture: Optional[str] = None,
) -> List[int]:
    params: Dict[str, Any] = {"q": q or "*"}  # 用通配避免空串导致的奇怪行为
    if has_images:
        params["hasImages"] = "true"
    if department_id:
        params["departmentId"] = int(department_id)
    if artist_or_culture:
        params["artistOrCulture"] = artist_or_culture

    data = _get_json(f"{BASE_API}/search", params=params)
    return data.get("objectIDs") or []


def pick_random_object(max_tries: int = 30) -> Optional[int]:
    """从全集随机找一个有图像的作品"""
    try:
        all_ids = _get_json(f"{BASE_API}/objects").get("objectIDs") or []
    except MetAPIError:
        return None
    if not all_ids:
        return None

    for _ in range(max_tries):
        oid = random.choice(all_ids)
        try:
            obj = get_object(int(oid))
        except MetAPIError:
            continue
        if obj.get("primaryImageSmall") or obj.get("primaryImage"):
            return int(oid)
    return None


# ---- 简单模板（不使用 Jinja 继承/复杂表达式，尽量避免报错点） ----

HTML_BASE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{{ app_title }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <meta name="color-scheme" content="light dark">
  <style>
    .card:hover { transform: translateY(-2px); }
    .line-clamp-2 { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  </style>
</head>
<body class="min-h-screen bg-gray-50 text-gray-900">
  <header class="sticky top-0 z-40 backdrop-blur bg-white/80 border-b">
    <div class="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
      <a href="{{ home_url }}" class="text-xl font-semibold">🎨 Explore Artworks</a>
      <span class="text-gray-400">|</span>
      <a href="{{ random_url }}" class="text-sm px-3 py-1 rounded-full bg-gray-900 text-white hover:bg-black">来件随机作品</a>
      <a href="https://www.metmuseum.org/art/collection" class="ml-auto text-sm text-gray-500 hover:text-gray-700" target="_blank" rel="noreferrer">The MET Collection ↗</a>
    </div>
  </header>

  <!-- CONTENT -->
  {content}

  <footer class="py-10 text-center text-gray-400 text-sm">
    数据来源：The MET Collection API · 非官方示例应用
  </footer>
</body>
</html>
"""

HTML_HOME = """
<main class="max-w-6xl mx-auto px-4">
  <section class="py-6">
    <form action="{{ home_url }}" method="get" class="grid md:grid-cols-4 gap-3 bg-white p-4 rounded-2xl shadow">
      <div class="md:col-span-2">
        <label class="block text-sm text-gray-600 mb-1">关键词（作品名、作者、题材…）</label>
        <input name="q" value="{{ q }}" class="w-full rounded-xl border-gray-200" placeholder="如 van gogh / landscape / bronze">
      </div>
      <div>
        <label class="block text-sm text-gray-600 mb-1">部门</label>
        <select name="departmentId" class="w-full rounded-xl border-gray-200">
          <option value="">全部</option>
          {% for d in departments %}
            <option value="{{ d.departmentId }}" {% if department_id==d.departmentId %}selected{% endif %}>{{ d.displayName }}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label class="block text-sm text-gray-600 mb-1">艺术家或文化（可选）</label>
        <input name="artistOrCulture" value="{{ artist_or_culture }}" class="w-full rounded-xl border-gray-200" placeholder="如 Rembrandt 或 Chinese">
      </div>

      <div class="md:col-span-4 flex items-center justify-between pt-2">
        <label class="inline-flex items-center gap-2 text-sm">
          <input type="checkbox" name="hasImages" value="true" {% if has_images %}checked{% endif %} class="rounded">
          仅显示带图片
        </label>
        <div class="flex items-center gap-2">
          <select name="page_size" class="rounded-xl border-gray-200">
            {% for n in [12,16,20,24] %}
              <option value="{{ n }}" {% if page_size==n %}selected{% endif %}>每页 {{ n }}</option>
            {% endfor %}
          </select>
          <button class="px-4 py-2 rounded-xl bg-gray-900 text-white hover:bg-black">搜索</button>
        </div>
      </div>
    </form>
  </section>

  {% if error_msg %}
    <div class="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6">{{ error_msg }}</div>
  {% endif %}

  {% if total %}
    <p class="text-sm text-gray-600 mb-3">共找到 <b>{{ total }}</b> 件结果。</p>
    <section class="grid sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      {% for item in results %}
        <a href="{{ item.detail_url }}" class="card block bg-white rounded-2xl shadow hover:shadow-lg transition">
          {% if item.img %}
            <img src="{{ item.img }}" alt="{{ item.title or 'Artwork' }}" class="w-full h-56 object-cover rounded-t-2xl">
          {% else %}
            <div class="w-full h-56 bg-gray-100 rounded-t-2xl grid place-items-center text-gray-400">无图像</div>
          {% endif %}
          <div class="p-4 space-y-2">
            <h3 class="font-medium line-clamp-2">{{ item.title or 'Untitled' }}</h3>
            <p class="text-sm text-gray-600">{{ item.artist or 'Unknown Artist' }}</p>
            <p class="text-xs text-gray-400">{{ item.date or '' }}</p>
            {% if item.repo %}
              <p class="text-[11px] text-gray-400">{{ item.repo }}</p>
            {% endif %}
          </div>
        </a>
      {% endfor %}
    </section>

    {% if pagination %}
      <nav class="flex items-center justify-center gap-2 my-8">
        {% for p in pagination %}
          {% if p.disabled %}
            <span class="px-3 py-1 rounded border text-gray-300">{{ p.label }}</span>
          {% elif p.active %}
            <span class="px-3 py-1 rounded border bg-gray-900 text-white">{{ p.label }}</span>
          {% else %}
            <a class="px-3 py-1 rounded border hover:bg-gray-100" href="{{ p.url }}">{{ p.label }}</a>
          {% endif %}
        {% endfor %}
      </nav>
    {% endif %}
  {% elif searched %}
    <div class="text-gray-500 py-10 text-center">未找到匹配结果，试试换个关键词或去掉筛选。</div>
  {% else %}
    <section class="py-10 text-center text-gray-600">
      <p>输入关键词开始探索，或点击“来件随机作品”。</p>
    </section>
  {% endif %}
</main>
"""

HTML_DETAIL = """
<main class="max-w-5xl mx-auto px-4 py-8">
  <a href="{{ home_url }}" class="text-sm text-gray-600 hover:text-gray-900">← 返回</a>
  <article class="mt-4 grid md:grid-cols-2 gap-6">
    <div class="bg-white rounded-2xl shadow overflow-hidden">
      {% if obj.primaryImage or obj.primaryImageSmall %}
        <img src="{{ obj.primaryImage or obj.primaryImageSmall }}" alt="{{ obj.title or 'Artwork' }}" class="w-full object-cover">
      {% else %}
        <div class="w-full aspect-[4/3] bg-gray-100 grid place-items-center text-gray-400">无图像</div>
      {% endif %}
    </div>
    <div class="space-y-3">
      <h1 class="text-2xl font-semibold">{{ obj.title or 'Untitled' }}</h1>
      <p class="text-gray-700">{{ obj.artistDisplayName or 'Unknown Artist' }}</p>
      {% if obj.objectDate %}<p class="text-gray-500">{{ obj.objectDate }}</p>{% endif %}
      {% if obj.medium %}<p class="text-sm text-gray-700"><b>媒介</b>：{{ obj.medium }}</p>{% endif %}
      {% if obj.department %}<p class="text-sm text-gray-700"><b>部门</b>：{{ obj.department }}</p>{% endif %}
      {% if obj.dimensions %}<p class="text-sm text-gray-700"><b>尺寸</b>：{{ obj.dimensions }}</p>{% endif %}
      {% if obj.culture %}<p class="text-sm text-gray-700"><b>文化</b>：{{ obj.culture }}</p>{% endif %}
      {% if obj.creditLine %}<p class="text-sm text-gray-700"><b>来源</b>：{{ obj.creditLine }}</p>{% endif %}
      {% if obj.repository %}<p class="text-xs text-gray-500">{{ obj.repository }}</p>{% endif %}
      <div class="pt-2">
        {% if obj.objectURL %}
          <a class="inline-block px-4 py-2 rounded-xl border hover:bg-gray-100" href="{{ obj.objectURL }}" target="_blank" rel="noreferrer">在 MET 官方页查看 ↗</a>
        {% endif %}
        <a class="inline-block px-4 py-2 rounded-xl border hover:bg-gray-100 ml-2" href="{{ random_url }}">换一件随机作品</a>
      </div>
      {% if obj.tags %}
        <div class="pt-3">
          <div class="text-sm text-gray-600 mb-1">标签</div>
          <div class="flex flex-wrap gap-2">
            {% for tag in obj.tags %}
              <span class="text-xs px-2 py-1 rounded-full bg-gray-100">{{ tag.term }}</span>
            {% endfor %}
          </div>
        </div>
      {% endif %}
    </div>
  </article>
</main>
"""


def render_page(content_html: str, **ctx) -> str:
    """用最简单的模板组合，减少报错点。"""
    base = HTML_BASE.format(content=content_html)
    return render_template_string(base, **ctx)


# ---- 路由 ----

@app.route("/")
def index():
    # 读取查询参数
    q = request.args.get("q", "", type=str)
    has_images = request.args.get("hasImages", "true").lower() != "false"
    department_id = request.args.get("departmentId", type=int)
    artist_or_culture = request.args.get("artistOrCulture", "", type=str)
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 12, type=int), 1), 24)

    # 部门
    try:
        departments = get_departments()
    except MetAPIError as e:
        departments = []
        # 在页面上用一个更友好的提示
        dept_note = f"部门列表加载失败：{e}"
    else:
        dept_note = None

    # 搜索
    results: List[Dict[str, Any]] = []
    total = 0
    error_msg = None
    searched = bool(q or department_id or artist_or_culture)

    if searched:
        try:
            ids = search_objects(q, has_images, department_id, artist_or_culture or None)
            total = len(ids)
            start = (page - 1) * page_size
            end = start + page_size
            page_ids = ids[start:end]
            for oid in page_ids:
                try:
                    obj = get_object(int(oid))
                except MetAPIError:
                    continue
                results.append({
                    "objectID": obj.get("objectID"),
                    "title": obj.get("title"),
                    "artist": obj.get("artistDisplayName"),
                    "date": obj.get("objectDate"),
                    "img": obj.get("primaryImageSmall") or obj.get("primaryImage"),
                    "repo": obj.get("repository"),
                    "detail_url": url_for("object_detail", object_id=int(obj.get("objectID"))),
                })
        except MetAPIError as e:
            error_msg = str(e)

    # 分页链接后端生成，避免模板里玩花样
    pagination = []
    if total:
        total_pages = max(1, math.ceil(total / page_size))
        def qs_with(**updates):
            base = request.args.to_dict(flat=True)
            base.update({k: v for k, v in updates.items() if v is not None})
            return f"{url_for('index')}?{urllib.parse.urlencode(base)}"

        if page > 1:
            pagination.append({"label": "上一页", "url": qs_with(page=page-1), "active": False, "disabled": False})
        else:
            pagination.append({"label": "上一页", "url": "", "active": False, "disabled": True})

        start_p = max(1, page - 2)
        end_p = min(total_pages, page + 2)
        for p in range(start_p, end_p + 1):
            pagination.append({"label": str(p), "url": qs_with(page=p), "active": p == page, "disabled": False})

        if page < total_pages:
            pagination.append({"label": "下一页", "url": qs_with(page=page+1), "active": False, "disabled": False})
        else:
            pagination.append({"label": "下一页", "url": "", "active": False, "disabled": True})
    else:
        total_pages = 0

    return render_page(
        HTML_HOME,
        app_title=APP_TITLE,
        home_url=url_for("index"),
        random_url=url_for("random_pick"),
        departments=departments,
        department_id=department_id,
        has_images=has_images,
        q=q,
        artist_or_culture=artist_or_culture,
        page_size=page_size,
        total=total,
        results=results,
        pagination=pagination,
        error_msg=(dept_note or error_msg),
        searched=searched,
    )


@app.route("/object/<int:object_id>")
def object_detail(object_id: int):
    try:
        obj = get_object(object_id)
    except MetAPIError as e:
        abort(502, str(e))
    if not obj:
        abort(404, "作品未找到")

    return render_page(
        HTML_DETAIL,
        app_title=APP_TITLE,
        home_url=url_for("index"),
        random_url=url_for("random_pick"),
        obj=obj,
    )


@app.route("/random")
def random_pick():
    oid = pick_random_object()
    if not oid:
        abort(502, "未能随机获取作品，请稍后重试。")
    return redirect(url_for("object_detail", object_id=int(oid)))


if __name__ == "__main__":
    # 生产环境可以用：gunicorn -w 2 -b 0.0.0.0:5000 app:app
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
