# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from colorama import Fore, Style
from mutagen import mp3, id3, flac, aiff, oggvorbis, oggopus, aac
from stat import ST_SIZE
from spotify_ripper.utils import *
from datetime import datetime
import os
import sys
import base64


def set_metadata_tags(args, audio_file, idx, track, ripper):
    # log completed file
    print(Fore.GREEN + Style.BRIGHT + os.path.basename(audio_file) +
          Style.NORMAL + "\t[ " +
          format_size(os.stat(enc_str(audio_file))[ST_SIZE]) + " ]" +
          Fore.RESET)

    if args.output_type == "wav" or args.output_type == "pcm":
        print(Fore.YELLOW + "Skipping metadata tagging for " +
              args.output_type + " encoding...")
        return

    # ensure everything is loaded still
    if not track.is_loaded:
        track.load(args.timeout)
    if not track.album.is_loaded:
        track.album.load(args.timeout)
    album_browser = track.album.browse()
    album_browser.load(args.timeout)

    # calculate num of tracks on disc and num of dics
    num_discs = 0
    num_tracks = 0
    for track_browse in album_browser.tracks:
        if (track_browse.disc == track.disc and
                track_browse.index > track.index):
            num_tracks = track_browse.index
        if track_browse.disc > num_discs:
            num_discs = track_browse.disc

    # try to get genres from Spotify's Web API
    genres = None
    if args.genres is not None:
        genres = ripper.web.get_genres(args.genres, track)

    # use mutagen to update id3v2 tags and vorbis comments
    try:
        audio = None
        on_error = 'replace' if args.ascii_path_only else 'ignore'
        album = to_ascii(track.album.name, on_error)
        artists = ", ".join([artist.name for artist in track.artists]) \
            if args.all_artists else track.artists[0].name
        artists_ascii = to_ascii(artists, on_error)
        album_artist = to_ascii(track.album.artist.name, on_error)
        title = to_ascii(track.name, on_error)

        # the comment tag can be formatted
        if args.comment is not None:
            comment = \
                format_track_string(ripper, args.comment, idx, track)
            comment_ascii = to_ascii(comment, on_error)

        if args.grouping is not None:
            grouping = \
                format_track_string(ripper, args.grouping, idx, track)
            grouping_ascii = to_ascii(grouping, on_error)

        if genres is not None and genres:
            genres_ascii = [to_ascii(genre) for genre in genres]

        # cover art image
        image = None
        if args.large_cover_art:
            image = ripper.web.get_large_coverart(track.link.uri)

        # if we fail, use regular cover size
        if image is None:
            image = track.album.cover()
            if image is not None:
                image.load(args.timeout)
                image = image.data

        def tag_to_ascii(_str, _str_ascii):
            return _str if args.ascii_path_only else _str_ascii

        def idx_of_total_str(_idx, _total):
            if _total > 0:
                return "%d/%d" % (_idx, _total)
            else:
                return "%d" % (_idx)

        def save_cover_image(embed_image_func):
            if image is not None:
                def write_image(file_name):
                    cover_path = os.path.dirname(audio_file)
                    cover_file = os.path.join(cover_path, file_name)
                    if not path_exists(cover_file):
                        with open(enc_str(cover_file), "wb") as f:
                            f.write(image)

                if args.cover_file is not None:
                    write_image(args.cover_file)
                elif args.cover_file_and_embed is not None:
                    write_image(args.cover_file_and_embed)
                    embed_image_func(image)
                else:
                    embed_image_func(image)

        def set_id3_tags(audio):
            # add ID3 tag if it doesn't exist
            audio.add_tags()

            def embed_image(data):
                audio.tags.add(
                    id3.APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Front Cover',
                        data=data
                    )
                )

            save_cover_image(embed_image)

            if album is not None:
                audio.tags.add(
                    id3.TALB(text=[tag_to_ascii(track.album.name, album)],
                             encoding=3))
            audio.tags.add(
                id3.TIT2(text=[tag_to_ascii(track.name, title)],
                         encoding=3))
            audio.tags.add(
                id3.TPE1(text=[tag_to_ascii(artists, artists_ascii)],
                         encoding=3))
            if album_artist is not None:
                audio.tags.add(
                    id3.TPE2(text=[tag_to_ascii(
                                       track.album.artist.name, album_artist)],
                             encoding=3))
            audio.tags.add(id3.TDRC(text=[str(track.album.year)],
                                    encoding=3))
            audio.tags.add(
                id3.TPOS(text=[idx_of_total_str(track.disc, num_discs)],
                         encoding=3))
            audio.tags.add(
                id3.TRCK(text=[idx_of_total_str(track.index, num_tracks)],
                         encoding=3))
            if args.comment is not None:
                audio.tags.add(
                    id3.COMM(text=[tag_to_ascii(comment, comment_ascii)],
                             encoding=3))
            if args.grouping is not None:
                audio.tags.add(
                    id3.TIT1(text=[tag_to_ascii(grouping, grouping_ascii)],
                             encoding=3))
            if genres is not None and genres:
                tcon_tag = id3.TCON(encoding=3)
                tcon_tag.genres = genres if args.ascii_path_only \
                    else genres_ascii
                audio.tags.add(tcon_tag)

            if args.id3_v23:
                audio.tags.update_to_v23()
                audio.save(v2_version=3, v23_sep='/')
                audio.tags.version = (2, 3, 0)
            else:
                audio.save()

        # aac is not well supported
        def set_id3_tags_raw(audio, audio_file):
            try:
                id3_dict = id3.ID3(audio_file)
            except id3.ID3NoHeaderError:
                id3_dict = id3.ID3()

            def embed_image(data):
                id3_dict.add(
                    id3.APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,
                        desc='Front Cover',
                        data=data
                    )
                )

            save_cover_image(embed_image)

            if album is not None:
                id3_dict.add(
                    id3.TALB(text=[tag_to_ascii(track.album.name, album)],
                             encoding=3))
            id3_dict.add(
                id3.TIT2(text=[tag_to_ascii(track.name, title)],
                         encoding=3))
            id3_dict.add(
                id3.TPE1(text=[tag_to_ascii(artists, artists_ascii)],
                         encoding=3))
            if album_artist is not None:
                id3_dict.add(
                    id3.TPE2(text=[tag_to_ascii(
                                       track.album.artist.name, album_artist)],
                             encoding=3))
            id3_dict.add(id3.TDRC(text=[str(track.album.year)],
                                  encoding=3))
            id3_dict.add(
                id3.TPOS(text=[idx_of_total_str(track.disc, num_discs)],
                         encoding=3))
            id3_dict.add(
                id3.TRCK(text=[idx_of_total_str(track.index, num_tracks)],
                         encoding=3))
            if args.comment is not None:
                id3_dict.add(
                    id3.COMM(text=[tag_to_ascii(comment, comment_ascii)],
                             encoding=3))
            if args.grouping is not None:
                audio.tags.add(
                    id3.TIT1(text=[tag_to_ascii(grouping, grouping_ascii)],
                             encoding=3))
            if genres is not None and genres:
                tcon_tag = id3.TCON(encoding=3)
                tcon_tag.genres = genres if args.ascii_path_only \
                    else genres_ascii
                id3_dict.add(tcon_tag)

            if args.id3_v23:
                id3_dict.update_to_v23()
                id3_dict.save(audio_file, v2_version=3, v23_sep='/')
                id3_dict.version = (2, 3, 0)
            else:
                id3_dict.save(audio_file)
            audio.tags = id3_dict

        def set_vorbis_comments(audio):
            # add Vorbis comment block if it doesn't exist
            if audio.tags is None:
                audio.add_tags()

            def embed_image(data):
                pic = flac.Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "Front Cover"
                pic.data = data
                if args.output_type == "flac":
                    audio.add_picture(pic)
                else:
                    data = base64.b64encode(pic.write())
                    audio["METADATA_BLOCK_PICTURE"] = [data.decode("ascii")]

            save_cover_image(embed_image)

            if album is not None:
                audio.tags["ALBUM"] = tag_to_ascii(track.album.name, album)
            audio.tags["TITLE"] = tag_to_ascii(track.name, title)
            audio.tags["ARTIST"] = tag_to_ascii(artists, artists_ascii)
            if album_artist is not None:
                audio.tags["ALBUMARTIST"] = \
                    tag_to_ascii(track.album.artist.name, album_artist)
            audio.tags["DATE"] = str(track.album.year)
            audio.tags["YEAR"] = str(track.album.year)
            audio.tags["DISCNUMBER"] = str(track.disc)
            audio.tags["DISCTOTAL"] = str(num_discs)
            audio.tags["TRACKNUMBER"] = str(track.index)
            audio.tags["TRACKTOTAL"] = str(num_tracks)
            if args.comment is not None:
                audio.tags["COMMENT"] = tag_to_ascii(comment, comment_ascii)
            if args.grouping is not None:
                audio.tags["GROUPING"] = \
                    tag_to_ascii(grouping, grouping_ascii)

            if genres is not None and genres:
                _genres = genres if args.ascii_path_only else genres_ascii
                audio.tags["GENRE"] = ", ".join(_genres)

            audio.save()

        # only called by Python 3
        def set_mp4_tags(audio):
            # add MP4 tags if it doesn't exist
            if audio.tags is None:
                audio.add_tags()

            def embed_image(data):
                audio.tags["covr"] = mp4.MP4Cover(data)

            save_cover_image(embed_image)

            if album is not None:
                audio.tags["\xa9alb"] = tag_to_ascii(track.album.name, album)
            audio["\xa9nam"] = tag_to_ascii(track.name, title)
            audio.tags["\xa9ART"] = tag_to_ascii(artists, artists_ascii)
            if album_artist is not None:
                audio.tags["aART"] = \
                    tag_to_ascii(track.album.artist.name, album_artist)
            audio.tags["\xa9day"] = str(track.album.year)
            audio.tags["disk"] = [(track.disc, num_discs)]
            audio.tags["trkn"] = [(track.index, num_tracks)]
            if args.comment is not None:
                audio.tags["\xa9cmt"] = tag_to_ascii(comment, comment_ascii)
            if args.grouping is not None:
                audio.tags["\xa9grp"] = tag_to_ascii(grouping, grouping_ascii)

            if genres is not None and genres:
                _genres = genres if args.ascii_path_only else genres_ascii
                audio.tags["\xa9gen"] = ", ".join(_genres)

            audio.save()

        def set_m4a_tags(audio):
            # add M4A tags if it doesn't exist
            audio.add_tags()

            def embed_image(data):
                audio.tags[str("covr")] = m4a.M4ACover(data)

            save_cover_image(embed_image)

            if album is not None:
                audio.tags[b"\xa9alb"] = tag_to_ascii(track.album.name, album)
            audio[b"\xa9nam"] = tag_to_ascii(track.name, title)
            audio.tags[b"\xa9ART"] = tag_to_ascii(artists, artists_ascii)
            if album_artist is not None:
                audio.tags[str("aART")] = tag_to_ascii(
                    track.album.artist.name, album_artist)
            audio.tags[b"\xa9day"] = str(track.album.year)
            audio.tags[str("disk")] = (track.disc, num_discs)
            audio.tags[str("trkn")] = (track.index, num_tracks)
            if args.comment is not None:
                audio.tags[b"\xa9cmt"] = tag_to_ascii(comment, comment_ascii)
            if args.grouping is not None:
                audio.tags[b"\xa9grp"] = tag_to_ascii(grouping, grouping_ascii)

            if genres is not None and genres:
                _genres = genres if args.ascii_path_only else genres_ascii
                audio.tags[b"\xa9gen"] = ", ".join(_genres)

            audio.save()

        if args.output_type == "flac":
            audio = flac.FLAC(audio_file)
            set_vorbis_comments(audio)
        if args.output_type == "aiff":
            audio = aiff.AIFF(audio_file)
            set_id3_tags(audio)
        elif args.output_type == "ogg":
            audio = oggvorbis.OggVorbis(audio_file)
            set_vorbis_comments(audio)
        elif args.output_type == "opus":
            audio = oggopus.OggOpus(audio_file)
            set_vorbis_comments(audio)
        elif args.output_type == "aac":
            audio = aac.AAC(audio_file)
            set_id3_tags_raw(audio, audio_file)
        elif args.output_type == "m4a":
            if sys.version_info >= (3, 0):
                from mutagen import mp4

                audio = mp4.MP4(audio_file)
                set_mp4_tags(audio)
            else:
                from mutagen import m4a, mp4

                audio = m4a.M4A(audio_file)
                set_m4a_tags(audio)
                audio = mp4.MP4(audio_file)
        elif args.output_type == "alac.m4a":
            if sys.version_info >= (3, 0):
                from mutagen import mp4

                audio = mp4.MP4(audio_file)
                set_mp4_tags(audio)
            else:
                from mutagen import m4a, mp4

                audio = m4a.M4A(audio_file)
                set_m4a_tags(audio)
                audio = mp4.MP4(audio_file)
        elif args.output_type == "mp3":
            audio = mp3.MP3(audio_file, ID3=id3.ID3)
            set_id3_tags(audio)

        def bit_rate_str(bit_rate):
            brs = "%d kb/s" % bit_rate
            if not args.cbr:
                brs = "~" + brs
            return brs

        def mode_str(mode):
            modes = ["Stereo", "Joint Stereo", "Dual Channel", "Mono"]
            if mode < len(modes):
                return modes[mode]
            else:
                return ""

        def channel_str(num):
            channels = ["", "Mono", "Stereo"]
            if num < len(channels):
                return channels[num]
            else:
                return ""

        # log id3 tags
        print("-" * 79)
        print(Fore.YELLOW + "Setting artist: " + artists_ascii + Fore.RESET)
        if album is not None:
            print(Fore.YELLOW + "Setting album: " + album + Fore.RESET)
        if album_artist is not None:
            print(Fore.YELLOW + "Setting album artist: " + album_artist +
                  Fore.RESET)
        print(Fore.YELLOW + "Setting title: " + title + Fore.RESET)
        print(Fore.YELLOW + "Setting track info: (" +
              str(track.index) + ", " + str(num_tracks) + ")" + Fore.RESET)
        print(Fore.YELLOW + "Setting disc info: (" + str(track.disc) +
              ", " + str(num_discs) + ")" + Fore.RESET)
        print(Fore.YELLOW + "Setting release year: " +
              str(track.album.year) + Fore.RESET)
        if genres is not None and genres:
            print(Fore.YELLOW + "Setting genres: " +
                  " / ".join(genres_ascii) + Fore.RESET)
        if image is not None:
            print(Fore.YELLOW + "Adding cover image" + Fore.RESET)
        if args.comment is not None:
            print(Fore.YELLOW + "Adding comment: " + comment_ascii +
                  Fore.RESET)
        if args.grouping is not None:
            print(Fore.YELLOW + "Adding grouping: " + grouping_ascii +
                  Fore.RESET)
        if args.output_type == "flac":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tFree Lossless Audio Codec" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Vorbis comments - " +
                  audio.tags.vendor + Fore.RESET)
            print("-" * 79)
        if args.output_type == "aiff":
            print("Time: " + format_time(audio.info.length) +
                  "\tAudio Interchange File Format" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print(
                Fore.YELLOW + "Writing ID3 version " +
                id3_version + Fore.RESET)
            print("-" * 79)
        if args.output_type == "alac.m4a":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tApple Lossless" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Apple iTunes metadata - " +
                  Fore.RESET)
            print("-" * 79)
        elif args.output_type == "ogg":
            print("Time: " + format_time(audio.info.length) +
                  "\tOgg Vorbis Codec" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Vorbis comments - " +
                  audio.tags.vendor + Fore.RESET)
            print("-" * 79)
        elif args.output_type == "opus":
            print("Time: " + format_time(audio.info.length) + "\tOpus Codec" +
                  "\t[ " + channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Vorbis comments - " +
                  audio.tags.vendor + Fore.RESET)
            print("-" * 79)
        elif args.output_type == "mp3":
            print("Time: " + format_time(audio.info.length) + "\tMPEG" +
                  str(audio.info.version) +
                  ", Layer " + ("I" * audio.info.layer) + "\t[ " +
                  bit_rate_str(audio.info.bitrate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  mode_str(audio.info.mode) + " ]")
            print("-" * 79)
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print(
                Fore.YELLOW + "Writing ID3 version " +
                id3_version + Fore.RESET)
            print("-" * 79)
        elif args.output_type == "aac":
            print("Time: " + format_time(audio.info.length) +
                  "\tAdvanced Audio Coding" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print(
                Fore.YELLOW + "Writing ID3 version " +
                id3_version + Fore.RESET)
            print("-" * 79)
        elif args.output_type == "m4a":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tMPEG-4 Part 14 Audio" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  channel_str(audio.info.channels) + " ]")
            print("-" * 79)
            print(Fore.YELLOW + "Writing Apple iTunes metadata - " +
                  str(audio.info.codec) + Fore.RESET)
            print("-" * 79)

    except id3.error:
        print(Fore.YELLOW + "Warning: exception while saving id3 tag: " +
              str(id3.error) + Fore.RESET)
