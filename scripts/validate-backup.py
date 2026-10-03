"""Validate both bundle layers before extracting any untrusted archive member."""
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath


def validate(archive, outer=False):
    names = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                or not (member.isfile() or member.isdir()) or member.name in names):
            raise ValueError("Unsafe backup archive")
        names.add(member.name)
    if outer and names != {"database.dump", "uploads.tar.gz", "README.txt"}:
        raise ValueError("Incomplete backup bundle")


def main():
    bundle, stage = map(Path, sys.argv[1:])
    with tarfile.open(bundle, "r:gz") as outer:
        validate(outer, outer=True)
        for name in ("database.dump", "uploads.tar.gz", "README.txt"):
            member = outer.getmember(name)
            if not member.isfile():
                raise ValueError("Expected a regular bundle member")
            with outer.extractfile(member) as source, (stage / name).open("wb") as target:
                shutil.copyfileobj(source, target)
    with tarfile.open(stage / "uploads.tar.gz", "r:gz") as uploads:
        validate(uploads)


if __name__ == "__main__":
    main()
