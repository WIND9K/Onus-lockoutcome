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
logs = []

def format_userid(userid):
    uid_str = str(userid)
    if len(uid_str) > 15:
        return f'"{uid_str}"'  # Sử dụng dấu nháy kép cho số lớn
    else:
        return f"'{uid_str}'"  # Dùng nháy đơn cho số thường
# =======================

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
            uid = format_userid(userid)
            url = f"https://wallet.vndc.io/api/users/{uid}/data-for-edit"
            logs.append(f"[GET] {uid} -> {url}")
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                return resp.json().get("user", {}).get("version")
            except Exception as e:
                logs.append(f"[GET][LỖI] {uid}: {e}")
                return None

        def lock_user(userid, comment, version):
            uid = format_userid(userid)
            url = f"https://wallet.vndc.io/api/users/{uid}"
            body = {
                "customValues": {
                    "blocked_features": "create_evoucher|escrow_create|offchain_send|onchain_send|p2p|pay_ticket|sell_vndc_via_partner|sell_vndc_via_system|nami_futures_send|exchange|loan_create|loan_repayment",
                    "blocked_features_note": comment,
                    "frozen": "true"
                },
                "version": version
            }
            logs.append(f"[PUT] {uid} -> {url}")
            try:
                resp = requests.put(url, json=body, headers=headers, timeout=10)
                resp.raise_for_status()
                return True, resp.status_code, resp.text
            except Exception as e:
                logs.append(f"[PUT][LỖI] {uid}: {e}")
                return False, None, str(e)


        def process(uid, comment):
            start = time.time()
            version = get_version(uid)
            if not version:
                return [uid, False, None, "versionInfo not found", 0]
            success, status, msg = lock_user(uid, comment, version)
            duration = round(time.time() - start, 3)
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

        with st.expander("📜 Xem log chi tiết"):
            for log in logs:
                st.text(log)


        output = io.StringIO()
        result_df.to_csv(output, index=False)
        st.download_button(
            label="📁 Tải file kết quả CSV",
            data=output.getvalue(),
            file_name="lock_outcome_result.csv",
            mime="text/csv"
        )