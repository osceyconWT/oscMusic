import curses
import os
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import random
import pygame
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import threading

def get_metadata(file_path):
    try:
        audio = MP3(file_path, ID3=EasyID3)
        # Add discnumber to the metadata
        discnum = audio.get("discnumber", ["1/1"])[0].split("/")[0]
        return {
            "title": audio.get("title", ["Unknown"])[0],
            "artist": audio.get("artist", ["Unknown"])[0],
            "album": audio.get("album", ["Unknown"])[0],
            "tracknumber": int(audio.get("tracknumber", ["0"])[0].split("/")[0]),
            "discnumber": int(discnum),  # Add disc number
            "length": int(audio.info.length),
        }
    except Exception:
        return {
            "title": "Unknown",
            "artist": "Unknown",
            "album": "Unknown",
            "tracknumber": 0,
            "discnumber": 1,  # Default disc number
            "length": 0,
        }

def organize_by_album(playlist):
    albums = {}
    for song in playlist:
        metadata = get_metadata(song)
        album = metadata["album"]
        if album not in albums:
            albums[album] = []
        albums[album].append((song, metadata))
    return albums

def sort_album_songs(songs):
    # Update sorting to consider disc number first, then track number
    return sorted(songs, key=lambda x: (x[1]["discnumber"], x[1]["tracknumber"], x[1]["title"]))

# Rest of your code remains exactly the same from here onwards...
def format_time(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02}:{seconds:02}"

class KDEMediaPlayerInterface(dbus.service.Object):
    MPRIS_INTERFACE = "org.mpris.MediaPlayer2.Player"
    PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"

    def __init__(self):
        DBusGMainLoop(set_as_default=True)
        self.loop = GLib.MainLoop()
        
        self.bus_name = "org.mpris.MediaPlayer2.PythonMusicPlayer"
        self.obj_path = "/org/mpris/MediaPlayer2"
        self.session_bus = dbus.SessionBus()
        self.bus = dbus.service.BusName(self.bus_name, self.session_bus)
        super().__init__(self.bus, self.obj_path)
        
        self.current_metadata = None
        self.is_playing = False
        
        self.thread = threading.Thread(target=self.loop.run)
        self.thread.daemon = True
        self.thread.start()

    @dbus.service.method(MPRIS_INTERFACE, in_signature='', out_signature='')
    def Play(self):
        global is_playing
        if not is_playing:
            curses.ungetch(ord(" "))

    @dbus.service.method(MPRIS_INTERFACE, in_signature='', out_signature='')
    def Pause(self):
        global is_playing
        if is_playing:
            curses.ungetch(ord(" "))

    @dbus.service.method(MPRIS_INTERFACE, in_signature='', out_signature='')
    def PlayPause(self):
        curses.ungetch(ord(" "))

    @dbus.service.method(MPRIS_INTERFACE, in_signature='', out_signature='')
    def Next(self):
        curses.ungetch(curses.KEY_DOWN)

    @dbus.service.method(MPRIS_INTERFACE, in_signature='', out_signature='')
    def Previous(self):
        curses.ungetch(curses.KEY_UP)

    @dbus.service.method(PROPERTIES_INTERFACE, in_signature='ss', out_signature='v')
    def Get(self, interface, prop):
        if interface == self.MPRIS_INTERFACE:
            if prop == 'PlaybackStatus':
                return "Playing" if self.is_playing else "Paused"
            elif prop == 'Metadata':
                if not self.current_metadata:
                    return dbus.Dictionary({}, signature='sv')
                return dbus.Dictionary({
                    'xesam:title': dbus.String(self.current_metadata["title"]),
                    'xesam:artist': dbus.Array([dbus.String(self.current_metadata["artist"])]),
                    'xesam:album': dbus.String(self.current_metadata["album"]),
                    'mpris:length': dbus.Int64(self.current_metadata["length"] * 1000000)
                }, signature='sv')
        return None

    @dbus.service.method(PROPERTIES_INTERFACE, in_signature='ssv')
    def Set(self, interface, prop, value):
        pass

    @dbus.service.method(PROPERTIES_INTERFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface == self.MPRIS_INTERFACE:
            return {
                'PlaybackStatus': self.Get(self.MPRIS_INTERFACE, 'PlaybackStatus'),
                'Metadata': self.Get(self.MPRIS_INTERFACE, 'Metadata')
            }
        return {}

    def update_metadata(self, metadata):
        self.current_metadata = metadata
        self.PropertiesChanged(self.MPRIS_INTERFACE, {'Metadata': self.Get(self.MPRIS_INTERFACE, 'Metadata')}, [])

    def update_playback_status(self, is_playing):
        self.is_playing = is_playing
        self.PropertiesChanged(self.MPRIS_INTERFACE, {'PlaybackStatus': self.Get(self.MPRIS_INTERFACE, 'PlaybackStatus')}, [])

    @dbus.service.signal(PROPERTIES_INTERFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed_properties, invalidated_properties):
        pass
    
def main(stdscr, playlist):
    # Initialize KDE interface
    kde_interface = KDEMediaPlayerInterface()
    
    # Keep all your existing variables
    curses.curs_set(0)
    stdscr.nodelay(True)
    albums = organize_by_album(playlist)
    album_names = list(albums.keys())
    album_names.append("view everything")

    is_playing = False
    loop_mode = "noloop"
    shuffle = False
    volume = 0.5
    pygame.mixer.init()
    pygame.mixer.music.set_volume(volume)

    current_album_index = 0
    in_album_view = True
    song_list = []
    current_song_index = 0
    scroll_offset = 0
    max_display = 10
    seek_position = 0

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        if in_album_view:
            stdscr.addstr(1, 1, "oscMusic player - v1.0 RELEASE - an oscey project")
            stdscr.addstr(2, 1, "your albums | arrow keys to nav, enter to select, q to quit")
            stdscr.addstr(3, 1, " ")
            for i in range(scroll_offset, min(scroll_offset + max_display, len(album_names))):
                prefix = ">> " if i == current_album_index else "   "
                album_name = album_names[i]
                truncated_name = (album_name[:width - 4] + "...") if len(album_name) > width - 4 else album_name
                stdscr.addstr(3 + (i - scroll_offset), 1, f"{prefix}{truncated_name}")
        else:
            if len(song_list) > 0:
                metadata = song_list[current_song_index][1]
                kde_interface.update_metadata(metadata)
                kde_interface.update_playback_status(is_playing)
                
                # Update display to show disc number
                stdscr.addstr(1, 1, f"now playing - {metadata['title']} - {metadata['artist']}")
                stdscr.addstr(2, 1, f"album - {metadata['album']} (Disc {metadata['discnumber']})")
                stdscr.addstr(3, 1, f"loop - {loop_mode} | shuffle - {'✓' if shuffle else '✘'} | volume: {int(volume * 100)}%")
                if pygame.mixer.music.get_busy():
                    current_time = pygame.mixer.music.get_pos() // 1000
                    stdscr.addstr(4, 1, f"time: {format_time(current_time)} / {format_time(metadata['length'])}")

                stdscr.addstr(6, 1, "songs")
                for i in range(scroll_offset, min(scroll_offset + max_display, len(song_list))):
                    prefix = ">> " if i == current_song_index else "   "
                    song_metadata = song_list[i][1]
                    # Include disc number in song info
                    song_info = f"[{song_metadata['discnumber']}-{song_metadata['tracknumber']:02d}] {song_metadata['title']} - {song_metadata['artist']}"
                    truncated_name = (song_info[:width - 4] + "...") if len(song_info) > width - 4 else song_info
                    stdscr.addstr(7 + (i - scroll_offset), 1, f"{prefix}{truncated_name}")

            stdscr.addstr(height - 2, 1, "[b]ack to albums | [v]olume +/- | seek: [<]/[>]")

        key = stdscr.getch()
        if key == ord("q"):
            break
        elif in_album_view:
            if key == curses.KEY_DOWN and current_album_index < len(album_names) - 1:
                current_album_index += 1
                if current_album_index >= scroll_offset + max_display:
                    scroll_offset += 1
            elif key == curses.KEY_UP and current_album_index > 0:
                current_album_index -= 1
                if current_album_index < scroll_offset:
                    scroll_offset -= 1
            elif key == ord("\n"):
                if album_names[current_album_index] == "view everything":
                    song_list = [(song, get_metadata(song)) for song in playlist]
                else:
                    song_list = albums[album_names[current_album_index]]
                if not shuffle:
                    song_list = sort_album_songs(song_list)
                current_song_index = 0
                scroll_offset = 0
                in_album_view = False
        else:
            if key == curses.KEY_DOWN and current_song_index < len(song_list) - 1:
                current_song_index += 1
                if current_song_index >= scroll_offset + max_display:
                    scroll_offset += 1
            elif key == curses.KEY_UP and current_song_index > 0:
                current_song_index -= 1
                if current_song_index < scroll_offset:
                    scroll_offset -= 1
            elif key == ord(" "):
                if not is_playing:
                    pygame.mixer.music.load(song_list[current_song_index][0])
                    pygame.mixer.music.play()
                    is_playing = True
                else:
                    pygame.mixer.music.pause()
                    is_playing = False
            elif key == ord("b"):
                in_album_view = True
                scroll_offset = 0
            elif key == ord("l"):
                loop_mode = "looptrack" if loop_mode == "noloop" else "loopalbum" if loop_mode == "looptrack" else "noloop"
            elif key == ord("s"):
                shuffle = not shuffle
                if shuffle:
                    random.shuffle(song_list)
                else:
                    song_list = sort_album_songs(song_list)
            elif key == ord(">"):
                seek_position += 5
                pygame.mixer.music.set_pos(seek_position)
            elif key == ord("<"):
                seek_position = max(0, seek_position - 5)
                pygame.mixer.music.set_pos(seek_position)
            elif key == ord("v"):
                volume = min(1.0, volume + 0.1)
                pygame.mixer.music.set_volume(volume)
            elif key == ord("-"):
                volume = max(0.0, volume - 0.1)
                pygame.mixer.music.set_volume(volume)

        if not pygame.mixer.music.get_busy() and is_playing:
            if loop_mode == "looptrack":
                pygame.mixer.music.play()
            elif loop_mode == "loopalbum":
                current_song_index = (current_song_index + 1) % len(song_list)
                pygame.mixer.music.load(song_list[current_song_index][0])
                pygame.mixer.music.play()
            else:
                current_song_index += 1
                if current_song_index < len(song_list):
                    pygame.mixer.music.load(song_list[current_song_index][0])
                    pygame.mixer.music.play()
                else:
                    is_playing = False

        stdscr.refresh()
        curses.napms(100)

    pygame.mixer.quit()

if __name__ == "__main__":
    music_dir = os.path.expanduser("~/Music")
    playlist = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.endswith((".mp3", ".wav", ".ogg"))] # technical limitation with pygame does not allow more formats
    curses.wrapper(main, playlist)
