import os
import sys
import io
import mido
import tkinter as tk
from tkinter import filedialog
from send2trash import send2trash

# --- CUSTOM RESCUE PARSER ---
# A bulletproof, pure-Python fallback parser that ignores structural errors, 
# proprietary GH/RB bytes, and EOF padding that cause mido to crash.

class MockMessage:
    def __init__(self, m_type, time=0, **kwargs):
        self.type = m_type
        self.time = time
        for k, v in kwargs.items():
            setattr(self, k, v)

class RescueMidiReader:
    def __init__(self, filepath):
        self.tracks = []
        self.ticks_per_beat = 480
        self.error = None
        self._load(filepath)
        
    def _load(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except Exception as e:
            self.error = str(e)
            return
            
        if len(data) < 14 or not data.startswith(b'MThd'):
            self.error = "Invalid header"
            return
            
        self.ticks_per_beat = int.from_bytes(data[12:14], 'big')
        
        idx = 14
        while idx + 8 <= len(data):
            ctype = data[idx:idx+4]
            if not ctype.isalpha():
                break # We hit console padding/garbage
                
            clen = int.from_bytes(data[idx+4:idx+8], 'big')
            
            if ctype == b'MTrk':
                safe_len = min(clen, len(data) - (idx + 8))
                t_data = data[idx+8 : idx+8+safe_len]
                self.tracks.append(self._parse_track(t_data))
                
            idx += 8 + clen
            
    def _parse_track(self, data):
        track = []
        idx = 0
        running_status = None
        
        def read_vlv():
            nonlocal idx
            val = 0
            while idx < len(data):
                b = data[idx]
                idx += 1
                val = (val << 7) | (b & 0x7f)
                if not (b & 0x80): break
            return val
            
        while idx < len(data):
            try:
                delta = read_vlv()
                if idx >= len(data): break
                
                b = data[idx]
                if b >= 0x80:
                    status = b
                    idx += 1
                    running_status = status
                else:
                    status = running_status
                    
                if status is None:
                    idx += 1
                    continue
                    
                cmd = status & 0xf0
                
                if cmd == 0x80:
                    note = data[idx]
                    vel = data[idx+1]
                    idx += 2
                    track.append(MockMessage('note_off', time=delta, note=note, velocity=0))
                elif cmd == 0x90:
                    note = data[idx]
                    vel = data[idx+1]
                    idx += 2
                    m_type = 'note_on' if vel > 0 else 'note_off'
                    track.append(MockMessage(m_type, time=delta, note=note, velocity=vel))
                elif cmd in (0xA0, 0xB0, 0xE0):
                    idx += 2
                elif cmd in (0xC0, 0xD0):
                    idx += 1
                elif status == 0xFF:
                    mtype = data[idx]
                    idx += 1
                    mlen = read_vlv()
                    mdata = data[idx:idx+mlen]
                    idx += mlen
                    
                    if mtype == 0x51 and len(mdata) == 3:
                        tempo = int.from_bytes(mdata, 'big')
                        track.append(MockMessage('set_tempo', time=delta, tempo=tempo))
                    elif mtype == 0x58 and len(mdata) >= 2:
                        track.append(MockMessage('time_signature', time=delta, numerator=mdata[0], denominator=2**mdata[1]))
                    elif mtype in (0x01, 0x05):
                        try: txt = mdata.decode('utf-8')
                        except: 
                            try: txt = mdata.decode('latin1')
                            except: txt = ""
                        track.append(MockMessage('text', time=delta, text=txt))
                    elif mtype == 0x03:
                        try: txt = mdata.decode('utf-8')
                        except: 
                            try: txt = mdata.decode('latin1')
                            except: txt = ""
                        track.append(MockMessage('track_name', time=delta, name=txt))
                elif status == 0xF0 or status == 0xF7:
                    slen = read_vlv()
                    idx += slen
                else:
                    # Ignore GH proprietary 0xF_ bytes without crashing
                    if status in (0xF1, 0xF3): idx += 1
                    elif status == 0xF2: idx += 2
                    
            except Exception:
                break # Salvage whatever valid events we parsed before hitting the corruption!
                
        return track
# ------------------------------

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

    config_template = f"""# Clone Hero Midi 2 Chart Configuration
# You can safely edit the path below using Notepad.
# Just make sure it points to your actual Clone Hero Songs directory.

{songs_directory}
"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(config_template)
    print(f"\033[32mSaved! You can change this path anytime by editing {CONFIG_FILE} in Notepad.\033[0m\n")
    
    return songs_directory

def get_note_lane(note):
    if 96 <= note <= 100: return ('Expert', note - 96)
    if note == 95: return ('Expert', 7) 
    if 84 <= note <= 88: return ('Hard', note - 84)
    if note == 83: return ('Hard', 7)
    if 72 <= note <= 76: return ('Medium', note - 72)
    if note == 71: return ('Medium', 7)
    if 60 <= note <= 64: return ('Easy', note - 60)
    if note == 59: return ('Easy', 7)
    return (None, None)

def get_modifier_zone(note):
    if note == 101: return ('Expert', 'HOPO')
    if note == 102: return ('Expert', 'STRUM')
    if note == 104: return ('Expert', 'TAP')
    
    if note == 89: return ('Hard', 'HOPO')
    if note == 90: return ('Hard', 'STRUM')
    if note == 92: return ('Hard', 'TAP')
    
    if note == 77: return ('Medium', 'HOPO')
    if note == 78: return ('Medium', 'STRUM')
    if note == 80: return ('Medium', 'TAP')
    
    if note == 65: return ('Easy', 'HOPO')
    if note == 66: return ('Easy', 'STRUM')
    if note == 68: return ('Easy', 'TAP')
    return (None, None)

def is_structural_pitch(note):
    if note == 116: return True
    if note in [101, 102, 103, 104, 105, 106]: return True 
    if note in [89, 90, 91, 92, 93, 94]: return True 
    if note in [77, 78, 79, 80, 81, 82]: return True 
    if note in [65, 66, 67, 68, 69, 70]: return True 
    return False

def is_in_zone(note_start, z_start, z_end, fuzz=2):
    if z_start == z_end:
        return abs(note_start - z_start) <= fuzz
    return (z_start - fuzz) <= note_start <= (z_end + fuzz)

def snap_and_quantize(notes, threshold=6):
    if not notes: return []
    notes.sort(key=lambda x: x[0])
    snapped = []
    chord_start = notes[0][0]
    for start, lane, length in notes:
        if abs(start - chord_start) <= threshold:
            snapped.append((chord_start, lane, length))
        else:
            chord_start = start
            snapped.append((chord_start, lane, length))
    return snapped

def calculate_1to1_toggles(notes_list, resolution, f_strum, f_hopo, f_tap):
    from collections import defaultdict
    ticks = defaultdict(list)
    lengths = {}
    
    for start, lane, length in notes_list:
        ticks[start].append(lane)
        if (start, lane) not in lengths or length > lengths[(start, lane)]:
            lengths[(start, lane)] = length
            
    sorted_ticks = sorted(ticks.keys())
    final_strings = set()
    
    prev_tick = -99999
    prev_lanes = []
    
    hopo_threshold = (resolution * 170) / 480.0
    
    for tick in sorted_ticks:
        current_lanes = ticks[tick]
        is_chord = len(current_lanes) > 1
        
        if is_chord:
            natural_state = "STRUM"
        elif not prev_lanes:
            natural_state = "STRUM"
        elif len(prev_lanes) == 1 and current_lanes[0] == prev_lanes[0]:
            natural_state = "STRUM" 
        elif (tick - prev_tick) <= hopo_threshold:
            natural_state = "HOPO"
        else:
            natural_state = "STRUM"
            
        is_tap = False
        for (z_start, z_end) in f_tap:
            if is_in_zone(tick, z_start, z_end):
                is_tap = True
                break
                
        target_state = natural_state
        active_zone_start = -1
        
        if not is_tap:
            for (z_start, z_end) in f_hopo:
                if is_in_zone(tick, z_start, z_end):
                    if z_start > active_zone_start:
                        active_zone_start = z_start
                        target_state = "HOPO"
                        
            for (z_start, z_end) in f_strum:
                if is_in_zone(tick, z_start, z_end):
                    if z_start > active_zone_start:
                        active_zone_start = z_start
                        target_state = "STRUM"
                        
        for lane in current_lanes:
            length = lengths[(tick, lane)]
            if length <= (resolution / 3.0):
                length = 0
                
            final_strings.add((tick, f"  {tick} = N {lane} {length}"))
            
            if is_tap:
                final_strings.add((tick, f"  {tick} = N 6 0"))
            elif target_state != natural_state:
                final_strings.add((tick, f"  {tick} = N 5 0"))
                
        prev_tick = tick
        prev_lanes = current_lanes
        
    return final_strings

def convert_midi_to_chart(midi_path, chart_path):
    try:
        # Step 1: Try strict standard utf-8 mido parsing
        mid = mido.MidiFile(midi_path, clip=True, charset='utf-8')
    except Exception:
        # Step 2: If mido throws ANY fit (EOFError, encoding, etc.), 
        # instantly switch to the custom bulletproof Rescue Reader.
        mid = RescueMidiReader(midi_path)
        if mid.error:
            print(f"  [!] Failed to read MIDI entirely: {mid.error}")
            return False
        print("  [*] Note: Rescued corrupted track via custom parser")
            
    resolution = mid.ticks_per_beat
    sync_track = []
    events = []
    global_notes_data = {}
    
    for idx, track in enumerate(mid.tracks):
        track_name = ""
        for msg in track:
            if msg.type == 'track_name':
                track_name = str(msg.name).upper().strip()
                break
                
        if not track_name:
            track_name = f"TRACK_{idx}"
            
        if 'ANIM' in track_name or 'REAL' in track_name or 'VOCAL' in track_name or 'HARM' in track_name:
            continue
            
        instrument = None
        if 'BASS' in track_name or 'T2 GEMS' in track_name: instrument = 'DoubleBass'
        elif 'DRUM' in track_name or 'T4 GEMS' in track_name: instrument = 'Drums'
        elif 'KEY' in track_name or 'T5 GEMS' in track_name: instrument = 'Keyboard'
        elif 'RHYTHM' in track_name or 'T3 GEMS' in track_name: instrument = 'DoubleRhythm'
        elif 'GUITAR' in track_name or 'T1 GEMS' in track_name: instrument = 'Single'
        
        raw_pitches = set()
        abs_time = 0
        for msg in track:
            abs_time += msg.time
            if msg.type == 'time_signature':
                sync_track.append((abs_time, f"  {abs_time} = TS {msg.numerator}"))
            elif msg.type == 'set_tempo':
                chart_bpm = int((60000000 / msg.tempo) * 1000)
                sync_track.append((abs_time, f"  {abs_time} = B {chart_bpm}"))
            elif msg.type in ['lyrics', 'text']:
                text = str(msg.text).strip()
                if text:
                    events.append((abs_time, f'  {abs_time} = E "{text}"'))
            elif msg.type == 'note_on' and msg.velocity > 0:
                raw_pitches.add(msg.note)
                
        if not instrument and track_name.startswith("TRACK_") and len(raw_pitches) > 0:
            if idx == 1: instrument = "Single"
            elif idx == 2: instrument = "DoubleBass"
            elif idx == 3: instrument = "DoubleRhythm"
            elif idx == 4: instrument = "Drums"
            else: instrument = f"Unknown_{idx}"
            
        if instrument:
            active_notes = {}
            track_notes = {'Expert': [], 'Hard': [], 'Medium': [], 'Easy': []}
            f_strum = {'Expert': [], 'Hard': [], 'Medium': [], 'Easy': []}
            f_hopo = {'Expert': [], 'Hard': [], 'Medium': [], 'Easy': []}
            f_tap = {'Expert': [], 'Hard': [], 'Medium': [], 'Easy': []}
            star_power_zones = [] 
            
            abs_time = 0
            for msg in track:
                abs_time += msg.time
                if msg.type == 'note_on' and msg.velocity > 0:
                    active_notes[msg.note] = abs_time
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active_notes:
                        start = active_notes.pop(msg.note)
                        length = abs_time - start
                        
                        if msg.note == 116:
                            star_power_zones.append((start, start + length))
                        else:
                            diff, lane = get_note_lane(msg.note)
                            if diff:
                                track_notes[diff].append((start, lane, length))
                            else:
                                mod_diff, mod_type = get_modifier_zone(msg.note)
                                if mod_diff:
                                    if mod_type == 'STRUM': f_strum[mod_diff].append((start, start + length))
                                    elif mod_type == 'HOPO': f_hopo[mod_diff].append((start, start + length))
                                    elif mod_type == 'TAP': f_tap[mod_diff].append((start, start + length))
                                    
            total_extracted = sum(len(lst) for lst in track_notes.values())
            
            if total_extracted == 0 and len(raw_pitches) > 0:
                sorted_p = sorted([p for p in raw_pitches if not is_structural_pitch(p)])
                if sorted_p:
                    abs_time = 0
                    active_notes_rescue = {}
                    for msg in track:
                        abs_time += msg.time
                        if msg.type == 'note_on' and msg.velocity > 0:
                            active_notes_rescue[msg.note] = abs_time
                        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                            if msg.note in active_notes_rescue:
                                start = active_notes_rescue.pop(msg.note)
                                length = abs_time - start
                                
                                if not is_structural_pitch(msg.note):
                                    try:
                                        p_idx = sorted_p.index(msg.note)
                                        lane = p_idx
                                        if lane > 4: lane = 4 
                                        track_notes['Expert'].append((start, lane, length))
                                    except ValueError:
                                        pass
                                        
            for diff in track_notes:
                if len(track_notes[diff]) > 0:
                    section_name = f"{diff}{instrument}"
                    if section_name not in global_notes_data:
                        global_notes_data[section_name] = set()
                        
                    snapped_notes = snap_and_quantize(track_notes[diff])
                    chart_strings = calculate_1to1_toggles(snapped_notes, resolution, f_strum[diff], f_hopo[diff], f_tap[diff])
                    
                    for (t_start, data_str) in chart_strings:
                        global_notes_data[section_name].add((t_start, data_str))
                                
                    for (z_start, z_end) in star_power_zones:
                        global_notes_data[section_name].add((z_start, f"  {z_start} = S 2 {z_end - z_start}"))
                        
            final_count = sum(len(lst) for lst in track_notes.values())
            if final_count > 0:
                print(f"    -> Extracted {final_count} raw notes for [{instrument}]")

    total_notes = sum(len(lst) for lst in global_notes_data.values())
    if total_notes == 0:
        print("  [!] Error: No valid notes found in this MIDI. Skipping.")
        return False

    unique_sync = []
    seen = set()
    for item in sync_track:
        if item[1] not in seen:
            seen.add(item[1])
            unique_sync.append(item)
    unique_sync.sort(key=lambda x: (x[0], 0 if 'TS' in x[1] else 1)) 
    
    unique_events = []
    seen_events = set()
    for item in events:
        if item[1] not in seen_events:
            seen_events.add(item[1])
            unique_events.append(item)
    unique_events.sort(key=lambda x: x[0])
    
    with open(chart_path, 'w', encoding='utf-8') as f:
        f.write("[Song]\n{\n")
        f.write(f"  Resolution = {resolution}\n")
        f.write("}\n")
        
        f.write("[SyncTrack]\n{\n")
        if not unique_sync:
            f.write("  0 = TS 4\n  0 = B 120000\n")
        else:
            for _, line in unique_sync: f.write(line + "\n")
        f.write("}\n")
        
        f.write("[Events]\n{\n")
        for _, line in unique_events: f.write(line + "\n")
        f.write("}\n")
        
        for section in global_notes_data:
            sorted_notes = sorted(list(global_notes_data[section]), key=lambda x: (x[0], x[1]))
            if sorted_notes:
                f.write(f"[{section}]\n{{\n")
                for _, line in sorted_notes: f.write(line + "\n")
                f.write("}\n")

    return True

def headless_batch():
    print("Clone Hero Midi 2 Chart v1.0.2 initialized...\n")
    
    SONGS_DIRECTORY = setup_directory()
    
    if not SONGS_DIRECTORY or not os.path.exists(SONGS_DIRECTORY):
        print(f"ERROR: Cannot find the folder.\n")
        return

    count = 0
    for root, dirs, files in os.walk(SONGS_DIRECTORY):
        for filename in files:
            if filename.lower().endswith('.mid'):
                midi_path = os.path.join(root, filename)
                chart_path = os.path.join(root, "notes.chart")
                
                print(f"Parsing: {filename}...")
                success = convert_midi_to_chart(midi_path, chart_path)
                if success:
                    try:
                        send2trash(midi_path)
                        print(f"  -> Generated pure 1:1 notes.chart & trashed original .mid\n")
                        count += 1
                    except Exception as e:
                        print(f"  -> Converted, but failed to trash .mid: {e}\n")
                        
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
