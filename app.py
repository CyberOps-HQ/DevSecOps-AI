import os
import sqlite3

# 1. Hardcoded Secret / Credential
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

def fetch_user_profile(user_input):
    # 2. SQL Injection Vulnerability
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{user_input}'"
    cursor.execute(query)
    return cursor.fetchall()

def execute_system_cmd(user_cmd):
    # 3. Command Injection / Unsafe Execution
    os.system(user_cmd)


    /// 4. Insecure Deserialization