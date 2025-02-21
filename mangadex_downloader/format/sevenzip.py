# MIT License

# Copyright (c) 2022 Rahman Yusuf

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging
import shutil
import os
import tqdm

from pathvalidate import sanitize_filename
from .base import (
    ConvertedChaptersFormat,
    ConvertedVolumesFormat,
    ConvertedSingleFormat
)
from .utils import get_chapter_info, NumberWithLeadingZeros
from ..utils import create_directory, delete_file
from ..errors import MangaDexException

try:
    import py7zr
except ImportError:
    PY7ZR_OK = False
else:
    PY7ZR_OK = True

class py7zrNotInstalled(MangaDexException):
    """Raised when py7zr is not installed"""
    pass

log = logging.getLogger(__name__)

class SevenZipFileExt:
    file_ext = ".cb7"

    def check_dependecies(self):
        if not PY7ZR_OK:
            raise py7zrNotInstalled("py7zr is not installed")

    def convert(self, images, path, pb=True): # `pb` stands for progress bar
        progress_bar = None
        if pb:
            # Don't mind me
            pb = self.config.no_progress_bar

        progress_bar = tqdm.tqdm(
            desc='cb7_progress',
            total=len(images),
            initial=0,
            unit='item',
            disable=pb
        )

        for im_path in images:

            with py7zr.SevenZipFile(path, "a" if os.path.exists(path) else "w") as zip_obj:
                zip_obj.write(im_path, im_path.name)
                progress_bar.update(1)
        
        progress_bar.close()

    def check_write_chapter_info(self, path, target):
        if not os.path.exists(path):
            return True

        with py7zr.SevenZipFile(path, 'r') as zip_obj:
            return target not in zip_obj.getnames()

class SevenZip(ConvertedChaptersFormat, SevenZipFileExt):
    def download_chapters(self, worker, chapters):
        # Begin downloading
        for chap_class, chap_images in chapters:
            count = NumberWithLeadingZeros(0)
            chap_name = chap_class.get_simplified_name()

            chapter_zip_path = self.path / (chap_name + self.file_ext)
            if chapter_zip_path.exists():
                if self.replace:
                    delete_file(chapter_zip_path)
                else:
                    log.info(f"'{chapter_zip_path.name}' is exist and replace is False, cancelling download...")
                    self.add_fi(chap_name, chap_class.id, chapter_zip_path)
                    continue

            chapter_path = create_directory(chap_name, self.path)

            images = self.get_images(chap_class, chap_images, chapter_path, count)

            log.info(f"{chap_name} has finished download, converting to cb7...")
            worker.submit(lambda: self.convert(images, chapter_zip_path))
            
            # Remove original chapter folder
            shutil.rmtree(chapter_path, ignore_errors=True)

            self.add_fi(chap_name, chap_class.id, chapter_zip_path)

class SevenZipVolume(ConvertedVolumesFormat, SevenZipFileExt):
    def download_volumes(self, worker, volumes):
        # Begin downloading
        for volume, chapters in volumes.items():
            images = []
            num = 0
            for chap_class, _ in chapters:
                # Each chapters has one page that has "Chapter n"
                # This is called "start of the chapter" image
                num += 1

                num += chap_class.pages

            count = NumberWithLeadingZeros(num)

            # Build volume folder name
            volume = self.get_volume_name(volume)

            volume_zip_path = self.path / (volume + self.file_ext)
            if volume_zip_path.exists():
                if self.replace:
                    delete_file(volume_zip_path)
                else:
                    log.info(f"'{volume_zip_path.name}' is exist and replace is False, cancelling download...")
                    self.add_fi(volume, None, volume_zip_path, chapters)
                    continue

            # Create volume folder
            volume_path = create_directory(volume, self.path)

            for chap_class, chap_images in chapters:
                # Insert "start of the chapter" image
                img_name = count.get() + '.png'

                # Make sure we never duplicated it
                write_start_image = self.check_write_chapter_info(volume_zip_path, img_name)

                if self.no_chapter_info:
                    write_start_image = False

                if write_start_image:
                    img_path = volume_path / img_name
                    get_chapter_info(chap_class, img_path, self.replace)
                    worker.submit(lambda: self.convert([img_path], volume_zip_path, False))

                count.increase()

                images.extend(self.get_images(chap_class, chap_images, volume_path, count))
            
            # Begin converting
            log.info(f"{volume} has finished download, converting to cb7...")
            worker.submit(lambda: self.convert(images, volume_zip_path))
                
            # Remove original chapter folder
            shutil.rmtree(volume_path, ignore_errors=True)

            self.add_fi(volume, None, volume_zip_path, chapters)

class SevenZipSingle(ConvertedSingleFormat, SevenZipFileExt):
    def download_single(self, worker, total, merged_name, chapters):
        images = []
        manga = self.manga
        count = NumberWithLeadingZeros(total)
        manga_zip_path = self.path / (merged_name + self.file_ext)

        if manga_zip_path.exists():
            if self.replace:
                delete_file(manga_zip_path)
            else:
                log.info(f"'{manga_zip_path.name}' is exist and replace is False, cancelling download...")
                self.add_fi(merged_name, None, manga_zip_path, chapters)
                return

        path = create_directory(merged_name, self.path)

        for chap_class, chap_images in chapters:
            # Insert "start of the chapter" image
            img_name = count.get() + '.png'

            # Make sure we never duplicated it
            write_start_image = self.check_write_chapter_info(manga_zip_path, img_name)

            if self.no_chapter_info:
                write_start_image = False

            if write_start_image:
                img_path = path / img_name
                get_chapter_info(chap_class, img_path, self.replace)
                worker.submit(lambda: self.convert([img_path], manga_zip_path, False))

            count.increase()

            images.extend(self.get_images(chap_class, chap_images, path, count))
        
        # Begin converting
        log.info(f"Manga '{manga.title}' has finished download, converting to cb7...")
        self.convert(images, manga_zip_path)

        # Remove original manga folder
        shutil.rmtree(path, ignore_errors=True)

        self.add_fi(merged_name, None, manga_zip_path, chapters)
