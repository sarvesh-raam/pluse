import argparse
import sys
import httpx
import os

API_URL = "http://localhost:8000/api/v1"

def get_auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}

def login():
    print("Welcome to Pulse CLI.")
    email = input("Email: ")
    password = input("Password: ")
    
    try:
        r = httpx.post(f"{API_URL}/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        token = r.json()["access_token"]
        print(f"\nLogin successful! Export this token to use the CLI:")
        print(f"export PULSE_TOKEN={token}")
    except httpx.HTTPError:
        print("Login failed. Check your credentials.")

def cluster_status(token: str, project_id: str):
    try:
        r = httpx.get(f"{API_URL}/workers", params={"project_id": project_id}, headers=get_auth_headers(token))
        r.raise_for_status()
        workers = r.json()["items"]
        
        print(f"\nCluster Status (Project {project_id}):")
        print(f"{'ID':<38} | {'Hostname':<20} | {'Status':<10} | {'CPU %':<8} | {'RAM (MB)':<10}")
        print("-" * 95)
        for w in workers:
            cpu = f"{w.get('cpu_percent') or 0:.1f}%"
            ram = f"{w.get('ram_mb') or 0:.1f}"
            print(f"{w['id']:<38} | {w['hostname']:<20} | {w['status']:<10} | {cpu:<8} | {ram:<10}")
    except httpx.HTTPError as e:
        print(f"Error fetching cluster status: {e}")

def main():
    parser = argparse.ArgumentParser(description="Pulse CLI - Manage your distributed job scheduler")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Login
    subparsers.add_parser("login", help="Log in to get an access token")
    
    # Cluster
    cluster_parser = subparsers.add_parser("cluster", help="Manage cluster and workers")
    cluster_parser.add_argument("action", choices=["status"], help="Action to perform")
    cluster_parser.add_argument("--project", required=True, help="Your project UUID")
    
    args = parser.parse_args()
    
    if args.command == "login":
        login()
    elif args.command == "cluster":
        token = os.environ.get("PULSE_TOKEN")
        if not token:
            print("Error: PULSE_TOKEN environment variable is not set. Run 'python cli.py login' first.")
            sys.exit(1)
            
        if args.action == "status":
            cluster_status(token, args.project)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
