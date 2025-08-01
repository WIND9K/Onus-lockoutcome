import streamlit as st
import pandas as pd
import requests
import time
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import os

# =======================
# App UI + Logic (Streamlit)
# =======================
st.set_page_config(page_title="Lock Outcome Tool", layout="centered")
st.title("🔐 Khóa tài khoản - OutCome")

# =======================
# Token Handling: Secrets -> .env -> Input
# =======================
load_dotenv()
token = None

def format_userid(uid, path=""):
    uid_str = str(uid).strip()
    if len(uid_str) < 16:
        return f"https://wallet.goonus.io/api/users/'{uid_str}{path}"
    else:
        return f"https://wallet.goonus.io/api/users/{uid_str}{path}"


# 1. Streamlit Cloud secrets
try:
    token = st.secrets["ACCESS_CLIENT_TOKEN"]
    st.success("🔑 Ứng dụng đã được cấp quyền")
except:
    token = os.getenv("ACCESS_CLIENT_TOKEN")
    if token:
        st.success("🔑 Access Token đã được nạp tự động qua .env")

with st.form("lock_form"):
    if not token:
        token = st.text_input("Nhập Access-Client-Token", type="password")
    file = st.file_uploader("Tải lên file lock_outcome.csv", type=["csv"])
    max_workers = st.number_input("Số luồng xử lý song song", min_value=1, max_value=10, value=5)
    submitted = st.form_submit_button("✅ Bắt đầu xử lý")

if submitted:
    if not token:
        st.error("🔒 Không có Access Token hợp lệ. Vui lòng cấu hình secrets hoặc nhập thủ công.")
    elif not file:
        st.error("📁 Bạn chưa tải file CSV")
    else:
        st.success("✨ Đang xử lý...")
        df = pd.read_csv(file)
        headers = {
            "Access-Client-Token": token,
            "Content-Type": "application/json"
        }

        def get_version(userid):
            url = format_userid(userid, "/data-for-edit")
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                user = data.get("user")
                if not user or "version" not in user:
                    st.warning(f"⚠️ Không tìm thấy version cho userid: {userid}")
                    return None
                return user["version"]
            except requests.exceptions.RequestException as e:
                st.error(f"❌ Lỗi lấy version cho userid: {userid}")
                st.code(f"URL: {url}\nStatus: {getattr(e.response, 'status_code', 'N/A')}\nBody: {getattr(e.response, 'text', 'N/A')}")
                return None


        def lock_user(userid, comment, version):
            url = format_userid(userid)
            body = {
                "customValues": {
                    "blocked_features": "create_evoucher|escrow_create|offchain_send|onchain_send|p2p|pay_ticket|sell_vndc_via_partner|sell_vndc_via_system|nami_futures_send|exchange|loan_create|loan_repayment",
                    "blocked_features_note": comment,
                    "frozen": "true"
                },
                "version": version
            }
            try:
                resp = requests.put(url, json=body, headers=headers, timeout=10)
                resp.raise_for_status()
                return True, resp.status_code, resp.text
            except Exception as e:
                return False, None, str(e)

        def process(uid, comment):
            start = time.time()
            version = get_version(uid)
            duration = round(time.time() - start, 3)

            if version is None:
                return [uid, False, None, "versionInfo not found", duration]

            success, status, msg = lock_user(uid, comment, version)
            return [uid, success, status, msg, duration]



        users = df.to_dict(orient='records')
        results = []
        errors = []
        start_all = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_user = {}
            for row in users:
                if isinstance(row, dict) and 'userid' in row:
                    future = executor.submit(process, row['userid'], row.get('comment', ''))
                    future_to_user[future] = row['userid']
                else:
                    errors.append([row, "Invalid row format"])

            for future in as_completed(future_to_user):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append([future_to_user[future], False, None, str(e), 0])

        duration_all = round(time.time() - start_all, 2)
        st.success(f"⏱️ Xử lý hoàn tất sau {duration_all} giây")

        result_df = pd.DataFrame(results, columns=['userid', 'success', 'status_code', 'msg', 'duration_seconds'])
        st.dataframe(result_df)

        output = io.StringIO()
        result_df.to_csv(output, index=False)
        st.download_button(
            label="📁 Tải file kết quả CSV",
            data=output.getvalue(),
            file_name="lock_outcome_result.csv",
            mime="text/csv"
        )
