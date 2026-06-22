import os
import sys
import mido
import tkinter as tk
from tkinter import filedialog
from send2trash import send2trash

# ==========================================
# CONFIGURATION & SETUP
# ==========================================
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
    root.destroy()
    
    if not songs_directory:
        print("\n\033[31mFolder selection cancelled. Exiting.\033[0m")
        sys.exit(0)

    songs_directory = os.path.normpath(songs_directory)

    config_template = f"""# Clone Hero Chart 2 Midi Configuration
# You can safely edit the path below using Notepad.
# Just make sure it points to your actual Clone Hero Songs directory.

{songs_directory}
"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(config_template)
    print(f"\033[32mSaved! You can change this path anytime by editing {CONFIG_FILE} in Notepad.\033[0m\n")
    
    return songs_directory

# ==========================================
# CORE CHART TO MIDI CONVERSION LOGIC
# ==========================================

PITCH_MAP = {
    'Expert': {0: 96, 1: 97, 2: 98, 3: 99, 4: 100, 7: 95, 5: 101, 6: 104, 'SP': 116},
    'Hard':   {0: 84, 1: 85, 2: 86, 3: 87, 4: 88,  7: 83, 5: 89,  6: 92,  'SP': 116},
    'Medium': {0: 72, 1: 73, 2: 74, 3: 75, 4: 76,  7: 71, 5: 77,  6: 80,  'SP': 116},
    'Easy':   {0: 60, 1: 61, 2: 62, 3: 63, 4: 64,  7: 59, 5: 65,  6: 68,  'SP': 116}
}

INSTRUMENT_MAP = {
    'Single': 'PART GUITAR',
    'DoubleBass': 'PART BASS',
    'DoubleRhythm': 'PART RHYTHM',
    'Keyboard': 'PART KEYS',
    'Drums': 'PART DRUMS'
}

def convert_chart_to_midi(chart_path, midi_path):
    sections = {}
    current_section = None
    
    try:
        with open(chart_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line == '{' or line == '}': continue
                
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    sections[current_section] = []
                elif current_section:
                    sections[current_section].append(line)
    except Exception as e:
        print(f"  [!] Failed to read .chart: {e}")
        return False

    resolution = 192
    for line in sections.get('Song', []):
        if 'Resolution' in line:
            parts = line.split('=')
            if len(parts) == 2:
                resolution = int(parts[1].strip())
                break

    mid = mido.MidiFile(ticks_per_beat=resolution)

    # TRACK 0: SyncTrack
    sync_track = mido.MidiTrack()
    sync_track.name = 'SYNC TRACK'
    sync_track.append(mido.MetaMessage('track_name', name='SYNC TRACK', time=0))
    
    sync_events = []
    for line in sections.get('SyncTrack', []):
        parts = line.split(' = ')
        if len(parts) == 2:
            tick = int(parts[0].strip())
            cmd = parts[1].strip().split()
            if cmd[0] == 'TS':
                num = int(cmd[1])
                sync_events.append((tick, mido.MetaMessage('time_signature', numerator=num, denominator=4, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0)))
            elif cmd[0] == 'B':
                cbpm = int(cmd[1])
                tempo = int(60_000_000_000 / cbpm)
                sync_events.append((tick, mido.MetaMessage('set_tempo', tempo=tempo, time=0)))

    # TRACK 1: Events
    event_track = mido.MidiTrack()
    event_track.name = 'EVENTS'
    event_track.append(mido.MetaMessage('track_name', name='EVENTS', time=0))
    
    events_list = []
    for line in sections.get('Events', []):
        parts = line.split(' = E ')
        if len(parts) == 2:
            tick = int(parts[0].strip())
            text = parts[1].strip().strip('"')
            events_list.append((tick, mido.MetaMessage('text', text=text, time=0)))

    def write_absolute_events_to_track(track_obj, absolute_events):
        absolute_events.sort(key=lambda x: x[0])
        last_tick = 0
        for tick, msg in absolute_events:
            delta = tick - last_tick
            msg.time = delta
            track_obj.append(msg)
            last_tick = tick

    write_absolute_events_to_track(sync_track, sync_events)
    write_absolute_events_to_track(event_track, events_list)
    mid.tracks.append(sync_track)
    mid.tracks.append(event_track)

    # INSTRUMENT TRACKS
    track_events = {} 

    for section_name, lines in sections.items():
        if section_name in ['Song', 'SyncTrack', 'Events']: continue

        diff = None
        inst_key = None
        for d in ['Expert', 'Hard', 'Medium', 'Easy']:
            if section_name.startswith(d):
                diff = d
                inst = section_name[len(d):]
                inst_key = INSTRUMENT_MAP.get(inst, f'PART {inst.upper()}')
                break

        if not diff: continue

        if inst_key not in track_events:
            track_events[inst_key] = []

        for line in lines:
            parts = line.split(' = ')
            if len(parts) != 2: continue
            
            tick = int(parts[0].strip())
            data = parts[1].strip().split()

            if data[0] == 'N':
                color = int(data[1])
                length = max(int(data[2]), 1) 
                
                pitch = PITCH_MAP[diff].get(color)
                if pitch:
                    track_events[inst_key].append((tick, 1, mido.Message('note_on', note=pitch, velocity=100, time=0)))
                    track_events[inst_key].append((tick + length, 0, mido.Message('note_off', note=pitch, velocity=0, time=0)))

            elif data[0] == 'S':
                length = max(int(data[2]), 1)
                pitch = PITCH_MAP[diff]['SP']
                track_events[inst_key].append((tick, 1, mido.Message('note_on', note=pitch, velocity=100, time=0)))
                track_events[inst_key].append((tick + length, 0, mido.Message('note_off', note=pitch, velocity=0, time=0)))

    parsed_instrument_count = 0
    for t_name, events in track_events.items():
        if not events: continue
        t = mido.MidiTrack()
        t.name = t_name
        t.append(mido.MetaMessage('track_name', name=t_name, time=0))
        
        events.sort(key=lambda x: (x[0], x[1]))

        last_tick = 0
        for tick, _, msg in events:
            delta = tick - last_tick
            msg.time = delta
            t.append(msg)
            last_tick = tick

        mid.tracks.append(t)
        parsed_instrument_count += 1

    if parsed_instrument_count == 0:
        print("  [!] Error: No valid notes found in this .chart. Skipping.")
        return False

    try:
        mid.save(midi_path)
    except Exception as e:
        print(f"  [!] Error saving MIDI file: {e}")
        return False
        
    return True

def headless_batch():
    print("Clone Hero Chart 2 Midi v1.0.1 initialized...\n")
    
    SONGS_DIRECTORY = setup_directory()
    
    if not SONGS_DIRECTORY or not os.path.exists(SONGS_DIRECTORY):
        print(f"ERROR: Cannot find the folder.\n")
        return

    count = 0
    for root, dirs, files in os.walk(SONGS_DIRECTORY):
        for filename in files:
            if filename.lower() == 'notes.chart':
                chart_path = os.path.join(root, filename)
                midi_path = os.path.join(root, "notes.mid")
                
                print(f"Parsing: {filename} in {os.path.basename(root)}...")
                success = convert_chart_to_midi(chart_path, midi_path)
                if success:
                    try:
                        send2trash(chart_path)
                        print(f"  -> Generated notes.mid & trashed original .chart\n")
                        count += 1
                    except Exception as e:
                        print(f"  -> Converted, but failed to trash .chart: {e}\n")
                        
    print(f"Done! Successfully converted {count} files.")

def run():
    try:
        headless_batch()
    except Exception as e:
        import traceback
        print("\n" + "!"*40)
        print("A CRITICAL ERROR OCCURRED:")
        traceback.print_exc()
        print("!"*40 + "\n")
    finally:
        print("\n" + "="*40)

if __name__ == "__main__":
    run()