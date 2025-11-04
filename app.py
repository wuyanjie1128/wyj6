# app.py
import os
import math
import random
from functools import lru_cache
from typing import Dict, Any, List, Optional

import requests
from flask import Flask, request, redirect, url_for, render_template_string, abort

APP_TITLE = "Explore Artworks • The MET"
BASE_API = "https://collectionapi.metmuseum.org/public/collection/v1"

app = Flask(__name__)

# ---------- Utilities ----------

class MetAPIError(RuntimeError):
    pass

def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()
        return resp.json()
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
    params = {"q": q or ""}

    # 常用可选参数：hasImages, departmentId, artistOrCulture
    if has_images:
        params["hasImages"] = "true"
    if department_id:
        params["departmentId"] = department_id
    if artist_or_culture:
        params["artistOrCulture"] = artist_or_culture

    data = _get_json(f"{BASE_API}/search", params=params)
    return data.get("objectIDs") or []

def pick_random_object(max_tries: int = 20) -> Optional[int]:
    """
    随机挑选一件“有图像”的作品。策略：
      1) 先取 /objects 拿到全集 ID
      2) 随机抽取，直到找到 hasPrimaryImage=True（限定最多 max_tries 次）
    """
    try:
        all_ids = _get_json(f"{BASE_API}/objects").get("objectIDs") or []
    except MetAPIError:
        return None
    if not all_ids:
        return None

    for _ in range(max_tries):
        oid = random.choice(all_ids)
        try:
            obj = get_object(oid)
            if obj.get("primaryImageSmall") or obj.get("primaryImage"):
                return oid
        except MetAPIError:
            continue
    return None

# ---------- Routes ----------

@app.route("/")
def index():
    # Query params
    q = request.args.get("q", "", type=str)
    has_images = request.args.get("hasImages", "true").lower() != "false"
    department_id = request.args.get("departmentId", type=int)
    artist_or_culture = request.args.get("artistOrCulture", "", type=str) or None
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 12, type=int), 1), 24)

    # Departments for filter
    try:
        departments = get_departments()
    except MetAPIError as e:
        departments = []
        dept_error = str(e)
    else:
        dept_error = None

    object_ids: List[int] = []
    total = 0
    page_ids: List[int] = []
    results: List[Dict[str, Any]] = []
    error: Optional[str] = None

    if q or department_id or artist_or_culture:
        try:
            object_ids = search_objects(q, has_images, department_id, artist_or_culture)
            total = len(object_ids)
            # Pagination slice
            start = (page - 1) * page_size
            end = start + page_size
            page_ids = object_ids[start:end]
            # Fetch object details for current page
            for oid in page_ids:
                try:
                    obj = get_object(int(oid))
                    results.append(obj)
                except MetAPIError:
                    continue
        except MetAPIError as e:
            error = str(e)

    total_pages = math.ceil(total / page_size) if total else 0

    return render_template_string(TEMPLATE_HOME,
        app_title=APP_TITLE,
        q=q,
        has_images=has_images,
        departments=departments,
        dept_error=dept_error,
        department_id=department_id,
        artist_or_culture=artist_or_culture or "",
        results=results,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        error=error
    )

@app.route("/object/<int:object_id>")
def object_detail(object_id: int):
    try:
        obj = get_object(object_id)
    except MetAPIError as e:
        abort(502, str(e))

    if not obj:
        abort(404, "作品未找到")

    return render_template_string(TEMPLATE_DETAIL,
        app_title=APP_TITLE,
        obj=obj
    )

@app.route("/random")
def random_pick():
    oid = pick_random_object()
    if not oid:
        abort(502, "未能随机获取作品，请稍后重试。")
    return redirect(url_for("object_detail", object_id=oid))

# ---------- Inline Templates (Tailwind + 一点小交互) ----------

TEMPLATE_BASE = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ app_title }}</title>
  <!-- Tailwind via CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <meta name="color-scheme" content="light dark">
  <style>
    .card:hover { transform: translateY(-2px); }
    .line-clamp-2 { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }
  </style>
</head>
<body class="min-h-screen bg-gray-50 text-gray-900">
  <header class="sticky top-0 z-40 backdrop-blur bg-white/80 border-b">
    <div class="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
      <a href="{{ url_for('index') }}" class="text-xl font-semibold">🎨 Explore Artworks</a>
      <span class="text-gray-400">|</span>
      <a href="{{ url_for('random_pick') }}" class="text-sm px-3 py-1 rounded-full bg-gray-900 text-white hover:bg-black">来件随机作品</a>
      <a href="https://www.metmuseum.org/art/collection" class="ml-auto text-sm text-gray-500 hover:text-gray-700" target="_blank" rel="noreferrer">The MET Collection ↗</a>
    </div>
  </header>
  {% block content %}{% endblock %}
  <footer class="py-10 text-center text-gray-400 text-sm">
    数据来源：The MET Collection API · 非官方示例应用
  </footer>
</body>
</html>
"""

TEMPLATE_HOME = r"""
{% extends none %}
""" + TEMPLATE_BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
  <main class="max-w-6xl mx-auto px-4">
    <section class="py-6">
      <form action="{{ url_for('index') }}" method="get" class="grid md:grid-cols-4 gap-3 bg-white p-4 rounded-2xl shadow">
        <div class="md:col-span-2">
          <label class="block text-sm text-gray-600 mb-1">关键词（作品名、作者、题材…）</label>
          <input name="q" value="{{ q }}" class="w-full rounded-xl border-gray-200" placeholder="如 van gogh / landscape / bronze">
        </div>
        <div>
          <label class="block text-sm text-gray-600 mb-1">部门</label>
          <select name="departmentId" class="w-full rounded-xl border-gray-200">
            <option value="">全部</option>
            {% if dept_error %}
              <option disabled>加载失败：{{ dept_error }}</option>
            {% else %}
              {% for d in departments %}
                <option value="{{ d.departmentId }}" {% if department_id==d.departmentId %}selected{% endif %}>{{ d.displayName }}</option>
              {% endfor %}
            {% endif %}
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

    {% if error %}
      <div class="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-6">{{ error }}</div>
    {% endif %}

    {% if total %}
      <p class="text-sm text-gray-600 mb-3">共找到 <b>{{ total }}</b> 件结果。</p>
      <section class="grid sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {% for item in results %}
          <a href="{{ url_for('object_detail', object_id=item.objectID) }}" class="card block bg-white rounded-2xl shadow hover:shadow-lg transition">
            {% if item.primaryImageSmall or item.primaryImage %}
              <img src="{{ item.primaryImageSmall or item.primaryImage }}" alt="{{ item.title or 'Artwork' }}" class="w-full h-56 object-cover rounded-t-2xl">
            {% else %}
              <div class="w-full h-56 bg-gray-100 rounded-t-2xl grid place-items-center text-gray-400">无图像</div>
            {% endif %}
            <div class="p-4 space-y-2">
              <h3 class="font-medium line-clamp-2">{{ item.title or 'Untitled' }}</h3>
              <p class="text-sm text-gray-600">{{ item.artistDisplayName or 'Unknown Artist' }}</p>
              <p class="text-xs text-gray-400">{{ item.objectDate or '' }}</p>
              {% if item.repository %}
                <p class="text-[11px] text-gray-400">{{ item.repository }}</p>
              {% endif %}
            </div>
          </a>
        {% endfor %}
      </section>

      {% if total_pages > 1 %}
      <nav class="flex items-center justify-center gap-2 my-8">
        {% set base_args = request.args.to_dict() %}
        {% set start = max(1, page-2) %}
        {% set end = min(total_pages, page+2) %}
        {% if page > 1 %}
          {% set prev_args = base_args.copy() %}{% set _ = prev_args.update({'page': page-1}) %}
          <a class="px-3 py-1 rounded border hover:bg-gray-100" href="{{ url_for('index') + '?' + (prev_args|tojson|safe)[1:-1].replace('\"', '').replace(': ', '=').replace(', ', '&') }}">上一页</a>
        {% endif %}
        {% for p in range(start, end+1) %}
          {% set p_args = base_args.copy() %}{% set _ = p_args.update({'page': p}) %}
          <a class="px-3 py-1 rounded border {% if p==page %}!bg-gray-900 !text-white{% else %}hover:bg-gray-100{% endif %}" href="{{ url_for('index') + '?' + (p_args|tojson|safe)[1:-1].replace('\"', '').replace(': ', '=').replace(', ', '&') }}">{{ p }}</a>
        {% endfor %}
        {% if page < total_pages %}
          {% set next_args = base_args.copy() %}{% set _ = next_args.update({'page': page+1}) %}
          <a class="px-3 py-1 rounded border hover:bg-gray-100" href="{{ url_for('index') + '?' + (next_args|tojson|safe)[1:-1].replace('\"', '').replace(': ', '=').replace(', ', '&') }}">下一页</a>
        {% endif %}
      </nav>
      {% endif %}
    {% elif q or department_id or artist_or_culture %}
      <div class="text-gray-500 py-10 text-center">未找到匹配结果，试试换个关键词或去掉筛选。</div>
    {% else %}
      <section class="py-10 text-center text-gray-600">
        <p>输入关键词开始探索，或点击“来件随机作品”。</p>
      </section>
    {% endif %}
  </main>
{% endblock %}
""")

TEMPLATE_DETAIL = r"""
{% extends none %}
""" + TEMPLATE_BASE.replace("{% block content %}{% endblock %}", r"""
{% block content %}
  <main class="max-w-5xl mx-auto px-4 py-8">
    <a href="{{ url_for('index') }}" class="text-sm text-gray-600 hover:text-gray-900">← 返回</a>
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
          <a class="inline-block px-4 py-2 rounded-xl border hover:bg-gray-100 ml-2" href="{{ url_for('random_pick') }}">换一件随机作品</a>
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
{% endblock %}
""")

# ---------- Entrypoint ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
