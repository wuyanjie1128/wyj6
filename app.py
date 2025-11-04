# app.py  (Streamlit version)
import random
import math
from typing import Dict, Any, List, Optional
import requests
import streamlit as st

APP_TITLE = "Explore Artworks • The MET"
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
        raise MetAPIError(f"MET API request failed: {e}")


@st.cache_data(show_spinner=False, ttl=3600)
def get_departments() -> List[Dict[str, Any]]:
    data = _get_json(f"{BASE_API}/departments")
    return data.get("departments", [])


@st.cache_data(show_spinner=False, ttl=3600, max_entries=4096)
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
    """Pick a random artwork that has an image."""
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


# --------------- Streamlit UI ---------------

st.set_page_config(page_title=APP_TITLE, page_icon="🎨", layout="wide")
st.title("🎨 Explore Artworks — The Metropolitan Museum of Art")

if "ids" not in st.session_state:
    st.session_state.ids = []
if "total" not in st.session_state:
    st.session_state.total = 0
if "page" not in st.session_state:
    st.session_state.page = 1
if "page_size" not in st.session_state:
    st.session_state.page_size = 12

# Sidebar
with st.sidebar:
    st.header("Filters")
    q = st.text_input("Keyword (title, artist, theme…)", value="")
    has_images = st.checkbox("Only show artworks with images", value=True)

    # Department selector
    dept_list = []
    dept_error = None
    try:
        dept_list = get_departments()
    except MetAPIError as e:
        dept_error = str(e)

    dept_options = ["All"] + [d["displayName"] for d in dept_list]
    dept_choice = st.selectbox("Department", dept_options, index=0)
    department_id = None
    if dept_choice != "All":
        for d in dept_list:
            if d["displayName"] == dept_choice:
                department_id = d["departmentId"]
                break

    artist_or_culture = st.text_input("Artist or Culture (optional)", value="")

    page_size = st.selectbox("Items per page", [12, 16, 20, 24], index=0)
    st.session_state.page_size = page_size

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        do_search = st.button("Search", use_container_width=True)
    with col_btn2:
        do_random = st.button("Random Artwork", use_container_width=True)

# Random artwork
if do_random:
    with st.spinner("Picking a random artwork..."):
        oid = pick_random_object()
    if not oid:
        st.error("Failed to fetch a random artwork. Please try again.")
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
                    st.info("No image available.")
            with cols[1]:
                st.write(f"**Artist:** {obj.get('artistDisplayName') or 'Unknown'}")
                if obj.get("objectDate"):
                    st.write(f"**Date:** {obj.get('objectDate')}")
                if obj.get("medium"):
                    st.write(f"**Medium:** {obj.get('medium')}")
                if obj.get("department"):
                    st.write(f"**Department:** {obj.get('department')}")
                if obj.get("dimensions"):
                    st.write(f"**Dimensions:** {obj.get('dimensions')}")
                if obj.get("culture"):
                    st.write(f"**Culture:** {obj.get('culture')}")
                if obj.get("creditLine"):
                    st.write(f"**Credit Line:** {obj.get('creditLine')}")
                if obj.get("repository"):
                    st.caption(obj.get("repository"))
                if obj.get("objectURL"):
                    st.link_button("View on MET Museum ↗", obj.get("objectURL"))
    st.divider()

# Search
if do_search:
    st.session_state.page = 1
    with st.spinner("Searching artworks..."):
        try:
            ids = search_objects(q, has_images, department_id, artist_or_culture or None)
            st.session_state.ids = ids
            st.session_state.total = len(ids)
        except MetAPIError as e:
            st.error(str(e))

# Results
total = st.session_state.total
ids = st.session_state.ids
page = st.session_state.page
page_size = st.session_state.page_size

if total:
    total_pages = max(1, math.ceil(total / page_size))
    left, mid, right = st.columns([1, 4, 1])
    with left:
        if st.button("← Previous", disabled=(page <= 1)):
            st.session_state.page = max(1, page - 1)
            st.rerun()
    with mid:
        st.write(f"**{total}** results · Page **{page}/{total_pages}**")
    with right:
        if st.button("Next →", disabled=(page >= total_pages)):
            st.session_state.page = min(total_pages, page + 1)
            st.rerun()

    start = (page - 1) * page_size
    end = start + page_size
    show_ids = ids[start:end]

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
                st.container(border=True).write("No image")
            st.write(f"**{title}**")
            st.caption(obj.get("artistDisplayName") or "Unknown Artist")
            if obj.get("objectDate"):
                st.caption(obj.get("objectDate"))
            if obj.get("objectURL"):
                st.link_button("View on MET ↗", obj.get("objectURL"))

elif any([q, department_id, (artist_or_culture or "").strip()]):
    st.info("No artworks found. Try another keyword or remove filters.")
else:
    st.caption("Use the sidebar to start exploring, or click 'Random Artwork' to begin.")

if dept_error:
    st.warning(f"Failed to load department list: {dept_error}")
