from PIL import Image
import PySimpleGUI as Gui
import re
import subprocess
from contextlib import contextmanager
from errno import ENOENT
from glob import iglob
from os import environ
from os import extsep
from os import remove
from os.path import normcase
from os.path import normpath
from os.path import realpath
from tempfile import NamedTemporaryFile

layout = [
    [
        Gui.Text('File'),
        Gui.InputText(),
        Gui.FileBrowse(),
        Gui.Radio('RUS', 'LANG', default=True),
        Gui.Radio('ENG', 'LANG', default=False)
    ],
    [Gui.Output(size=(88, 20))],
    [Gui.Submit()]
]

window = Gui.Window('Text Recognition', layout)
tesseract_cmd = 'tesseract'


class TesseractError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        self.message = message
        self.args = (status, message)


class TesseractNotFoundError(EnvironmentError):
    def __init__(self):
        super(TesseractNotFoundError, self).__init__(
            f"{tesseract_cmd} is not installed or it's not in your PATH."
            + ' See README file for more information.',
            )


@contextmanager
def timeout_manager(proc):
    try:
        yield proc.communicate()[1]
        return
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()


def get_errors(error_string):
    return u' '.join(
        line for line in error_string.decode('utf-8').splitlines()
    ).strip()


def cleanup(temp_name):
    for filename in iglob(temp_name + '*' if temp_name else temp_name):
        try:
            remove(filename)
        except OSError as e:
            if e.errno != ENOENT:
                raise e


def prepare(image):
    if not isinstance(image, Image.Image):
        raise TypeError('Unsupported image object')

    extension = 'PNG' if not image.format else image.format

    if 'A' in image.getbands():
        background = Image.new('RGB', image.size, (255, 255, 255))
        background.paste(image, (0, 0), image.getchannel('A'))
        image = background

    image.format = extension
    return image, extension


@contextmanager
def save(image):
    try:
        with NamedTemporaryFile(prefix='tess_', delete=False) as f:
            if isinstance(image, str):
                yield f.name, realpath(normpath(normcase(image)))
                return
            image, extension = prepare(image)
            input_file_name = f.name + extsep + extension
            image.save(input_file_name, format=image.format)
            yield f.name, input_file_name
    finally:
        cleanup(f.name)


def subprocess_args(include_stdout=True):
    kwargs = {
        'stdin': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'startupinfo': None,
        'env': environ,
    }

    if hasattr(subprocess, 'STARTUPINFO'):
        kwargs['startupinfo'] = subprocess.STARTUPINFO()
        kwargs['startupinfo'].dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs['startupinfo'].wShowWindow = subprocess.SW_HIDE

    if include_stdout:
        kwargs['stdout'] = subprocess.PIPE

    return kwargs


def run_tesseract(input_filename, output_filename_base, extension, lang):
    cmd_args = []
    cmd_args += (tesseract_cmd, input_filename, output_filename_base)

    if lang is not None:
        cmd_args += ('-l', lang)

    if extension:
        cmd_args.append(extension)

    try:
        proc = subprocess.Popen(cmd_args, **subprocess_args())
    except OSError as e:
        if e.errno != ENOENT:
            raise e
        raise TesseractNotFoundError()

    with timeout_manager(proc) as error_string:
        if proc.returncode:
            raise TesseractError(proc.returncode, get_errors(error_string))


def run_and_get_output(image, extension='', lang=None):
    with save(image) as (temp_name, input_filename):
        kwargs = {
            'input_filename': input_filename,
            'output_filename_base': temp_name,
            'extension': extension,
            'lang': lang,
        }
        run_tesseract(**kwargs)
        filename = kwargs['output_filename_base'] + extsep + extension
        with open(filename, 'rb') as output_file:
            return output_file.read().decode('utf-8')


def image_to_string(image, lang):
    args = [image, 'txt', lang]
    return run_and_get_output(*args)


def process_image(image_name, lang_code):
    return image_to_string(Image.open(image_name), lang_code)


while True:
    event, values = window.read()
    image_regex = '\S+.(png|jpg|jpeg)$'

    file_path = values[0]
    lang_code = 'rus' if values[1] else 'eng'

    if event in (None, 'Exit'):
        break
    if event == 'Submit' and re.match(image_regex, file_path):
        data = process_image(file_path, lang_code)
        print(data)
    else:
        print('File path is invalid')
