#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess
from pathlib import Path

def update_document_ids(data, sheet_id):
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k == "documentId":
                if isinstance(v, dict) and "value" in v:
                    v["value"] = sheet_id
                    new_dict[k] = v
                elif isinstance(v, str):
                    new_dict[k] = sheet_id
                else:
                    new_dict[k] = v
            else:
                new_dict[k] = update_document_ids(v, sheet_id)
        return new_dict
    elif isinstance(data, list):
        return [update_document_ids(item, sheet_id) for item in data]
    else:
        return data

def main():
    parser = argparse.ArgumentParser(description="Inject Google Sheet Document ID into n8n workflows and re-import them.")
    parser.add_argument("sheet_id", help="The Google Sheet Document ID (from Google Sheets URL)")
    args = parser.parse_args()
    
    sheet_id = args.sheet_id.strip()
    if not sheet_id:
        print("[-] Please provide a valid Sheet ID.", file=sys.stderr)
        return 1
        
    workflow_dir = Path(os.environ.get("JOBHUNT_ROOT", str(Path.home() / "JobHunt"))) / "n8n_workflows"
    print(f"[*] Injecting Sheet ID '{sheet_id}' into n8n workflows under {workflow_dir}...")
    
    json_files = list(workflow_dir.glob("*.json"))
    if not json_files:
        print("[-] No JSON workflow files found.", file=sys.stderr)
        return 1
        
    for fpath in json_files:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
            
            updated_data = update_document_ids(data, sheet_id)
            
            with open(fpath, "w") as f:
                json.dump(updated_data, f, indent=2)
            print(f"[+] Updated: {fpath.name}")
        except Exception as e:
            print(f"[-] Failed to update {fpath.name}: {e}", file=sys.stderr)
            return 1
            
    # Run setup.sh to re-import
    setup_script = workflow_dir / "setup.sh"
    if setup_script.exists():
        print("[*] Re-importing updated workflows into n8n...")
        res = subprocess.run([str(setup_script)])
        if res.returncode == 0:
            print("[+] Successfully injected Sheet ID and re-imported all workflows!")
            return 0
        else:
            print(f"[-] setup.sh failed with exit code: {res.returncode}", file=sys.stderr)
            return res.returncode
    else:
        print("[-] n8n setup.sh script not found.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
