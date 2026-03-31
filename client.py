import requests
import os
import argparse
import sys

COORDINATOR_URL = "http://localhost:8000"

def upload(args):
    """Handles uploading a local file to the distributed store."""
    if not os.path.exists(args.local_path):
        print(f"[-] Error: Local file '{args.local_path}' not found.")
        sys.exit(1)
        
    print(f"[*] Uploading '{args.local_path}' to '{args.remote_path}'...")
    with open(args.local_path, "rb") as f:
        resp = requests.post(f"{COORDINATOR_URL}/upload/", 
                             files={"file": f}, 
                             params={"custom_filename": args.remote_path})
    
    if resp.status_code == 200:
        print("[+] Upload successful!")
        print(resp.json())
    else:
        print(f"[-] Upload failed: {resp.text}")

def download(args):
    """Handles downloading a file from the distributed store."""
    print(f"[*] Downloading '{args.remote_path}' to '{args.local_dest}'...")
    resp = requests.get(f"{COORDINATOR_URL}/download/{args.remote_path}")
    
    if resp.status_code == 200:
        with open(args.local_dest, "wb") as f:
            f.write(resp.content)
        print(f"[+] Successfully downloaded to '{args.local_dest}'")
    else:
        print(f"[-] Download failed (Status {resp.status_code}): {resp.json().get('detail', 'Unknown error')}")

def list_files(args):
    """Lists files currently in the distributed store."""
    print(f"[*] Fetching file list (Prefix: '{args.prefix}')...")
    resp = requests.get(f"{COORDINATOR_URL}/list/", params={"prefix": args.prefix})
    
    if resp.status_code == 200:
        files = resp.json()
        if not files:
            print("[-] No files found.")
            return
            
        print(f"\n{'FILENAME':<40} | {'SIZE (BYTES)':<15}")
        print("-" * 60)
        for f in files:
            print(f"{f['filename']:<40} | {f['size_bytes']:<15}")
        print("-" * 60)
        print(f"Total Files: {len(files)}\n")
    else:
        print(f"[-] Failed to list files: {resp.text}")

def corrupt(args):
    """
    Simulates a hacker attack or bit-rot.
    We tell the Coordinator to tell a specific node to ruin its piece of the file.
    """
    print(f"[*] Simulating attack on Node {args.node_id} for file '{args.remote_path}'...")
    # We will hit the new admin endpoint we are about to add to the Coordinator
    resp = requests.post(f"{COORDINATOR_URL}/admin/corrupt/{args.node_id}/{args.remote_path}")
    
    if resp.status_code == 200:
        print(f"[+] Attack successful! Node {args.node_id}'s fragment is now corrupted.")
    else:
        print(f"[-] Attack failed: {resp.text}")

def main():
    parser = argparse.ArgumentParser(
        description="SecStore CLI: Interact with the Distributed Object Store with Integrity.",
        epilog="Use 'python client.py <command> --help' for more information on a specific command."
    )
    
    subparsers = parser.add_subparsers(title="Commands", dest="command", required=True)

    # --- UPLOAD COMMAND ---
    parser_upload = subparsers.add_parser("upload", help="Upload a file to the distributed store")
    parser_upload.add_argument("local_path", type=str, help="Path to the local file on your computer")
    parser_upload.add_argument("remote_path", type=str, help="The virtual path/name to save it as (e.g., /docs/secret.txt)")
    parser_upload.set_defaults(func=upload)

    # --- DOWNLOAD COMMAND ---
    parser_download = subparsers.add_parser("download", help="Download a file from the distributed store")
    parser_download.add_argument("remote_path", type=str, help="The virtual path/name in the store")
    parser_download.add_argument("local_dest", type=str, help="Where to save the downloaded file locally")
    parser_download.set_defaults(func=download)

    # --- LIST COMMAND ---
    parser_list = subparsers.add_parser("list", help="List all files in the distributed store")
    parser_list.add_argument("--prefix", type=str, default="", help="Filter files by a directory prefix (e.g., /docs/)")
    parser_list.set_defaults(func=list_files)

    # --- CORRUPT COMMAND ---
    parser_corrupt = subparsers.add_parser("corrupt", help="[DEMO] Intentionally corrupt a node's fragment")
    parser_corrupt.add_argument("node_id", type=int, choices=[1, 2, 3], help="The Node ID to attack (1, 2, or 3)")
    parser_corrupt.add_argument("remote_path", type=str, help="The file to attack")
    parser_corrupt.set_defaults(func=corrupt)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
