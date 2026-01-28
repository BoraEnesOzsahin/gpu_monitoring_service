u# admin_approve.py
import os
import requests
from dotenv import load_dotenv
import argparse

# Load .env variables
load_dotenv()

def approve_node(node_id):
    EMS_API_URL = os.environ["EMS_API_URL"]
    ADMIN_API_TOKEN = os.environ["ADMIN_API_TOKEN"]

    url = f"{EMS_API_URL}/api/v1/nodes/{node_id}/approve"
    headers = {
        "Authorization": f"Bearer {ADMIN_API_TOKEN}"
    }

    print(f"Approving node {node_id}...")

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            print("SUCCESS! Node approved.")
            print("Response:", resp.json())
        elif resp.status_code == 401:
            print("ERROR: Unauthorized - Token incorrect.")
        elif resp.status_code == 404:
            print("ERROR: Node not found.")
        else:
            print(f"ERROR: {resp.status_code} - {resp.text}")
    except Exception as e:
        print("Network error:", e)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Approve a pending node by node ID using the EMS admin API token."
    )
    parser.add_argument(
        "node_id",
        metavar="NODE_ID",
        type=str,
        help="The node ID to approve (e.g., cn-abc123)"
    )

    args = parser.parse_args()
    approve_node(args.node_id)
