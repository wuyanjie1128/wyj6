# app.py (Streamlit 版)
import random
import math
from typing import Dict, Any, List, Optional

import requests
import streamlit as st

APP_TITLE = "Explore Artworks • The MET (Streamlit)"
BASE_API = "https://collectionapi.metmuseum.org/public/collection/v1"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Explore-MET-Streamlit/1.0"})
TIMEOUT = 12


# --------------- API helpers ---------------

class MetAPIError(RuntimeError):
    pass


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        r = SESSION.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise MetAPIError(f"MET API 请求失败：{e}")


@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_departments() -> List[Dict[str, Any]]:
    data = _get_json(f"{BASE_API}/departments")
    return data.get("departments", [])


@st.cache_data(show_spinner=False, ttl=60 * 60, max_entries=4096)
def get_object(object_id: int) -> Dict[str, Any]:
    return _get_json(f"{BASE_API}/objects/{object_id}")


def search_objects(
    q: str,
    has_images: bool = True,
    department_id: Optional[int] = None,
    artist_or_culture: Optional[str] = None,
) -> List[int]:
    params: Dict[str, Any] = {"q": q or "*"}
    if has_images:
        params["hasImages"] = "true"
    if department_id:
        params["departmentId"] = int(department_id)
    if artist_or_culture:
        params["artistOrCulture"] = artist_or_culture

    data = _get_json(f"{BASE_API}/search", params=params)
    return data.get("objectIDs") or []


def pick_random_object(max_tries: int = 30) -> Optional[int]:
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


# --------------- UI state ---------------

st.set_page_config(page_title=APP_TITLE, page_icon="🎨", layout="wide")
st.title("🎨 Explore Artworks — The MET")

if "ids" not in st.session_state:
    st.session_state.ids = []
if "total" not in st.session_state:
    st.session_state.total = 0
if "page" not in st.session_state:
    st.session_state.page = 1
if "page_size" not in st.session_state:
    st.session_state.page_size = 12

# --------------- Sidebar filters ---------------

with st.sidebar:
    st.header("筛选")
    q = st.text_input("关键词（作品名、作者、题材…）", value="")
    has_images = st.checkbox("仅显示带图片", value=True)

    # 部门
    dept_list = []
    dept_error = None
    try:
        dept_list = get_departments()
    except MetAPIError as e:
        dept_error = str(e)

    dept_options = ["全部"] + [d["displayName"] for d in dept_list]
    dept_choice = st.selectbox("部门", dept_options, index=0)
    department_id = None
    if dept_choice != "全部":
        # 找出对应ID
        for d in dept_list:
            if d["displayName"] == dept_choice:
                department_id = d["departmentId"]
                break

    artist_or_culture = st.text_input("艺术家或文化（可选）", value="")

    page_size = st.selectbox("每页条数", [12, 16, 20, 24], index=[12,16,20,24].index(st.session_state.page_size))
    st.session_state.page_size = page_size

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        do_search = st.button("搜索", use_container_width=True)
    with col_btn2:
        do_random = st.button("来件随机作品", use_container_width=True)

# --------------- Actions ---------------

if do_random:
    with st.spinner("随机挑选中…"):
        oid = pick_random_object()
    if not oid:
        st.error("未能随机获取作品，请稍后再试。")
    else:
        try:
            obj = get_object(int(oid))
        except MetAPIError as e:
            st.error(str(e))
        else:
            st.subheader(obj.get("title") or "Untitled")
            cols = st.columns([2, 3])
            with cols[0]:
                img = obj.get("primaryImage") or obj.get("primaryImageSmall")
                if img:
                    st.image(img, use_column_width=True)
                else:
                    st.info("该作品无图像。")
            with cols[1]:
                st.write(f"**艺术家**：{obj.get('artistDisplayName') or 'Unknown'}")
                if obj.get("objectDate"):
                    st.write(f"**年代**：{obj.get('objectDate')}")
                if obj.get("medium"):
                    st.write(f"**媒介**：{obj.get('medium')}")
                if obj.get("department"):
                    st.write(f"**部门**：{obj.get('department')}")
                if obj.get("dimensions"):
                    st.write(f"**尺寸**：{obj.get('dimensions')}")
                if obj.get("culture"):
                    st.write(f"**文化**：{obj.get('culture')}")
                if obj.get("creditLine"):
                    st.write(f"**来源**：{obj.get('creditLine')}")
                if obj.get("repository"):
                    st.caption(obj.get("repository"))
                if obj.get("objectURL"):
                    st.link_button("在 MET 官方页查看 ↗", obj.get("objectURL"))
    st.divider()

if do_search:
    st.session_state.page = 1  # 新搜索回到第一页
    with st.spinner("搜索中…"):
        try:
            ids = search_objects(q, has_images, department_id, artist_or_culture or None)
            st.session_state.ids = ids
            st.session_state.total = len(ids)
        except MetAPIError as e:
            st.error(str(e))

# --------------- Results ---------------

total = st.session_state.total
ids = st.session_state.ids
page = st.session_state.page
page_size = st.session_state.page_size

# 翻页控件（只有有结果时显示）
if total:
    total_pages = max(1, math.ceil(total / page_size))
    left, mid, right = st.columns([1, 4, 1])
    with left:
        if st.button("← 上一页", disabled=(page <= 1)):
            st.session_state.page = max(1, page - 1)
            st.rerun()
    with mid:
        st.write(f"共 **{total}** 件结果 · 第 **{page}/{total_pages}** 页")
    with right:
        if st.button("下一页 →", disabled=(page >= total_pages)):
            st.session_state.page = min(total_pages, page + 1)
            st.rerun()

# 展示卡片
if total:
    start = (page - 1) * page_size
    end = start + page_size
    show_ids = ids[start:end]

    # 以 4 列网格展示
    cols = st.columns(4)
    for i, oid in enumerate(show_ids):
        with cols[i % 4]:
            try:
                obj = get_object(int(oid))
            except MetAPIError:
                continue
            title = obj.get("title") or "Untitled"
            img = obj.get("primaryImageSmall") or obj.get("primaryImage")
            if img:
                st.image(img, use_column_width=True)
            else:
                st.container(border=True).write("无图像")
            st.write(f"**{title}**")
            st.caption(obj.get("artistDisplayName") or "Unknown Artist")
            if obj.get("objectDate"):
                st.caption(obj.get("objectDate"))
            if obj.get("objectURL"):
                st.link_button("MET 官方页 ↗", obj.get("objectURL"))

elif any([q, department_id, (artist_or_culture or "").strip()]):
    st.info("未找到匹配结果，试试换个关键词或去掉筛选。")
else:
    st.caption("在左侧输入关键词开始探索，或点“来件随机作品”。")

# 部门加载提示
if dept_error:
    st.warning(f"部门列表加载失败：{dept_error}")
