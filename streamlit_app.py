import streamlit as st
import pandas as pd
import requests
import time
import io
import streamlit as st

# =======================
# App UI + Logic (Streamlit)
# =======================
st.set_page_config(page_title="Lock Outcome Tool", layout="centered")
st.title("🔐 Khóa tài khoản - OutCome")

with st.form("lock_form"):
    token = st.text_input("Nhập Access-Client-Token", type="password")
    file = st.file_uploader("Tải lên file lock_outcome.csv", type=["csv"])
    max_workers = st.number_input("Số luồng xử lý song song", min_value=1, max_value=20, value=5)
    submitted = st.form_submit_button("✅ Bắt đầu xử lý")



if submitted:
    if not token:
        st.error("🔒 Bạn chưa nhập Access Token")
    elif not file:
        st.error("📁 Bạn chưa tải file CSV")
    else:
        st.success("✨ Đang xử lý...")
        df = pd.read_csv(file)
        headers = {
            "Access-Client-Token": token,
            "Content-Type": "application/json"
        }

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def get_version(userid):
            uid = "'" + str(userid)
            url = f"https://wallet.vndc.io/api/users/{uid}/data-for-edit"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                return resp.json().get("user", {}).get("version")
            except:
                return None

        def lock_user(userid, comment, version):
            uid = "'" + str(userid)
            url = f"https://wallet.vndc.io/api/users/{uid}"
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
            if not version:
                return [uid, False, None, "versionInfo not found", 0]
            success, status, msg = lock_user(uid, comment, version)
            duration = round(time.time() - start, 3)
            return [uid, success, status, msg, duration]

        users = df.to_dict(orient='records')
        results = []
        start_all = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_user = {
                executor.submit(process, row['userid'], row.get('comment', '')): row['userid']
                for row in users
            }
            for future in as_completed(future_to_user):
                results.append(future.result())

        duration_all = round(time.time() - start_all, 2)
        st.success(f"⏱️ Xử lý hoàn tất sau {duration_all} giây")

        result_df = pd.DataFrame(results, columns=['userid', 'success', 'status_code', 'msg', 'duration_seconds'])
        st.dataframe(result_df)

        # Tạo file download
        output = io.StringIO()
        result_df.to_csv(output, index=False)
        st.download_button(
            label="📁 Tải file kết quả CSV",
            data=output.getvalue(),
            file_name="lock_outcome_result.csv",
            mime="text/csv"
        )
