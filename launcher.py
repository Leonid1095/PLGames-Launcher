import tkinter as tk
from tkinter import messagebox
import os
import subprocess
import time
import threading
import json
import requests

# Configuration
# TODO: User must replace this with their actual raw github url
UPDATE_URL = "https://raw.githubusercontent.com/USER/REPO/main/version.json" 
SERVER_REALMLIST = "set realmlist lkds-room.online"
WOW_EXE = "wow.exe"
VERSION_FILE = "version.json"
REALMLIST_PATHS = [
    "Data/ruRU/realmlist.wtf",
    "Data/enUS/realmlist.wtf",
    "realmlist.wtf" # Fallback
]

class WowLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("PLGames Launcher")
        self.root.geometry("600x450")
        self.root.configure(bg="#000000")
        
        # Header
        self.label_title = tk.Label(root, text="PLGAMES: CHRONOS", font=("Helvetica", 24, "bold"), fg="#fca311", bg="#000000")
        self.label_title.pack(pady=40)

        # Status
        self.status_var = tk.StringVar()
        self.status_var.set("Initializing...")
        self.label_status = tk.Label(root, textvariable=self.status_var, font=("Arial", 10), fg="#888888", bg="#000000")
        self.label_status.pack(pady=5)
        
        # Progress info
        self.progress_var = tk.StringVar()
        self.label_progress = tk.Label(root, textvariable=self.progress_var, font=("Arial", 9), fg="#fca311", bg="#000000")
        self.label_progress.pack(pady=5)

        # Play Button
        self.btn_play = tk.Button(root, text="PLAY NOW", font=("Arial", 16, "bold"), 
                                  bg="#fca311", fg="#000000", bd=0, padx=40, pady=15, 
                                  command=self.launch_game, state="disabled")
        self.btn_play.pack(pady=20)
        
        # Start update check
        threading.Thread(target=self.run_update_check, daemon=True).start()

    def get_local_version(self):
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('version', 0)
            except:
                return 0
        return 0

    def save_local_version(self, version_data):
        try:
            with open(VERSION_FILE, 'w') as f:
                json.dump(version_data, f, indent=4)
        except Exception as e:
            print(f"Failed to save version: {e}")

    def run_update_check(self):
        self.status_var.set("Checking for updates...")
        
        try:
            # 1. Fetch Remote Version
            # timeout for safety
            response = requests.get(UPDATE_URL, timeout=5)
            
            if response.status_code != 200:
                # If 404/Connection error, assume no update server -> Playable
                self.status_var.set("Update server unavailable. Ready to play.")
                self.btn_play.config(state="normal")
                return

            remote_data = response.json()
            remote_ver = remote_data.get('version', 0)
            local_ver = self.get_local_version()

            if remote_ver > local_ver:
                self.perform_update(remote_data)
            else:
                self.status_var.set(f"Client is up to date (v{local_ver}).")
                self.btn_play.config(state="normal")

        except Exception as e:
            print(f"Update check failed: {e}")
            self.status_var.set("Offline Mode / Error checking updates.")
            self.btn_play.config(state="normal")

    def perform_update(self, version_data):
        self.status_var.set("Update found! Downloading...")
        files = version_data.get('files', [])
        total_files = len(files)
        
        for idx, file_info in enumerate(files):
            url = file_info.get('url')
            path = file_info.get('path')
            
            if not url or not path:
                continue
                
            self.progress_var.set(f"Downloading {idx+1}/{total_files}: {os.path.basename(path)}")
            
            try:
                # Ensure dir exists
                os.makedirs(os.path.dirname(path), exist_ok=True)
                
                # Stream download
                r = requests.get(url, stream=True)
                if r.status_code == 200:
                    with open(path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                else:
                    print(f"Failed to download {url}")
                    
            except Exception as e:
                print(f"Error downloading {path}: {e}")
        
        self.progress_var.set("")
        self.save_local_version(version_data)
        self.status_var.set(f"Update Complete (v{version_data.get('version')}). Ready to play.")
        self.btn_play.config(state="normal")

    def set_realmlist(self):
        target_file = None
        for path in REALMLIST_PATHS:
            if os.path.exists(path):
                target_file = path
                break
        
        if not target_file:
            if os.path.exists("Data/ruRU"):
                target_file = "Data/ruRU/realmlist.wtf"
            else:
                target_file = "realmlist.wtf"
        
        try:
            with open(target_file, "w") as f:
                f.write(SERVER_REALMLIST)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update realmlist: {e}")
            return False

    def launch_game(self):
        if self.set_realmlist():
            if os.path.exists(WOW_EXE):
                subprocess.Popen([WOW_EXE])
                self.root.destroy()
            else:
                messagebox.showerror("Error", f"Could not find {WOW_EXE} in current directory.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WowLauncher(root)
    root.mainloop()
