"""Documents: a title, which is the file name, and a body, the file's text.

Everything lives in one folder as <title>.md (older .txt files are listed
too). A new document has no file until it gets a title. Saving writes a
temporary file and renames it over the old one, and the folder is synced
after every rename, so a power cut can never leave a half-written file.
"""

import os
import tempfile
import time

WRITING_DIR = os.path.expanduser('~/writing')
EXTENSION = '.md'
LISTED = ('.md', '.txt')


TRASH = '.trash'  # deleted things go here, out of sight but not gone


def list_documents(folder=WRITING_DIR):
    """(title, path) for every document in folder, most recently edited first."""
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return []
    paths = [os.path.join(folder, n) for n in names
             if n.endswith(LISTED) and not n.startswith('.')]
    paths = [p for p in paths if os.path.isfile(p)]
    paths.sort(key=os.path.getmtime, reverse=True)
    return [(os.path.splitext(os.path.basename(p))[0], p) for p in paths]


def list_folders(folder):
    """(name, path) for every folder in folder, A to Z."""
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return []
    found = [(n, os.path.join(folder, n)) for n in names if not n.startswith('.')]
    return sorted((f for f in found if os.path.isdir(f[1])), key=lambda f: f[0].lower())


def free_name(folder, name):
    """name, or 'name (2)', 'name (3)'... whichever nothing in folder has."""
    try:
        taken = {n.lower() for n in os.listdir(folder)}
    except FileNotFoundError:
        taken = set()
    candidate, n = name, 1
    while candidate.lower() in taken:
        n += 1
        candidate = f'{name} ({n})'
    return candidate


def make_folder(parent, name):
    """Creates a folder in parent (' (2)' etc. if the name is taken) and
    returns its path."""
    path = os.path.join(parent, free_name(parent, clean_title(name)))
    os.mkdir(path)
    sync_folder(parent)
    return path


def create_document(folder, title):
    """Creates an empty document in folder (' (2)' etc. if the title is
    taken) and returns its path."""
    path = os.path.join(folder, free_title(clean_title(title), folder) + EXTENSION)
    write_atomic(path, '')
    return path


def move(path, destination):
    """Moves a document or folder into destination, adding ' (2)' etc. if
    its name is taken there. Returns its new path."""
    if os.path.isdir(path):
        name = free_name(destination, os.path.basename(path))
    else:
        title, extension = os.path.splitext(os.path.basename(path))
        name = free_title(title, destination) + extension
    new_path = os.path.join(destination, name)
    os.rename(path, new_path)
    sync_folder(os.path.dirname(path))
    sync_folder(destination)
    return new_path


def trash(path, root):
    """Moves a document or folder into root's hidden trash folder."""
    trash_folder = os.path.join(root, TRASH)
    os.makedirs(trash_folder, exist_ok=True)
    return move(path, trash_folder)


def clean_title(title):
    """The title as a file name can hold it: no '/', no leading dot."""
    return title.replace('/', '-').strip().lstrip('.').strip()


def free_title(title, folder, own_path=None):
    """title, or 'title (2)', 'title (3)'... whichever no other document has.
    Upper and lower case count as the same, so the folder stays safe to
    copy to Windows or open in Obsidian."""
    taken = {t.lower() for t, p in list_documents(folder) if p != own_path}
    candidate, n = title, 1
    while candidate.lower() in taken:
        n += 1
        candidate = f'{title} ({n})'
    return candidate


def sync_folder(folder):
    """Makes a new or renamed file in folder survive a power cut."""
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_atomic(path, text):
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.remove(tmp)
        raise
    sync_folder(folder)


class Document:
    def __init__(self, path=None, folder=WRITING_DIR):
        self.folder = os.path.dirname(path) if path else folder
        self.path = path
        self.title = os.path.splitext(os.path.basename(path))[0] if path else ''
        self.lines = ['']
        if path and os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                self.lines = f.read().split('\n')
        self.dirty = False
        self.edited_at = 0.0  # when the latest change was made (for autosave)

    def changed(self):
        """Call after every edit of lines; autosave uses edited_at."""
        if not self.dirty:
            self.dirty = True
        self.edited_at = time.monotonic()

    def save(self):
        if self.path:
            write_atomic(self.path, '\n'.join(self.lines))
            self.dirty = False

    def set_title(self, title):
        """Gives the document a title, creating or renaming its file. Returns
        the title it got: ' (2)' etc. is added if the name is taken."""
        os.makedirs(self.folder, exist_ok=True)
        title = free_title(clean_title(title), self.folder, self.path)
        extension = os.path.splitext(self.path)[1] if self.path else EXTENSION
        new_path = os.path.join(self.folder, title + extension)
        if self.path is None:
            write_atomic(new_path, '\n'.join(self.lines))
            self.dirty = False
        elif new_path != self.path:
            os.rename(self.path, new_path)
            sync_folder(self.folder)
        self.path, self.title = new_path, title
        return title
