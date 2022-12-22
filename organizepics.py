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

class FileProcessor(threading.Thread):
    def __init__(self, queue, simulate=False):
        super().__init__()
        self.queue = queue
        self.simulate = simulate

    def run(self):
        while (True):
            try:
                file = self.queue.get_nowait()
                if not self.simulate:
                    type = Image.open(file)
                    if type == 'PNG':
                        raise TypeError
                    exif_tags = open(file, 'rb')
                    tags = exifread.process_file(exif_tags)
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
        msg = 'open_directory ' + dir.name
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

    async def closedir(self):
        msg = 'close_directory ' + self.dir.name
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

    async def get_nr_of_files(self):
        msg = 'get_number_of_files ' + self.dir.name
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return int(data.decode())

    async def get_nr_of_converted_files(self):
        msg = 'get_number_of_converted_files ' + self.dir.name
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return int(data.decode())

    async def convert(self):
        msg = 'start_convertion ' + self.dir.name
        await self.__open()
        self.writer.write(msg.encode())
        await self.writer.drain()
        data = await self.reader.read(100)
        await self.__close()
        return data.decode() == 'ok'

class ClientGui(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.pack()
        self.create_widgets()

    def create_widgets(self):
        self.hi_there = tk.Button(self)
        self.hi_there["text"] = "Hello World\n(click me)"
        self.hi_there["command"] = self.say_hi
        self.hi_there.pack(side="top")

        self.quit = tk.Button(self, text="QUIT", fg="red",
                              command=self.master.destroy)
        self.quit.pack(side="bottom")

    def say_hi(self):
        print("hi there, everyone!")

async def main(ipaddr, test=False):
    comm = Comm(ipaddr, test)
    await comm.serve()
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Server and client for picture organization based on date.')
    parser.add_argument('--client', dest='client', action='store_true',
                        help='Run application as client widget')
    parser.add_argument('--ip', dest='ipaddr', default='127.0.0.1',
                        help='IP address to serve on or connect to')
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
            root = tk.Tk()
            client = ClientGui(master=root)
            client.mainloop()
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
