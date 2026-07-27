import streamlit as st
import requests

try:
    API_URL = st.secrets["API_URL"]
except Exception:
    API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="My Assistant", page_icon="🤖")

if "token" not in st.session_state:
    st.session_state.token = None
if "messages" not in st.session_state:
    st.session_state.messages = []

def login(username, password):
    response = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
    if response.status_code == 200:
        st.session_state.token = response.json()["access_token"]
        st.session_state.username = username
        return True
    return False

def register(username, password):
    response = requests.post(f"{API_URL}/register", json={"username": username, "password": password})
    return response.status_code == 200

if st.session_state.token is None:
    st.title("Sign in")
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            if login(username, password):
                st.rerun()
            else:
                st.error("Invalid credentials")

    with register_tab:
        new_username = st.text_input("Username", key="reg_user")
        new_password = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Create account"):
            if register(new_username, new_password):
                st.success("Account created, now log in")
            else:
                st.error("Username already taken")

else:
    st.title(f"Hi, {st.session_state.username}")

    with st.sidebar:
        st.subheader("Upload a note (PDF)")
        uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"])
        if uploaded_file and st.button("Upload"):
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            response = requests.post(f"{API_URL}/notes/upload-pdf", files=files, headers=headers)
            if response.status_code == 200:
                st.success(response.json()["message"])
            else:
                st.error("Upload failed.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["text"])

    user_input = st.chat_input("Type a message...")
    if user_input:
        st.session_state.messages.append({"role": "user", "text": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        response = requests.post(
            f"{API_URL}/chat",
            json={"message": user_input, "thread_id": st.session_state.username},
            headers=headers
        )

        if response.status_code == 200:
            reply_text = response.json()["reply"]
        else:
            reply_text = "Error: session expired, reload the page and log in again."

        st.session_state.messages.append({"role": "assistant", "text": reply_text})
        with st.chat_message("assistant"):
            st.write(reply_text)