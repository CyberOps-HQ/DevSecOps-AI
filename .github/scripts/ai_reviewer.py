import os
import sys
import json
import requests
from github import Github

# Initialize environment and tokens
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
REPO_NAME = os.getenv("REPO_NAME")
PR_NUMBER = int(os.getenv("PR_NUMBER")) if os.getenv("PR_NUMBER") else None

# Model Configuration
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"

def get_pr_files_and_diffs():
    """Fetch changed files and their patches from GitHub API."""
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    pr = repo.get_pull(PR_NUMBER)
    
    files = pr.get_files()
    file_diffs = []
    
    for file in files:
        # Ignore binary files, lockfiles, and media assets
        if file.filename.endswith(('.lock', '.png', '.jpg', '.pdf', '.svg', '.json')):
            continue
        if file.patch:
            file_diffs.append({
                "path": file.filename,
                "patch": file.patch
            })
            
    return pr, file_diffs

def analyze_diff_for_inline_comments(file_diffs):
    """Query Hugging Face model and request structured JSON array for inline findings."""
    system_prompt = (
        "You are an expert DevSecOps security auditor reviewing a Pull Request diff.\n"
        "Your goal is to identify specific security vulnerabilities and critical bugs and output inline comments.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- Respond ONLY in strict JSON format. Do not include markdown code blocks (```json ... ```) or conversational commentary.\n"
        "- The JSON must be an array of objects, where each object has:\n"
        "  * 'path': (string) Exact file path as given in the diff.\n"
        "  * 'line': (integer) The line number in the NEW file where the issue exists.\n"
        "  * 'body': (string) Concise security feedback and actionable code fix.\n"
        "- Only comment on lines that were ADDED or MODIFIED (lines prefixed with '+' in the patch).\n"
        "- If no issues are found, return an empty array: []\n\n"
        "JSON SCHEMA EXAMPLE:\n"
        "[\n"
        "  {\n"
        "    \"path\": \"app.py\",\n"
        "    \"line\": 12,\n"
        "    \"body\": \"🔒 **Security Vulnerability**: SQL Injection detected. Use parameterized queries instead of string interpolation.\"\n"
        "  }\n"
        "]"
    )

    # Format diffs payload
    diff_text = ""
    for fd in file_diffs:
        diff_text += f"\n--- File: {fd['path']} ---\n{fd['patch']}\n"
    
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Review this PR Diff and return JSON inline comments:\n{diff_text[:12000]}"}
        ],
        "temperature": 0.1,
        "max_tokens": 1500
    }

    response = requests.post(HF_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"Error from HF API ({response.status_code}): {response.text}")
        sys.exit(1)

    content = response.json()["choices"][0]["message"]["content"].strip()
    
    # Strip markdown wrapper if model accidentally included it
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response from model: {e}\nRaw Content: {content}")
        return []

def main():
    if not HF_TOKEN or not PR_NUMBER or not REPO_NAME:
        print("CRITICAL: Missing environment variables (HF_TOKEN, PR_NUMBER, REPO_NAME).")
        sys.exit(1)

    print(f"Fetching diffs for PR #{PR_NUMBER} in {REPO_NAME}...")
    pr, file_diffs = get_pr_files_and_diffs()

    if not file_diffs:
        print("No reviewable code changes detected. Exiting.")
        return

    print("Analyzing code changes for inline annotations...")
    inline_comments = analyze_diff_for_inline_comments(file_diffs)

    if not inline_comments:
        print("No inline issues found by AI auditor.")
        # Post a general approval/passing comment
        pr.create_issue_comment(f"## 🤖 DevSecOps AI Review (`{MODEL_ID}`)\n\n✅ No critical security issues or anti-patterns detected in this PR.")
        return

    # Filter comments to ensure they target valid changed files
    valid_paths = {fd["path"] for fd in file_diffs}
    comments_payload = []

    for comment in inline_comments:
        if isinstance(comment, dict) and "path" in comment and "line" in comment and "body" in comment:
            if comment["path"] in valid_paths:
                comments_payload.append({
                    "path": comment["path"],
                    "line": int(comment["line"]),
                    "body": f"🤖 **AI Reviewer (`{MODEL_ID}`):**\n\n{comment['body']}"
                })

    if not comments_payload:
        print("No valid inline comments matched the changed files.")
        return

    print(f"Posting {len(comments_payload)} inline annotations to PR #{PR_NUMBER}...")

    try:
        # Create a GitHub PR Review with inline comments
        pr.create_review(
            body=f"## 🤖 DevSecOps AI Review (`{MODEL_ID}`)\nFound {len(comments_payload)} inline issue(s) that require attention.",
            event="COMMENT", # Options: COMMENT, REQUEST_CHANGES, APPROVE
            comments=comments_payload
        )
        print("Successfully posted inline PR annotations!")
    except Exception as e:
        print(f"Error creating GitHub PR review: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()