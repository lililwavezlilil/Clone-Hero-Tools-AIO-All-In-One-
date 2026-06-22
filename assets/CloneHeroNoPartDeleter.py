import os
import sys
import re
import tkinter as tk
from tkinter import filedialog
from send2trash import send2trash

def setup_directory():
    CONFIG_FILE = "CH_Settings.txt"
    songs_directory = None

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            lines = [line for line in f if line.strip() and not line.strip().startswith('#')]
            if lines:
                songs_directory = lines[0].strip()

    is_valid_dir = songs_directory and os.path.isdir(songs_directory)

    if is_valid_dir:
        return os.path.normpath(songs_directory)

    print("\033[36mFirst time setup: Please select your Clone Hero songs folder\033[0m")
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True) 
    
    songs_directory = filedialog.askdirectory(title="Please select your Clone Hero songs folder")
    
    if not songs_directory:
        print("\n\033[31mFolder selection cancelled. Exiting.\033[0m")
        return None  # Changed to return None so the script flows to the footer

    songs_directory = os.path.normpath(songs_directory)

    config_template = f"""# Clone Hero Batch-Deleter Configuration
# You can safely edit the path below using Notepad.
# Just make sure it points to your actual Clone Hero Songs directory.

{songs_directory}
"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(config_template)
    print(f"\033[32mSaved! You can change this path anytime by editing {CONFIG_FILE} in Notepad.\033[0m\n")
    return songs_directory

DRY_RUN = False  

CHART_PARTS_TO_KEEP = [
    "Single]",        # Lead Guitar
    "DoubleGuitar]",  # Co-op Guitar
    "DoubleBass]",    # Bass
    "DoubleRhythm]",  # Rhythm
    "Keyboard]"       # Keys
]

MID_REGEX_TO_KEEP = [
    rb"PART GUITAR(?!\sGHL)",
    rb"PART BASS(?!\sGHL)",
    rb"PART RHYTHM(?!\sGHL)",
    rb"PART KEYS",
    rb"T1 GEMS"       # Phase Shift fallback for Guitar
]

def has_required_instruments(folder_path):
    for file in os.listdir(folder_path):
        file_lower = file.lower()
        file_path = os.path.join(folder_path, file)
        
        if file_lower.endswith('.chart'):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if any(part in content for part in CHART_PARTS_TO_KEEP):
                        return True
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                
        elif file_lower.endswith(('.mid', '.midi')):
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    for pattern in MID_REGEX_TO_KEEP:
                        if re.search(pattern, content):
                            return True
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    return False

def clean_songs(songs_directory):
    folders_to_trash = []
    
    for root, dirs, files in os.walk(songs_directory):
        is_song_folder = any(f.lower() in ['song.ini', 'notes.chart', 'notes.mid'] for f in files)
        
        if is_song_folder:
            if not has_required_instruments(root):
                folders_to_trash.append(root)
            dirs[:] = []
                
    if not folders_to_trash:
        print("\033[32mAll songs have Guitar, Bass, Rhythm, or Keys. Nothing to delete!\033[0m")
        return

    print(f"\033[33mFound {len(folders_to_trash)} songs missing Guitar, Bass, Rhythm, or Keys.\033[0m")
    
    for folder in folders_to_trash:
        if DRY_RUN:
            print(f"\033[36m[DRY RUN] Would delete:\033[0m {os.path.basename(folder)}")
        else:
            print(f"\033[31mMoving to Recycle Bin:\033[0m {os.path.basename(folder)}")
            try:
                send2trash(folder)
            except Exception as e:
                print(f"Failed to delete {folder}: {e}")

    if DRY_RUN:
        print("Dry run complete. No files were actually moved.")
        print("To actually delete files, change DRY_RUN = False in the script.")
    else:
        print("\033[35mCleanup complete! Check your Recycle Bin if you need to restore anything.\033[0m")

def run():
    print("Clone Hero No Part Deleter v1.0.1 initialized...\n") 
    
    SONGS_DIR = setup_directory()
    
    if SONGS_DIR and os.path.exists(SONGS_DIR):
        clean_songs(SONGS_DIR)
    elif SONGS_DIR:
        print(f"\033[31mError: The directory '{SONGS_DIR}' does not exist.\033[0m")
        
    # Guaranteed to print at the very bottom of every execution path
    print("\n" + "=" * 43)

if __name__ == "__main__":
    run()