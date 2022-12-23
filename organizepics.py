#!/usr/bin/env python

from pathlib import Path
import asyncio
import threading
import queue
from PIL import Image
import exifread
import argparse
import sys
import tkinter as tk
from tkinter import ttk
import subprocess
import time
import shutil
import os

class FileProcessor(threading.Thread):
    def __init__(self, queue, simulate=False):
        super().__init__()
        self.queue = queue
        self.simulate = simulate

    def get_date(self, filepath):
        type = Image.open(filepath)
        if type == 'PNG':
            raise TypeError
        exif_tags = open(filepath, 'rb')
        tags = exifread.process_file(exif_tags)
        date = str(tags['EXIF DateTimeOriginal'])
        date_parts = date.split(':')
        year = date_parts[0]
        month = date_parts[1]
        return (year, month)

    def copy_file(self, filepath, year, month):
        newpath = os.path.normpath(os.path.join(filepath.parent, year, year + '_' + month))
        os.makedirs(newpath, exist_ok=True)
        shutil.copy2(filepath, newpath)
                    
    def run(self):
        while True:
            try:
                filepath = self.queue.get_nowait()
                if not self.simulate:
                    (year, month) = self.get_date(filepath)
                    self.copy_file(filepath, year, month)
                else:
                    print('Simulated processing of - ' + str(filepath))
                self.queue.task_done()
            except queue.Empty:
                break
            except TypeError:
                raise

class Pictures:
    def __init__(self, dirname, simulate=False):
        self.dirname = dirname
        self.queue = queue.Queue()
        self.file_processors = []
        self.track_progress = False
        for _ in range(4):
            self.file_processors.append(FileProcessor(self.queue, simulate))

    def process_dir(self):
        '''Extract files from directory'''
        self.dir = Path(self.dirname)
        self.files = [file for file in self.dir.iterdir() if file.is_file() and 
            (file.name.endswith('.JPG') or file.name.endswith('.jpg'))]
        
    def get_number_of_files(self):
        '''Read number of files in given directory'''
        return len(self.files)

    def get_number_of_converted_files(self):
        ret = 0
        if self.track_progress:
            ret = len(self.files) - self.queue.qsize()
        return ret

    def process_files(self):
        '''Reads the date of the picture and moves it to a corresponding subfolder'''
        for file in self.files:
            self.queue.put_nowait(file)
        self.__process_files()

    def __process_files(self):
        self.track_progress = True
        for file_processor in self.file_processors:
            file_processor.start()

    def wait_to_finish(self):
        self.queue.join()

class Comm:
    def __init__(self, ipaddr, simulate=False):
        self.pics = {}
        self.ipaddr = ipaddr
        self.simulate = simulate

    def _process(self, input):
        inputs = input.split()
        if len(inputs) < 2:
            ret = 'missingdir'
        elif inputs[1] not in self.pics and not input.startswith('open_directory'):
            ret = 'closeddir'
        else:
            dirname = inputs[1]
            if input.startswith('open_directory'):
                self.pics[dirname] = Pictures(dirname, self.simulate)
                self.pics[dirname].process_dir()
                ret = 'ok'
            elif input.startswith('get_number_of_files'):
                ret = str(self.pics[dirname].get_number_of_files())
            elif input.startswith('start_convertion'):
                self.pics[dirname].process_files()
                ret = 'ok'
            elif input.startswith('get_number_of_converted_files'):
                ret = str(self.pics[dirname].get_number_of_converted_files())
            elif input.startswith('close_directory'):
                self.pics[dirname].wait_to_finish()
                del self.pics[dirname]
                ret = 'ok'
            else:
                ret = 'invalid'
        return ret

    async def process(self, reader, writer):
        data = await reader.read(100)
        message = data.decode()
        return_data = self._process(message)
        writer.write(return_data.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def serve(self):
        server = await asyncio.start_server(
            self.process, self.ipaddr, 8888)
        async with server:
            await server.serve_forever()

class Client:
    def __init__(self, ipaddr):
        self.ipaddr = ipaddr
        self.reader = None
        self.writer = None
        self.dir = None

    async def __open(self):
        self.reader, self.writer = await asyncio.open_connection(
            self.ipaddr, 8888)
    
    async def __close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def opendir(self, dir):
        self.dir = dir
        msg = 'open_directory ' + dir.as_posix()
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

    async def closedir(self):
        msg = 'close_directory ' + self.dir.as_posix()
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

    async def get_nr_of_files(self):
        msg = 'get_number_of_files ' + self.dir.as_posix()
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return int(data.decode())

    async def get_nr_of_converted_files(self):
        msg = 'get_number_of_converted_files ' + self.dir.as_posix()
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return int(data.decode())

    async def convert(self):
        msg = 'start_convertion ' + self.dir.as_posix()
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

class ClientGui(ttk.Frame):
    def __init__(self, master, ipaddr):
        super().__init__(master)
        ttk.Frame(self)['padding'] = (3, 3, 12, 12)
        
        self.master = master
        self.master.title('Organize pics')
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        
        self.grid(column=0, row=0, sticky=(tk.N, tk.W, tk.E, tk.S))
        
        self.nr_of_files = 0
        self.nr_of_converted_files = 0
        self.client = Client(ipaddr)
        self.thread = None
        
        self.create_widgets()

    async def run_update_progress(self):
        self.nr_of_converted_files = await self.client.get_nr_of_converted_files()

    def update_progress(self):
        while self.thread.is_alive():
            time.sleep(0.1)
            asyncio.run(self.run_update_progress())
            self.progress_text.set(str(self.nr_of_converted_files) + '/' + str(self.nr_of_files))
            if self.nr_of_converted_files >= self.nr_of_files:
                asyncio.run(self.client.closedir())
                self.progress_text.set(str(self.nr_of_converted_files) + '/' + str(self.nr_of_files) + '-----> COMPLETED')
                self.exec_button['state'] = 'normal'
                break

    def create_widgets(self):
        self.progress_text = tk.StringVar()
        self.progress_var = ttk.Label(self, textvariable=self.progress_text).grid(column=1, row=3, sticky=tk.S)
        self.exec_button = ttk.Button(self, text='Convert', command=self.convert)
        self.exec_button.grid(column=3, row=2, sticky=(tk.S,tk.E))
        self.folder_button = ttk.Button(self, text='Browse', command=self.browse)
        self.folder_button.grid(column=1, row=1, sticky=(tk.N,tk.W))
        self.folder_text = tk.StringVar()
        self.folder_var = ttk.Entry(self, textvariable=self.folder_text).grid(column=3, row=1, sticky=tk.E)
        #self.folder_text.set('/media/share/tmp')
        self.folder_text.set('/home/raul/Pictures/something/')
        self.progress_text.set(str(self.nr_of_converted_files) + '/' + str(self.nr_of_files))

    def browse(self):
        self.file_dialog = tk.tkFileDialog()

    async def run_convert(self, folder):
        await self.client.opendir(folder)
        self.nr_of_files = await self.client.get_nr_of_files()
        await self.client.convert()

    def convert(self):
        folder = Path(self.folder_text.get())
        if not folder.is_dir():
            self.progress_text.set('invalid folder')
            return
        self.thread = threading.Thread(target=self.update_progress)
        self.exec_button['state'] = 'disabled'
        asyncio.run(self.run_convert(folder))
        self.thread.start()

async def main(ipaddr, test=False):
    comm = Comm(ipaddr, test)
    await comm.serve()
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Server and client for picture organization based on date.')
    parser.add_argument('--client', dest='client', action='store_true',
                        help='Run application as client widget')
    parser.add_argument('--ip', dest='ipaddr', default='127.0.0.1',
                        help='IP address to serve on or connect to')
    parser.add_argument('--standalone', action='store_true',
                        help='run server on the same machine')
    parser.add_argument('-t', '--test', action='store_true',
                        help='set if this is running the unittests')
    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='debug server while running tests in a separate process (execute server with -d and tests with -t -d)')
    parser.add_argument('--sim', action='store_true',
                        help='only simulate actions, do not create/modify files')
    args = parser.parse_args()

    if args.debug and not args.test:
        asyncio.run(main(args.ipaddr, True))
    elif not args.test:
        if not args.client:
            asyncio.run(main(args.ipaddr, args.sim))
        else:
            if args.standalone:
                proc_args = ['python3', 'organizepics.py']
                if args.sim:
                    proc_args.append('--sim')
                proc = subprocess.Popen(proc_args)
            root = tk.Tk()
            client = ClientGui(root, args.ipaddr)
            client.mainloop()
            if args.standalone:
                proc.terminate()
                proc.wait()
    else:
        import unittest
        import tempfile

        class TestFileProcessor(unittest.TestCase):
            def setUp(self):
                self.queue = queue.Queue()
                self.file_processor = FileProcessor(self.queue, True)

            def test_execution(self):
                self.queue.put_nowait('something')
                self.file_processor.start()
                self.queue.join()

        class TestPictures(unittest.TestCase):
            def setUp(self):
                self.picdir = tempfile.TemporaryDirectory()
                self.picture1 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.picture2 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.pictures = Pictures(self.picdir.name, True)

            def tearDown(self):
                self.picture1.close()
                self.picture2.close()
                self.picdir.cleanup()
                self.pictures.wait_to_finish()

            def test_process_dir(self):
                self.pictures.process_dir()

            def test_get_number_of_files(self):
                self.pictures.process_dir()
                nr = self.pictures.get_number_of_files()
                self.assertEqual(nr, 2)

        class TestComm(unittest.TestCase):
            def setUp(self):
                self.picdir = tempfile.TemporaryDirectory()
                self.picture1 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.picture2 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.comm = Comm('127.0.0.1', True)
                message = 'open_directory ' + self.picdir.name
                returned_message = self.comm._process(message)
                self.assertEqual(returned_message, 'ok')

            def tearDown(self):
                self.picture1.close()
                self.picture2.close()
                self.picdir.cleanup()         

            def test_get_number_of_files(self):
                message = 'get_number_of_files ' + self.picdir.name
                returned_message = self.comm._process(message)
                self.assertEqual(returned_message, '2')

            def test_start_convertion(self):
                message = 'start_convertion ' + self.picdir.name
                returned_message = self.comm._process(message)
                self.assertEqual(returned_message, 'ok')

            def test_get_number_of_converted_files(self):
                self.comm._process('start_convertion ' + self.picdir.name)
                message = 'get_number_of_converted_files ' + self.picdir.name
                returned_message = self.comm._process(message)
                self.assertEqual(returned_message, '2')

            def test_close_directory(self):
                message = 'close_directory ' + self.picdir.name
                returned_message = self.comm._process(message)
                self.assertEqual(returned_message, 'ok')

            def test_operations_on_wrong_directory(self):
                ret = self.comm._process('start_convertion ' + 'wrongdir')
                self.assertEqual(ret, 'closeddir')
                ret = self.comm._process('get_number_of_converted_files ' + 'wrongdir')
                self.assertEqual(ret, 'closeddir')
                ret = self.comm._process('close_directory ' + 'wrongdir')
                self.assertEqual(ret, 'closeddir')

            def test_undefined_operations(self):
                ret = self.comm._process('undefined ' + self.picdir.name)
                self.assertEqual(ret, 'invalid')

            def test_missing_directory(self):
                ret = self.comm._process('start_convertion')
                self.assertEqual(ret, 'missingdir')

        class TestClient(unittest.TestCase):
            async def run_server(self):
                if not args.debug:
                    self.proc = await asyncio.create_subprocess_exec('python3', *['organizepics.py', '--sim'])
                    await asyncio.sleep(0.3)

            async def stop_server(self):
                if not args.debug:
                    self.proc.terminate()
                    await self.proc.wait()

            def setUp(self):
                self.picdir = tempfile.TemporaryDirectory()
                self.picture1 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.picture2 = tempfile.NamedTemporaryFile(suffix='.jpg', dir=self.picdir.name)
                self.client = Client('127.0.0.1')

            def tearDown(self):
                self.picture1.close()
                self.picture2.close()
                self.picdir.cleanup()

            async def run_open_dir(self):
                try:
                    await self.run_server()
                    ret = await self.client.opendir(self.picdir)
                    self.assertTrue(ret)
                    ret = await self.client.closedir()
                    self.assertTrue(ret)
                finally:
                    await self.stop_server()

            async def run_get_nr_of_files(self):
                try:
                    await self.run_server()
                    ret = await self.client.opendir(self.picdir)
                    self.assertTrue(ret)
                    ret = await self.client.get_nr_of_files()
                    self.assertEqual(ret, 2)
                    ret = await self.client.closedir()
                    self.assertTrue(ret)
                finally:
                    await self.stop_server()

            async def run_get_nr_of_converted_files(self):
                try:
                    await self.run_server()
                    ret = await self.client.opendir(self.picdir)
                    self.assertTrue(ret)
                    ret = await self.client.get_nr_of_converted_files()
                    self.assertEqual(ret, 0)
                    ret = await self.client.closedir()
                    self.assertTrue(ret)
                finally:
                    await self.stop_server()

            async def run_convert(self):
                try:
                    await self.run_server()
                    ret = await self.client.opendir(self.picdir)
                    self.assertTrue(ret)
                    ret = await self.client.convert()
                    self.assertTrue(ret)
                    ret = await self.client.get_nr_of_converted_files()
                    self.assertEqual(ret, 2)
                    ret = await self.client.closedir()
                    self.assertTrue(ret)
                finally:
                    await self.stop_server()

            def test_open_dir(self):
                asyncio.run(self.run_open_dir())

            def test_get_nr_of_files(self):
                asyncio.run(self.run_get_nr_of_files())

            def test_get_nr_of_converted_files(self):
                asyncio.run(self.run_get_nr_of_converted_files())

            def test_run_convert(self):
                asyncio.run(self.run_convert())

        newargv = [arg for arg in sys.argv if arg not in ('-t', '--test', '-d', '--debug', '--ip')]
        # TODO catch ip address value to remove
        sys.argv = newargv

        unittest.main()
